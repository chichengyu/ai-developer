"""HLS discovery, selection, and download client for authorized media work.

The client parses m3u8 playlists with the dependency-free parser in
`media_parser.py`, resolves a master playlist down to a media playlist, then
downloads init segments, keys, and media segments. AES-128 segments are
decrypted when `cryptography` or `pycryptodome` is installed; otherwise they
are saved in their encrypted form and the result reports the limitation.
"""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from media_parser import M3U8Playlist, M3U8Variant, parse_m3u8
from media_session import MediaSession
from proxy_pool import ProxyPool


class HLSError(RuntimeError):
    """Raised when a playlist cannot be fetched, selected, or downloaded."""


@dataclass
class HLSResolution:
    """One resolved media playlist plus the master metadata that led to it."""

    source_url: str
    media_url: str
    playlist: M3U8Playlist
    master_url: str | None = None
    variant: M3U8Variant | None = None
    master_text: str = ""
    media_text: str = ""

    @property
    def is_master(self) -> bool:
        return self.master_url is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "master_url": self.master_url,
            "media_url": self.media_url,
            "is_master": self.is_master,
            "variant": _variant_dict(self.variant) if self.variant else None,
            "segments": len(self.playlist.segments),
            "keys": [item.__dict__ for item in self.playlist.keys],
            "init_uri": self.playlist.init_uri,
            "target_duration": self.playlist.target_duration,
            "media_sequence": self.playlist.media_sequence,
            "endlist": self.playlist.endlist,
        }


@dataclass
class HLSDownloadResult:
    """Result of one HLS stream download."""

    url: str
    output_dir: str
    media_url: str
    master_playlist_path: str | None = None
    media_playlist_path: str | None = None
    combined_path: str | None = None
    segment_paths: list[str] = field(default_factory=list)
    downloaded_segments: int = 0
    failed_segments: int = 0
    total_bytes: int = 0
    decrypted: bool = False
    encrypted: bool = False
    encryption_method: str | None = None
    errors: list[str] = field(default_factory=list)
    resolution: HLSResolution | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "media_url": self.media_url,
            "output_dir": self.output_dir,
            "combined_path": self.combined_path,
            "segment_paths": len(self.segment_paths),
            "downloaded_segments": self.downloaded_segments,
            "failed_segments": self.failed_segments,
            "total_bytes": self.total_bytes,
            "decrypted": self.decrypted,
            "encrypted": self.encrypted,
            "encryption_method": self.encryption_method,
            "errors": list(self.errors),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "output_dir": self.output_dir,
            "media_url": self.media_url,
            "master_playlist_path": self.master_playlist_path,
            "media_playlist_path": self.media_playlist_path,
            "combined_path": self.combined_path,
            "segment_paths": list(self.segment_paths),
            "downloaded_segments": self.downloaded_segments,
            "failed_segments": self.failed_segments,
            "total_bytes": self.total_bytes,
            "decrypted": self.decrypted,
            "encrypted": self.encrypted,
            "encryption_method": self.encryption_method,
            "errors": list(self.errors),
            "resolution": self.resolution.to_dict() if self.resolution else None,
        }


def _variant_dict(variant: M3U8Variant) -> dict[str, Any]:
    return {
        "bandwidth": variant.bandwidth,
        "resolution": variant.resolution,
        "codecs": variant.codecs,
        "url": variant.url,
    }


def _variant_height(variant: M3U8Variant) -> int | None:
    if not variant.resolution:
        return None
    match = re.search(r"(\d+)x(\d+)", variant.resolution)
    if not match:
        return None
    with suppress(ValueError):
        return int(match.group(2))
    return None


class HLSClient:
    """Fetch, select, and download HLS playlists with one persistent session."""

    def __init__(
        self,
        session: MediaSession | None = None,
        *,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
        proxy_pool: ProxyPool | None = None,
        cookies: list[dict[str, Any]] | None = None,
        min_interval: float = 0.0,
        jitter: float = 0.2,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        backoff_max: float = 15.0,
        timeout: float = 30.0,
    ) -> None:
        self._owns_session = session is None
        if session is None:
            session = MediaSession(
                headers=headers,
                proxy=proxy,
                proxy_pool=proxy_pool,
                timeout=timeout,
                min_interval=min_interval,
                jitter=jitter,
                max_retries=max_retries,
                backoff_base=backoff_base,
                backoff_max=backoff_max,
            )
        self.session = session
        if cookies:
            self.session.load_cookies(cookies)

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def _fetch_bytes(
        self,
        url: str,
        range_header: str | None = None,
    ) -> tuple[bytes, int]:
        if range_header:
            body, _ = self.session.get_bytes(url, range_header=range_header)
            return body, 200
        body, status, _ = self.session.get_bytes_with_meta(url)
        if status >= 400:
            raise HLSError(f"HLS fetch failed with HTTP {status}: {url}")
        return body, status

    def _fetch_text(self, url: str) -> tuple[str, int]:
        body, status = self._fetch_bytes(url)
        return body.decode("utf-8", "replace"), status

    def _fetch_range(
        self,
        url: str,
        byterange: str | None,
    ) -> bytes:
        if not byterange:
            body, _ = self._fetch_bytes(url)
            return body
        length_text, _, offset_text = byterange.partition("@")
        try:
            length = int(length_text, 0)
            offset = int(offset_text, 0) if offset_text else 0
        except ValueError as exc:
            raise HLSError(f"invalid HLS BYTERANGE: {byterange}") from exc
        try:
            body, _ = self._fetch_bytes(
                url,
                range_header=f"bytes={offset}-{offset + length - 1}",
            )
            return body
        except Exception:
            full, _ = self._fetch_bytes(url)
            return full[offset : offset + length]

    def resolve(
        self,
        url: str,
        *,
        preferred_height: int | None = None,
        max_bandwidth: int | None = None,
    ) -> HLSResolution:
        """Fetch a playlist and resolve it to a concrete media playlist."""
        master_text, _ = self._fetch_text(url)
        master_playlist = parse_m3u8(master_text, base_url=url)
        if not master_playlist.is_master:
            return HLSResolution(
                source_url=url,
                media_url=url,
                playlist=master_playlist,
                master_url=None,
                master_text=master_text,
                media_text=master_text,
            )
        variant = self._select_variant(
            master_playlist,
            preferred_height=preferred_height,
            max_bandwidth=max_bandwidth,
        )
        if variant is None:
            raise HLSError(f"master playlist has no usable variant: {url}")
        media_url = variant.url
        media_text, _ = self._fetch_text(media_url)
        media_playlist = parse_m3u8(media_text, base_url=media_url)
        if media_playlist.is_master:
            raise HLSError("resolved playlist is still a master playlist")
        return HLSResolution(
            source_url=url,
            media_url=media_url,
            playlist=media_playlist,
            master_url=url,
            variant=variant,
            master_text=master_text,
            media_text=media_text,
        )

    def _select_variant(
        self,
        playlist: M3U8Playlist,
        *,
        preferred_height: int | None = None,
        max_bandwidth: int | None = None,
    ) -> M3U8Variant | None:
        variants = list(playlist.variants)
        if max_bandwidth is not None:
            variants = [item for item in variants if item.bandwidth <= max_bandwidth]
        if preferred_height is not None:
            eligible = [
                item
                for item in variants
                if (_variant_height(item) or 0) <= preferred_height
            ]
            if eligible:
                variants = eligible
        if not variants:
            return None
        return max(
            variants,
            key=lambda item: (
                item.bandwidth,
                _variant_height(item) or 0,
            ),
        )

    def download(
        self,
        url: str,
        output_dir: str | Path,
        *,
        preferred_height: int | None = None,
        max_bandwidth: int | None = None,
        include_segments: bool = True,
        combine: bool = True,
        decrypt: bool = True,
        save_playlists: bool = True,
        segment_prefix: str = "segment",
        overwrite: bool = False,
    ) -> HLSDownloadResult:
        """Download one HLS stream and optionally combine the segments."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        resolution = self.resolve(
            url,
            preferred_height=preferred_height,
            max_bandwidth=max_bandwidth,
        )
        result = HLSDownloadResult(
            url=url,
            output_dir=str(out),
            media_url=resolution.media_url,
            resolution=resolution,
        )
        if save_playlists:
            if resolution.master_text:
                master_path = out / "master.m3u8"
                if overwrite or not master_path.exists():
                    master_path.write_text(resolution.master_text, encoding="utf-8")
                result.master_playlist_path = str(master_path)
            media_path = out / "media.m3u8"
            if overwrite or not media_path.exists():
                media_path.write_text(resolution.media_text, encoding="utf-8")
            result.media_playlist_path = str(media_path)

        playlist = resolution.playlist
        keys: dict[int, bytes] = {}
        for index, key in enumerate(playlist.keys):
            if key.method not in {"AES-128", "AES-256"} or not key.uri:
                continue
            try:
                keys[index], _ = self._fetch_bytes(key.uri)
            except Exception as exc:
                result.errors.append(f"key {index}: {exc}")

        init_data: bytes | None = None
        if playlist.init_uri:
            try:
                init_data = self._fetch_range(playlist.init_uri, playlist.init_byterange)
            except Exception as exc:
                result.errors.append(f"init segment: {exc}")

        combined_path: Path | None = None
        combined_handle = None
        if combine:
            extension = ".mp4" if init_data else ".ts"
            candidate = out / f"combined{extension}"
            if overwrite or not candidate.exists():
                combined_handle = candidate.open("wb")
            combined_path = candidate
        if init_data and combined_handle is not None:
            combined_handle.write(init_data)
        decryptor = _AESDecryptor()
        try:
            for index, segment in enumerate(playlist.segments):
                try:
                    data = self._fetch_range(segment.uri, segment.byterange)
                    key_index = segment.key_index
                    if key_index is not None and key_index < len(playlist.keys):
                        key_spec = playlist.keys[key_index]
                        if key_spec.method in {"AES-128", "AES-256"}:
                            result.encrypted = True
                            result.encryption_method = key_spec.method
                            key_data = keys.get(key_index)
                            if decrypt and key_data and decryptor.available:
                                iv = _derive_iv(
                                    key_spec.iv,
                                    playlist.media_sequence + index,
                                )
                                data = decryptor.decrypt(data, key_data, iv)
                                result.decrypted = True
                            elif decrypt and key_data and not decryptor.available:
                                result.errors.append(
                                    "AES decryption unavailable: "
                                    "install cryptography or pycryptodome"
                                )
                    if include_segments:
                        segment_path = out / f"{segment_prefix}_{index:05d}.seg"
                        if overwrite or not segment_path.exists():
                            segment_path.write_bytes(data)
                        result.segment_paths.append(str(segment_path))
                    if combined_handle is not None:
                        combined_handle.write(data)
                    result.downloaded_segments += 1
                    result.total_bytes += len(data)
                except Exception as exc:
                    result.failed_segments += 1
                    result.errors.append(f"segment {index}: {exc}")
        finally:
            if combined_handle is not None:
                combined_handle.close()
        if combined_path is not None:
            result.combined_path = str(combined_path)
        return result


class _AESDecryptor:
    """Lazy AES-CBC decryptor backed by cryptography or pycryptodome."""

    def __init__(self) -> None:
        self._mode: str | None = None

    @property
    def available(self) -> bool:
        return self._load() is not None

    def _load(self) -> str | None:
        if self._mode is not None:
            return self._mode
        try:
            import cryptography  # noqa: F401

            self._mode = "cryptography"
        except ImportError:
            try:
                import Crypto  # noqa: F401

                self._mode = "pycryptodome"
            except ImportError:
                self._mode = "unavailable"
        return self._mode

    def decrypt(self, data: bytes, key: bytes, iv: bytes) -> bytes:
        mode = self._load()
        if mode == "cryptography":
            from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

            decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
            return decryptor.update(data) + decryptor.finalize()
        if mode == "pycryptodome":
            from Crypto.Cipher import AES

            return AES.new(key, AES.MODE_CBC, iv).decrypt(data)
        raise HLSError("AES decryption is unavailable")


def _derive_iv(iv_text: str | None, sequence: int) -> bytes:
    if iv_text:
        hex_value = iv_text[2:] if iv_text.lower().startswith("0x") else iv_text
        with suppress(ValueError):
            return bytes.fromhex(hex_value)
    return (sequence & ((1 << 128) - 1)).to_bytes(16, "big")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Resolve or download an HLS stream")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default=None, help="output directory for downloads")
    parser.add_argument("--height", type=int, default=None, help="preferred video height")
    parser.add_argument("--max-bandwidth", type=int, default=None)
    parser.add_argument(
        "--segments",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--combine", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--decrypt", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--headers", default=None, help="JSON headers object")
    args = parser.parse_args(argv)
    headers = json.loads(args.headers) if args.headers else None
    client = HLSClient(headers=headers, proxy=args.proxy)
    try:
        if args.output:
            result = client.download(
                args.url,
                args.output,
                preferred_height=args.height,
                max_bandwidth=args.max_bandwidth,
                include_segments=args.segments,
                combine=args.combine,
                decrypt=args.decrypt,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            resolution = client.resolve(
                args.url,
                preferred_height=args.height,
                max_bandwidth=args.max_bandwidth,
            )
            print(json.dumps(resolution.to_dict(), ensure_ascii=False, indent=2))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
