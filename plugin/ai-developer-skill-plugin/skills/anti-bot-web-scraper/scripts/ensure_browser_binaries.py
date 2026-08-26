"""Chunked downloader for large browser binaries and Camoufox add-ons."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

ProgressFn = Callable[[str, float | None, str], None]

_DEFAULT_CHUNK_MB = 8
_USER_AGENT = "anti-bot-web-scraper/1.0"
_DEFAULT_MIRRORS = (
    "https://gh-proxy.com/",
    "https://ghfast.top/",
    "https://ghproxy.net/",
)


def _noop_progress(stage: str, percent: float | None, message: str) -> None:
    print(f"[{stage}] {percent or 0:.0%} {message}", flush=True)


def _request_headers(url: str) -> tuple[dict[str, str], int]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return {str(key).lower(): str(value) for key, value in response.headers.items()}, int(
                getattr(response, "status", 200)
            )
    except urllib.error.HTTPError as exc:
        return {str(key).lower(): str(value) for key, value in exc.headers.items()}, int(
            getattr(exc, "code", 0)
        )


def _candidate_urls(url: str) -> list[str]:
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1", "0.0.0.0"}:
        return [url]
    mirrors = [
        str(item).strip().rstrip("/") + "/" + url
        for item in os.environ.get("CAMOUFOX_MIRRORS", "").split(",")
        if str(item).strip()
    ]
    mirrors.extend(f"{mirror}{url}" for mirror in _DEFAULT_MIRRORS)
    mirrors.append(url)
    return mirrors


def _curl_download_range(
    url: str,
    start: int,
    end: int,
    output: Path,
    *,
    timeout: float = 300.0,
) -> bool:
    curl = shutil.which("curl")
    if not curl:
        return False
    result = subprocess.run(
        [
            curl,
            "-L",
            "-s",
            "--max-time",
            str(int(timeout)),
            "-r",
            f"{start}-{end}",
            "-o",
            str(output),
            url,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not output.exists() or output.stat().st_size <= 0:
        return False
    expected = end - start + 1
    return output.stat().st_size == expected


def _urllib_download_range(
    url: str,
    start: int,
    end: int,
    output: Path,
    *,
    timeout: float = 300.0,
) -> bool:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": _USER_AGENT,
                "Range": f"bytes={start}-{end}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as response, output.open("wb") as handle:
            handle.write(response.read())
        return output.stat().st_size == end - start + 1
    except Exception:
        return False


def _download_chunk(
    url: str,
    start: int,
    end: int,
    output: Path,
    *,
    timeout: float = 300.0,
) -> bool:
    for candidate in _candidate_urls(url):
        if _curl_download_range(
            candidate,
            start,
            end,
            output,
            timeout=timeout,
        ) or _urllib_download_range(
            candidate,
            start,
            end,
            output,
            timeout=timeout,
        ):
            return True
    return False


def chunked_download(
    url: str,
    buffer: Any,
    *,
    chunk_size: int = _DEFAULT_CHUNK_MB * 1024 * 1024,
    max_retries: int = 3,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Any:
    """Download a URL into an open binary buffer using parallel Range chunks."""
    headers, _ = _request_headers(url)
    total = int(headers.get("content-length") or 0)
    supports_range = headers.get("accept-ranges", "").lower() == "bytes" or total > 0
    downloaded = 0
    download_lock = threading.Lock()

    def report() -> None:
        if progress_callback is not None:
            progress_callback(downloaded, total)

    if not supports_range or total <= 0:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as response:
            while True:
                data = response.read(chunk_size)
                if not data:
                    break
                buffer.write(data)
                downloaded += len(data)
                report()
        buffer.seek(0)
        return buffer

    ranges = []
    start = 0
    while start < total:
        end = min(start + chunk_size - 1, total - 1)
        ranges.append((start, end))
        start = end + 1

    def report_delta(delta: int) -> None:
        nonlocal downloaded
        with download_lock:
            downloaded += delta
            report()

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        workers = max(1, min(8, len(ranges)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for index, (start, end) in enumerate(ranges):
                part = tmp_path / f"part-{index:05d}.bin"
                futures[pool.submit(_download_chunk, url, start, end, part)] = (
                    index,
                    part,
                    start,
                    end,
                )
            for future in as_completed(futures):
                index, part, start, end = futures[future]
                try:
                    ok = future.result()
                except Exception:
                    ok = False
                if not ok:
                    raise RuntimeError(f"failed to download bytes {start}-{end} from {url}")
                with part.open("rb") as handle:
                    data = handle.read()
                buffer.seek(start)
                buffer.write(data)
                report_delta(len(data))
    buffer.seek(0)
    return buffer


def chunked_webdl(
    url: str,
    desc: str | None = None,
    buffer: Any | None = None,
    bar: bool = True,
    progress_callback: Callable[[int, int], None] | None = None,
) -> Any:
    """Drop-in replacement for camoufox.pkgman.webdl with Range chunks."""
    if buffer is None:
        buffer = io.BytesIO()
    chunked_download(url, buffer, progress_callback=progress_callback)
    return buffer


def camoufox_installed() -> bool:
    try:
        from camoufox.pkgman import camoufox_path

        camoufox_path(download_if_missing=False)
        return True
    except Exception:
        return False


def ensure_camoufox(
    progress: ProgressFn | None = None,
    chunk_size_mb: int = _DEFAULT_CHUNK_MB,
) -> bool:
    report = progress or _noop_progress
    if camoufox_installed():
        report("camoufox", 1.0, "Camoufox browser already installed")
        return True
    try:
        import camoufox.pkgman as pkgman
        from camoufox.pkgman import CamoufoxFetcher, RepoConfig
    except Exception as exc:
        report("camoufox", None, f"Camoufox package unavailable: {exc}")
        return False

    pkgman.webdl = chunked_webdl
    report("camoufox", 0.05, "resolving Camoufox release")
    fetcher = CamoufoxFetcher(repo_config=RepoConfig.get_default())
    fetcher.download_file = lambda buffer, url: chunked_download(
        url,
        buffer,
        chunk_size=max(1, int(chunk_size_mb)) * 1024 * 1024,
        progress_callback=lambda done, total: report(
            "camoufox",
            done / total if total else None,
            f"chunked download {done / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB",
        ),
    )
    report("camoufox", 0.1, f"installing {fetcher.verstr} with chunked download")
    fetcher.install()
    ok = camoufox_installed()
    report("camoufox", 1.0, "Camoufox browser installed")
    return ok


def status() -> dict[str, Any]:
    return {
        "camoufox_browser": camoufox_installed(),
        "chunk_size_mb": _DEFAULT_CHUNK_MB,
        "range_resume": True,
    }


def ensure(
    install: bool = True,
    progress: ProgressFn | None = None,
    chunk_size_mb: int = _DEFAULT_CHUNK_MB,
) -> dict[str, Any]:
    report = progress or _noop_progress
    if not install:
        return status()
    report("binaries", 0.0, "checking large browser binaries")
    ensure_camoufox(report, chunk_size_mb=chunk_size_mb)
    return status()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install large browser binaries with chunked downloads")
    parser.add_argument("--check", action="store_true", help="only report status")
    parser.add_argument("--chunk-size-mb", type=int, default=_DEFAULT_CHUNK_MB)
    args = parser.parse_args(argv)
    result = ensure(install=not args.check, chunk_size_mb=args.chunk_size_mb)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("camoufox_browser") or args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
