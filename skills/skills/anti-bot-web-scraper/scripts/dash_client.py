"""DASH MPD discovery, selection, and download client.

Supports static MPD manifests with SegmentTemplate, SegmentTimeline, and
SegmentList representations. CENC/DRM-protected streams are reported as
unsupported instead of producing a corrupt file.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from media_parser import (
    MPDPlaylist,
    MPDRepresentation,
    build_mpd_segment_urls,
    mpd_initialization_range,
    mpd_initialization_url,
    parse_mpd,
    select_mpd_representation,
)
from media_session import MediaSession
from proxy_pool import ProxyPool


class DASHError(RuntimeError):
    """Raised when an MPD manifest cannot be fetched, selected, or downloaded."""


@dataclass
class DASHResolution:
    url: str
    manifest_text: str
    playlist: MPDPlaylist
    representation: MPDRepresentation
    init_url: str | None
    init_range: str | None
    segment_urls: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "type": self.playlist.type,
            "media_presentation_duration": self.playlist.media_presentation_duration,
            "min_buffer_time": self.playlist.min_buffer_time,
            "representation": {
                "id": self.representation.id,
                "bandwidth": self.representation.bandwidth,
                "width": self.representation.width,
                "height": self.representation.height,
                "codecs": self.representation.codecs,
                "mime_type": self.representation.mime_type,
            },
            "init_url": self.init_url,
            "init_range": self.init_range,
            "segments": len(self.segment_urls),
        }


@dataclass
class DASHDownloadResult:
    url: str
    output_dir: str
    manifest_path: str | None = None
    init_path: str | None = None
    combined_path: str | None = None
    segment_paths: list[str] = field(default_factory=list)
    downloaded_segments: int = 0
    resumed_segments: int = 0
    failed_segments: int = 0
    total_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    resolution: DASHResolution | None = None
    metadata: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "init_path": self.init_path,
            "combined_path": self.combined_path,
            "segment_paths": len(self.segment_paths),
            "downloaded_segments": self.downloaded_segments,
            "resumed_segments": self.resumed_segments,
            "failed_segments": self.failed_segments,
            "total_bytes": self.total_bytes,
            "errors": list(self.errors),
            "metadata": self.metadata,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "output_dir": self.output_dir,
            "manifest_path": self.manifest_path,
            "init_path": self.init_path,
            "combined_path": self.combined_path,
            "segment_paths": list(self.segment_paths),
            "downloaded_segments": self.downloaded_segments,
            "resumed_segments": self.resumed_segments,
            "failed_segments": self.failed_segments,
            "total_bytes": self.total_bytes,
            "errors": list(self.errors),
            "resolution": self.resolution.to_dict() if self.resolution else None,
            "metadata": self.metadata,
        }


class DASHClient:
    """Fetch, select, and download DASH MPD streams with one session."""

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

    def _fetch_bytes(self, url: str) -> bytes:
        body, status, _ = self.session.get_bytes_with_meta(url)
        if status >= 400:
            raise DASHError(f"DASH fetch failed with HTTP {status}: {url}")
        return body

    def _fetch_text(self, url: str) -> str:
        return self._fetch_bytes(url).decode("utf-8", "replace")

    def _fetch_range(self, url: str, range_header: str) -> bytes:
        body, _ = self.session.get_bytes(url, range_header=range_header)
        return body

    def _fetch_bytes_with_retries(self, url: str, retries: int) -> bytes:
        last_error: Exception | None = None
        for attempt in range(max(0, int(retries)) + 1):
            try:
                return self._fetch_bytes(url)
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    time.sleep(0.2 * (2**attempt))
        if last_error is not None:
            raise last_error
        raise DASHError(f"DASH segment fetch failed: {url}")

    def resolve(
        self,
        url: str,
        *,
        preferred_height: int | None = None,
        max_bandwidth: int | None = None,
        max_segments: int = 1000,
    ) -> DASHResolution:
        manifest_text = self._fetch_text(url)
        playlist = parse_mpd(manifest_text, base_url=url)
        representation = select_mpd_representation(
            playlist,
            preferred_height=preferred_height,
            max_bandwidth=max_bandwidth,
        )
        if representation is None:
            raise DASHError(f"MPD has no usable representation: {url}")
        segment_urls = build_mpd_segment_urls(representation, max_segments=max_segments)
        init_range_info = mpd_initialization_range(representation)
        return DASHResolution(
            url=url,
            manifest_text=manifest_text,
            playlist=playlist,
            representation=representation,
            init_url=mpd_initialization_url(representation),
            init_range=init_range_info[1] if init_range_info else None,
            segment_urls=segment_urls,
        )

    def download(
        self,
        url: str,
        output_dir: str | Path,
        *,
        preferred_height: int | None = None,
        max_bandwidth: int | None = None,
        max_segments: int = 1000,
        include_segments: bool = True,
        combine: bool = True,
        save_manifest: bool = True,
        segment_prefix: str = "segment",
        overwrite: bool = False,
        segment_retries: int = 2,
    ) -> DASHDownloadResult:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        resolution = self.resolve(
            url,
            preferred_height=preferred_height,
            max_bandwidth=max_bandwidth,
            max_segments=max_segments,
        )
        result = DASHDownloadResult(url=url, output_dir=str(out), resolution=resolution)
        if save_manifest:
            manifest_path = out / "manifest.mpd"
            if overwrite or not manifest_path.exists():
                manifest_path.write_text(resolution.manifest_text, encoding="utf-8")
            result.manifest_path = str(manifest_path)

        init_data = b""
        if resolution.init_url:
            try:
                if resolution.init_range:
                    init_data = self._fetch_range(
                        resolution.init_url,
                        f"bytes={resolution.init_range}",
                    )
                else:
                    init_data = self._fetch_bytes(resolution.init_url)
                init_path = out / "init.mp4"
                if overwrite or not init_path.exists():
                    init_path.write_bytes(init_data)
                result.init_path = str(init_path)
            except Exception as exc:
                result.errors.append(f"init segment: {exc}")

        combined_handle = None
        combined_path: Path | None = None
        if combine:
            extension = ".mp4" if init_data else ".bin"
            candidate = out / f"combined{extension}"
            if overwrite or not candidate.exists():
                combined_handle = candidate.open("wb")
            combined_path = candidate
        if init_data and combined_handle is not None:
            combined_handle.write(init_data)

        try:
            for index, segment_url in enumerate(resolution.segment_urls):
                try:
                    segment_path = (
                        out / f"{segment_prefix}_{index:05d}.m4s"
                        if include_segments
                        else None
                    )
                    resumed = False
                    if (
                        segment_path is not None
                        and not overwrite
                        and segment_path.exists()
                        and segment_path.stat().st_size > 0
                    ):
                        data = segment_path.read_bytes()
                        resumed = True
                    else:
                        data = self._fetch_bytes_with_retries(
                            segment_url,
                            segment_retries,
                        )
                    if include_segments:
                        if segment_path is not None and (
                            overwrite or not segment_path.exists()
                        ):
                            segment_path.write_bytes(data)
                        result.segment_paths.append(str(segment_path))
                    if resumed:
                        result.resumed_segments += 1
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
            from media_metadata import probe_media_file

            result.metadata = probe_media_file(combined_path)
        return result


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Resolve or download a DASH MPD stream")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--max-bandwidth", type=int, default=None)
    parser.add_argument("--max-segments", type=int, default=1000)
    parser.add_argument("--segment-retries", type=int, default=2)
    parser.add_argument("--segments", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--combine", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--headers", default=None, help="JSON headers object")
    args = parser.parse_args(argv)
    headers = json.loads(args.headers) if args.headers else None
    client = DASHClient(headers=headers, proxy=args.proxy)
    try:
        if args.output:
            result = client.download(
                args.url,
                args.output,
                preferred_height=args.height,
                max_bandwidth=args.max_bandwidth,
                max_segments=args.max_segments,
                include_segments=args.segments,
                combine=args.combine,
                segment_retries=args.segment_retries,
            )
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        else:
            resolution = client.resolve(
                args.url,
                preferred_height=args.height,
                max_bandwidth=args.max_bandwidth,
                max_segments=args.max_segments,
            )
            print(json.dumps(resolution.to_dict(), ensure_ascii=False, indent=2))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
