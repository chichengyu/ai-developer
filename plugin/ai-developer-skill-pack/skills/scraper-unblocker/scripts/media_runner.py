#!/usr/bin/env python3
"""Deep media crawler: discover media pages, classify assets by name, and download.

Discovery starts from a sitemap when available, then analyzes player/detail
pages for drama names and media URLs. Direct image/video/audio files can be
downloaded; unencrypted HLS manifests can be merged with ffmpeg. Encrypted or
access-controlled streams are logged and skipped.
"""

from __future__ import annotations

import argparse
import html as html_module
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

from media_probe import analyze_page, classify_url
from scraper_probe import (
    DEFAULT_USER_AGENT,
    build_opener,
    fetch,
    load_cookie_header,
    parse_headers,
    robots_allowed,
)

PLAYER_PATH = re.compile(r"/(player|play|video|detail|drama|vod|show|episode|watch)/", re.I)


class MediaState:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.robots_cache: Dict[str, str] = {}
        self.cache_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.last_request = 0.0

    def throttle(self) -> None:
        with self.rate_lock:
            now = time.monotonic()
            wait_for = self.args.delay - (now - self.last_request)
            if wait_for > 0:
                time.sleep(wait_for)
            self.last_request = time.monotonic()

    def robots_allowed_for(self, url: str) -> bool:
        if self.args.no_robots:
            return True
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        with self.cache_lock:
            text = self.robots_cache.get(origin)
        if text is None:
            self.throttle()
            response = fetch(
                origin + "/robots.txt",
                self.args.user_agent,
                self.args.timeout,
                self.args.proxy,
                50_000,
                extra_headers=self.args.extra_headers,
                cookie=self.args.cookie,
            )
            text = response["body_text"] if response["status"] == 200 else ""
            with self.cache_lock:
                self.robots_cache[origin] = text
        return robots_allowed(url, self.args.user_agent, text)[0]


def sanitize_name(name: str, max_len: int = 80) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return cleaned[:max_len] or "untitled"


def parse_sitemap_locs(xml_text: str) -> List[str]:
    urls: List[str] = []
    try:
        root = ET.fromstring(xml_text)
        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
        for loc in root.iter(namespace + "loc"):
            if loc.text:
                urls.append(loc.text.strip())
        if not urls:
            for loc in root.iter("loc"):
                if loc.text:
                    urls.append(loc.text.strip())
    except ET.ParseError:
        pass
    if not urls:
        pattern = re.compile(r"<loc[^>]*>(.*?)</loc>", re.I | re.S)
        urls = [
            html_module.unescape(match.group(1)).strip()
            for match in pattern.finditer(xml_text)
        ]
    return list(dict.fromkeys(urls))


def fetch_sitemap_urls(
    sitemap_url: str,
    state: MediaState,
    depth: int = 0,
    max_depth: int = 2,
    seen: Optional[Set[str]] = None,
) -> List[str]:
    if seen is None:
        seen = set()
    if depth > max_depth or sitemap_url in seen:
        return []
    seen.add(sitemap_url)
    state.throttle()
    response = fetch(
        sitemap_url,
        state.args.user_agent,
        state.args.timeout,
        state.args.proxy,
        state.args.max_sitemap_bytes,
        extra_headers=state.args.extra_headers,
        cookie=state.args.cookie,
    )
    if response["status"] != 200 or response["error"]:
        return []
    results: List[str] = []
    for loc in parse_sitemap_locs(response["body_text"]):
        path = urlparse(loc).path.lower()
        if loc.endswith(".xml") or "sitemap" in path:
            results.extend(
                fetch_sitemap_urls(loc, state, depth + 1, max_depth, seen)
            )
        else:
            results.append(loc)
    return list(dict.fromkeys(results))


def is_player_url(url: str) -> bool:
    return bool(PLAYER_PATH.search(urlparse(url).path))


def discover_candidates(state: MediaState, seed: str) -> List[str]:
    parsed = urlparse(seed)
    if seed.endswith(".xml") or "sitemap" in parsed.path.lower():
        return fetch_sitemap_urls(seed, state)
    page = analyze_page(
        seed,
        state.args.user_agent,
        state.args.timeout,
        state.args.proxy,
        state.args.max_body_bytes,
        extra_headers=state.args.extra_headers,
        cookie=state.args.cookie,
    )
    candidates = [seed]
    if not page["block_signals"] and not page["error"]:
        candidates.extend(link for link in page["links"] if is_player_url(link))
    return list(dict.fromkeys(candidates))


def analyze_worker(state: MediaState, url: str) -> Dict[str, Any]:
    state.throttle()
    if not state.robots_allowed_for(url):
        return {
            "url": url,
            "status": None,
            "error": "blocked by robots.txt",
            "best_drama_name": "",
            "media": [],
            "block_signals": [],
        }
    return analyze_page(
        url,
        state.args.user_agent,
        state.args.timeout,
        state.args.proxy,
        state.args.max_body_bytes,
        extra_headers=state.args.extra_headers,
        cookie=state.args.cookie,
    )


def crawl_pages(state: MediaState, candidates: List[str]) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=state.args.concurrency) as pool:
        futures = {
            pool.submit(analyze_worker, state, url): url
            for url in candidates[: state.args.max_pages]
        }
        while futures:
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                pages.append(future.result())
    return pages


def normalize_modes(raw_mode: str) -> set[str]:
    tokens = {token.strip().lower() for token in raw_mode.split(",") if token.strip()}
    if not tokens or "all" in tokens:
        return {"image", "video", "audio", "manifest"}
    modes: set[str] = set()
    if "images" in tokens or "image" in tokens:
        modes.add("image")
    if "videos" in tokens or "video" in tokens:
        modes.add("video")
        modes.add("manifest")
    if "audio" in tokens:
        modes.add("audio")
    if "manifest" in tokens:
        modes.add("manifest")
    if not modes:
        raise SystemExit("--mode must be all, images, videos, audio, or comma-separated values")
    return modes


def build_media_records(
    pages: List[Dict[str, Any]], modes: set[str]
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for page in pages:
        drama = page.get("best_drama_name") or "untitled"
        for item in page.get("media", []):
            kind = item.get("kind", "unknown")
            if kind == "unknown" or kind not in modes:
                continue
            records.append(
                {
                    "drama": drama,
                    "page_url": page.get("url"),
                    "final_url": page.get("final_url"),
                    "kind": kind,
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "text": item.get("text"),
                    "status": page.get("status"),
                    "error": page.get("error"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    return records


def write_index(records: List[Dict[str, Any]], output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    index_path = os.path.join(output_dir, "media_index.jsonl")
    with open(index_path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return index_path


def extension_for(url: str, content_type: str = "") -> str:
    path = urlparse(url).path.lower()
    match = re.search(r"\.([a-z0-9]{2,5})$", path)
    if match:
        return "." + match.group(1)
    mime_ext = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
    }
    for mime, ext in mime_ext.items():
        if content_type.lower().startswith(mime):
            return ext
    return ".bin"


def download_file(url: str, dest: str, state: MediaState) -> str:
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    opener = build_opener(state.args.proxy)
    headers = {
        "User-Agent": state.args.user_agent,
        "Accept": "image/*,video/*,audio/*,*/*;q=0.8",
    }
    if state.args.cookie:
        headers["Cookie"] = state.args.cookie
    if state.args.extra_headers:
        headers.update(state.args.extra_headers)
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    try:
        state.throttle()
        with opener.open(request, timeout=state.args.timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            if response.status != 200 or content_type.startswith("text/html"):
                return "skipped"
            if not os.path.exists(dest) or os.path.getsize(dest) == 0:
                with open(dest, "wb") as handle:
                    shutil.copyfileobj(response, handle)
        return "saved"
    except Exception as exc:
        return f"error: {type(exc).__name__}: {exc}"


def download_manifest(record: Dict[str, Any], state: MediaState) -> str:
    state.throttle()
    response = fetch(
        record["url"],
        state.args.user_agent,
        state.args.timeout,
        state.args.proxy,
        500_000,
        extra_headers=state.args.extra_headers,
        cookie=state.args.cookie,
    )
    if response["error"] or response["status"] != 200:
        return "error: manifest fetch failed"
    if re.search(r"#EXT-X(?:-SESSION)?-KEY:METHOD=AES", response["body_text"], re.I):
        return "protected"
    dest_dir = os.path.join(
        state.args.output_dir, sanitize_name(record["drama"]), "videos"
    )
    os.makedirs(dest_dir, exist_ok=True)
    digest = hashlib.sha1(record["url"].encode("utf-8")).hexdigest()[:10]
    dest = os.path.join(dest_dir, digest + ".mp4")
    state.throttle()
    result = subprocess.run(
        [
            state.args.ffmpeg,
            "-y",
            "-i",
            record["url"],
            "-c",
            "copy",
            dest,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode == 0 and os.path.exists(dest):
        return "saved"
    return f"error: ffmpeg rc={result.returncode}"


def download_records(
    records: List[Dict[str, Any]], state: MediaState
) -> Dict[str, int]:
    counts = {"saved": 0, "skipped": 0, "protected": 0, "error": 0}
    seen: Set[str] = set()
    for record in records:
        url = record["url"]
        if url in seen:
            continue
        seen.add(url)
        if record["kind"] == "manifest":
            if not state.args.ffmpeg:
                counts["skipped"] += 1
                continue
            outcome = download_manifest(record, state)
        elif record["kind"] in ("image", "video", "audio"):
            digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
            filename = digest + extension_for(url)
            dest = os.path.join(
                state.args.output_dir,
                sanitize_name(record["drama"]),
                record["kind"],
                filename,
            )
            outcome = download_file(url, dest, state)
        else:
            outcome = "skipped"
        key = "protected" if outcome == "protected" else "error"
        if outcome == "saved":
            counts["saved"] += 1
        elif outcome == "skipped":
            counts["skipped"] += 1
        else:
            counts[key] += 1
    return counts


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deep media crawler with sitemap discovery and drama-name classification."
    )
    parser.add_argument("--seed", required=True, help="Sitemap URL or starting page.")
    parser.add_argument(
        "--mode",
        default="all",
        help="Media kinds: all, images, videos, audio, or comma-separated values.",
    )
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--proxy", default=None)
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="Extra request header; repeatable.",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help="Cookie header for an authorized session you already hold.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="JSON session file from session_capture.py or browser storage state.",
    )
    parser.add_argument("--max-body-bytes", type=int, default=1_000_000)
    parser.add_argument("--max-sitemap-bytes", type=int, default=20_000_000)
    parser.add_argument("--output-dir", default="media_crawl")
    parser.add_argument("--download", action="store_true", help="Download direct media assets.")
    parser.add_argument("--ffmpeg", default=None, help="Path to ffmpeg for HLS manifests.")
    parser.add_argument("--no-robots", action="store_true")
    args = parser.parse_args(argv)

    if args.concurrency < 1 or args.max_pages < 1 or args.delay < 0:
        parser.error("concurrency >= 1, max-pages >= 1, delay >= 0")

    args.extra_headers = parse_headers(args.header)
    args.cookie = args.cookie or load_cookie_header(args.cookies_file)
    modes = normalize_modes(args.mode)
    state = MediaState(args)
    print("Discovering candidate pages from:", args.seed)
    candidates = discover_candidates(state, args.seed)
    print("Candidates:", len(candidates))
    if not candidates:
        print("No candidate pages found.")
        return 1

    pages = crawl_pages(state, candidates)
    records = build_media_records(pages, modes)
    index_path = write_index(records, args.output_dir)
    print(f"Media records: {len(records)} -> {index_path}")

    drama_counts: Dict[str, int] = {}
    for record in records:
        drama_counts[record["drama"]] = drama_counts.get(record["drama"], 0) + 1
    for drama, count in sorted(drama_counts.items())[:20]:
        print(f"  {drama}: {count}")

    if args.download:
        counts = download_records(records, state)
        print("Download summary:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
