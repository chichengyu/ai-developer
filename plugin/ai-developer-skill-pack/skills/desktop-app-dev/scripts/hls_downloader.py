"""HLS / m3u8 downloader with AES-128 key support and ffmpeg merge."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from media_downloader import CancelToken, DownloadCancelled, safe_output_name
from media_parser import M3U8Playlist, M3U8Variant, choose_best_variant, parse_m3u8
from media_session import MediaSession


@dataclass
class HLSProgress:
    task_id: int | str | None
    done: int
    total: int
    percent: float
    current: str
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    output_size: int | None = None
    stage: str = "segments"


@dataclass
class HLSResult:
    output_path: Path | None
    segments_downloaded: int
    total_segments: int
    output_dir: Path


def _load_playlist(
    session: MediaSession,
    playlist_url: str,
    quality: int | None = None,
) -> tuple[M3U8Playlist, str]:
    body, _ = session.get_bytes(playlist_url)
    playlist = parse_m3u8(body.decode("utf-8", "replace"), base_url=playlist_url)
    if playlist.is_master:
        variant: M3U8Variant | None
        if quality is not None and 0 <= quality < len(playlist.variants):
            variant = playlist.variants[quality]
        else:
            variant = choose_best_variant(playlist)
        if variant is None:
            raise RuntimeError("master playlist has no usable variant")
        body, _ = session.get_bytes(variant.url)
        playlist = parse_m3u8(body.decode("utf-8", "replace"), base_url=variant.url)
        return playlist, variant.url
    return playlist, playlist_url


def _download_keys(session: MediaSession, playlist: M3U8Playlist) -> dict[str, bytes]:
    keys: dict[str, bytes] = {}
    for key in playlist.keys:
        if key.method != "AES-128" or not key.uri or key.uri in keys:
            continue
        data, _ = session.get_bytes(key.uri)
        keys[key.uri] = data
    return keys


def _decrypt_segment(data: bytes, key: bytes, iv_hex: str | None) -> bytes:
    try:
        from Crypto.Cipher import AES
    except ImportError as exc:
        raise RuntimeError("AES-128 HLS requires pycryptodome: pip install pycryptodome") from exc
    normalized_iv = iv_hex[2:] if iv_hex and iv_hex.lower().startswith("0x") else iv_hex
    iv = bytes.fromhex(normalized_iv) if normalized_iv else key
    if len(iv) != 16:
        iv = key
    return AES.new(key, AES.MODE_CBC, iv=iv).decrypt(data)


def _download_segment(
    session: MediaSession,
    url: str,
    dest: Path,
    key: bytes | None,
    iv_hex: str | None,
    cancel: CancelToken | None,
    byterange: str | None = None,
) -> None:
    range_length: int | None = None
    offset = 0
    if byterange:
        length_text, _, offset_text = byterange.partition("@")
        range_length = int(length_text, 0)
        offset = int(offset_text, 0) if offset_text else 0
    if dest.exists() and dest.stat().st_size > 0:
        if range_length is None or dest.stat().st_size == range_length:
            return
        dest.unlink()
    tmp = dest.with_name(f"{dest.name}.tmp")
    headers = None
    if byterange and range_length is not None:
        headers = {"Range": f"bytes={offset}-{offset + range_length - 1}"}
    with session.open(url, headers=headers) as response, tmp.open("wb") as out:
        while True:
            if cancel and cancel.cancelled:
                raise DownloadCancelled()
            data = response.read(1024 * 1024)
            if not data:
                break
            out.write(data)
    if key is not None:
        encrypted = tmp.read_bytes()
        tmp.write_bytes(_decrypt_segment(encrypted, key, iv_hex))
    if range_length is not None and tmp.stat().st_size != range_length:
        raise RuntimeError(f"byterange segment incomplete: {tmp.stat().st_size}/{range_length}")
    os.replace(tmp, dest)


def _segment_suffix(uri: str) -> str:
    path = uri.split("?", 1)[0].lower()
    if path.endswith((".m4s", ".mp4", ".fmp4")):
        return ".m4s"
    return ".ts"


def _download_init_segment(
    session: MediaSession,
    playlist: M3U8Playlist,
    segments_dir: Path,
    cancel: CancelToken | None,
) -> Path | None:
    if not playlist.init_uri:
        return None
    dest = segments_dir / "init.mp4"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    _download_segment(
        session,
        playlist.init_uri,
        dest,
        key=None,
        iv_hex=None,
        cancel=cancel,
        byterange=playlist.init_byterange,
    )
    return dest


def _merge_without_ffmpeg(
    output_dir: Path,
    output_name: str,
    segments_dir: Path,
    segment_exts: list[str],
    init_path: Path | None,
) -> Path:
    """Concatenate segments directly when ffmpeg is not installed."""
    output_path = output_dir / output_name
    with output_path.open("wb") as out:
        if init_path is not None:
            with init_path.open("rb") as source:
                shutil.copyfileobj(source, out, 1024 * 1024)
        for index, ext in enumerate(segment_exts):
            segment = segments_dir / f"seg_{index:06d}{ext}"
            with segment.open("rb") as source:
                shutil.copyfileobj(source, out, 1024 * 1024)
    return output_path


def download_hls(
    playlist_url: str,
    output_dir: str | Path,
    output_name: str = "output.mp4",
    session: MediaSession | None = None,
    concurrency: int = 4,
    quality: int | None = None,
    progress: Callable[[HLSProgress], None] | None = None,
    cancel: CancelToken | None = None,
    ffmpeg_path: str | None = "ffmpeg",
    task_id: int | str | None = None,
    *,
    segment_retries: int = 3,
    merge_fallback: bool = True,
    keep_segments: bool = True,
) -> HLSResult:
    """Download an HLS stream and merge it with ffmpeg when available."""
    session = session or MediaSession()
    output_dir = Path(output_dir)
    output_name = safe_output_name(output_name, "output.mp4")
    segments_dir = output_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    playlist, _ = _load_playlist(session, playlist_url, quality=quality)
    if not playlist.segments:
        raise RuntimeError("playlist contains no segments")

    init_path = _download_init_segment(session, playlist, segments_dir, cancel)
    keys = _download_keys(session, playlist)
    total = len(playlist.segments)
    segment_exts = [_segment_suffix(segment.uri) for segment in playlist.segments]
    done = 0
    done_lock = threading.Lock()
    downloaded_bytes = 0
    downloaded_bytes_lock = threading.Lock()

    def on_segment_done(segment_url: str, segment_bytes: int) -> None:
        nonlocal done
        nonlocal downloaded_bytes
        with done_lock:
            done += 1
            with downloaded_bytes_lock:
                downloaded_bytes += segment_bytes
            if progress:
                progress(
                    HLSProgress(
                        task_id=task_id,
                        done=done,
                        total=total,
                        percent=done / total,
                        current=segment_url,
                        downloaded_bytes=downloaded_bytes,
                        total_bytes=None,
                        stage="segments",
                    )
                )

    def work(index: int, segment) -> None:
        dest = segments_dir / f"seg_{index:06d}{segment_exts[index]}"
        key_data = None
        iv_hex = None
        if segment.key_index is not None and segment.key_index < len(playlist.keys):
            key = playlist.keys[segment.key_index]
            if key.method == "AES-128" and key.uri:
                key_data = keys.get(key.uri)
                iv_hex = key.iv
        last_error: Exception | None = None
        for attempt in range(max(1, segment_retries)):
            try:
                _download_segment(
                    session,
                    segment.uri,
                    dest,
                    key_data,
                    iv_hex,
                    cancel,
                    byterange=segment.byterange,
                )
                on_segment_done(segment.uri, dest.stat().st_size)
                return
            except DownloadCancelled:
                raise
            except Exception as exc:
                last_error = exc
                if attempt < max(1, segment_retries) - 1:
                    time.sleep(min(2**attempt, 8))
        assert last_error is not None
        raise last_error

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(work, index, segment): segment
            for index, segment in enumerate(playlist.segments)
        }
        for future in as_completed(futures):
            future.result()

    concat_file = output_dir / "concat.txt"
    concat_items: list[Path] = []
    if init_path is not None:
        concat_items.append(init_path)
    concat_items.extend(segments_dir / f"seg_{i:06d}{segment_exts[i]}" for i in range(total))
    concat_lines = [f"file '{item}'" for item in concat_items]
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")

    output_path: Path | None = None
    if ffmpeg_path and shutil.which(ffmpeg_path):
        output_path = output_dir / output_name
        command = [
            ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(output_path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 and not merge_fallback:
            raise RuntimeError(f"ffmpeg merge failed: {result.stderr[-500:]}")
        if result.returncode != 0:
            output_path = _merge_without_ffmpeg(
                output_dir,
                output_name,
                segments_dir,
                segment_exts,
                init_path,
            )
    elif merge_fallback:
        output_path = _merge_without_ffmpeg(
            output_dir,
            output_name,
            segments_dir,
            segment_exts,
            init_path,
        )

    if output_path is not None and not keep_segments:
        shutil.rmtree(segments_dir, ignore_errors=True)
        if concat_file.exists():
            concat_file.unlink()

    if progress:
        output_size = output_path.stat().st_size if output_path is not None else None
        progress(
            HLSProgress(
                task_id=task_id,
                done=total,
                total=total,
                percent=1.0,
                current="merge",
                downloaded_bytes=downloaded_bytes,
                total_bytes=output_size,
                output_size=output_size,
                stage="merge",
            )
        )

    return HLSResult(
        output_path=output_path,
        segments_downloaded=done,
        total_segments=total,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    print("desktop-app-dev hls_downloader: import download_hls() for m3u8 segment downloads.")
