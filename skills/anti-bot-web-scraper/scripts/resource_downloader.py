"""Streaming, resumable resource downloader with integrity verification.

Downloads large media through HTTP Range requests when the server supports
them, appends to an existing partial file, and verifies SHA-256 when the
caller supplies an expected hash. Works with `MediaSession` / smart fetch
sessions so proxy rotation and anti-bot backends apply to media too.
"""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from media_session import MediaSession

DEFAULT_CHUNK_SIZE = 1024 * 1024

_CONTENT_TYPE_SUFFIX = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "video/x-msvideo": ".avi",
    "video/x-flv": ".flv",
    "video/mp2t": ".ts",
    "video/x-m4v": ".m4v",
    "video/x-ms-wmv": ".wmv",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/avif": ".avif",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
}


@dataclass
class ResourceDownloadResult:
    url: str
    path: str | None = None
    size: int = 0
    sha256: str | None = None
    status: int | None = None
    content_type: str | None = None
    resumed: bool = False
    skipped: bool = False
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "status": self.status,
            "content_type": self.content_type,
            "resumed": self.resumed,
            "skipped": self.skipped,
            "error": self.error,
            "details": self.details,
}


def _content_type_suffix(content_type: str | None) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    return _CONTENT_TYPE_SUFFIX.get(normalized, "")


def _safe_filename(value: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip() or "resource.bin"


def _classify_url(url: str) -> str:
    lower = url.lower()
    if ".m3u8" in lower:
        return "hls"
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}:
        return "image"
    if suffix in {".mp4", ".webm", ".mov", ".mkv", ".avi", ".flv", ".ts", ".m4v", ".wmv"}:
        return "video"
    if suffix in {".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".wma"}:
        return "audio"
    return "resource"


class ResourceDownloader:
    """Download one resource with streaming, resume, and hash verification."""

    def __init__(
        self,
        session: MediaSession,
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        timeout: float = 30.0,
    ) -> None:
        self.session = session
        self.chunk_size = max(4096, int(chunk_size))
        self.timeout = timeout

    def download(
        self,
        url: str,
        output_dir: str | Path,
        *,
        filename: str | None = None,
        expected_sha256: str | None = None,
        overwrite: bool = False,
        resume: bool = True,
    ) -> ResourceDownloadResult:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        probe = self.session.head(url)
        total_size = probe.total_size
        content_type = probe.content_type
        kind = _classify_url(url)
        safe_name = _safe_filename(filename or probe.filename or urllib.parse.urlsplit(url).path.rsplit("/", 1)[-1] or "resource")
        if not Path(safe_name).suffix:
            safe_name = f"{safe_name}{_content_type_suffix(content_type)}"
        target = out / safe_name
        if target.exists() and not overwrite:
            existing_size = target.stat().st_size
            if total_size is not None and existing_size == total_size:
                return ResourceDownloadResult(
                    url=url,
                    path=str(target),
                    size=existing_size,
                    status=probe.status,
                    content_type=content_type,
                    skipped=True,
                    details={"kind": kind},
                )
        start = target.stat().st_size if resume and target.exists() else 0
        if start and total_size is not None and start >= total_size:
            start = 0
        resumed = start > 0
        try:
            if start:
                response = self.session.open(
                    url,
                    headers={"Range": f"bytes={start}-"},
                    timeout=self.timeout,
                )
            else:
                response = self.session.open(url, timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and start:
                start = 0
                resumed = False
                response = self.session.open(url, timeout=self.timeout)
            else:
                return ResourceDownloadResult(
                    url=url,
                    status=int(exc.code),
                    error=str(exc),
                    details={"kind": kind},
                )
        status = int(getattr(response, "status", getattr(response, "code", 200)))
        if status == 206 and start:
            resumed = True
        elif status == 200 and start:
            start = 0
            resumed = False
        digest = hashlib.sha256()
        try:
            mode = "ab" if start else "wb"
            with target.open(mode) as handle:
                while True:
                    chunk = response.read(self.chunk_size)
                    if not chunk:
                        break
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception as exc:
            return ResourceDownloadResult(
                url=url,
                path=str(target),
                status=status,
                resumed=resumed,
                error=str(exc),
                details={"kind": kind},
            )
        finally:
            with suppress(Exception):
                response.close()
        sha256 = digest.hexdigest()
        if expected_sha256 and sha256.lower() != expected_sha256.lower():
            return ResourceDownloadResult(
                url=url,
                path=str(target),
                status=status,
                resumed=resumed,
                error="SHA-256 mismatch",
                details={"expected": expected_sha256, "actual": sha256, "kind": kind},
            )
        return ResourceDownloadResult(
            url=url,
            path=str(target),
            size=target.stat().st_size,
            sha256=sha256,
            status=status,
            content_type=content_type,
            resumed=resumed,
            details={"kind": kind},
        )
if __name__ == "__main__":
    print("resource_downloader: streaming/resumable downloader")
