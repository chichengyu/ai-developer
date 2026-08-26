"""Breadth-first deep crawler for authorized desktop automation.

The crawler discovers pages through HTML links and sitemaps, normalizes and
deduplicates URLs, stays on the configured origin(s), honors robots.txt and
rate limits, and records every page's deep analysis plus security findings.
It is designed to run without user interaction: blocked pages are classified
by `security_detector.py` and skipped or escalated according to config.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from media_session import MediaSession
from page_data_parser import PageDataAnalysis, analyze_page
from proxy_pool import ProxyPool
from scrape_guard import RobotsPolicy
from security_detector import SecurityReport, detect_security_mechanisms
from smart_fetch import create_fetch_session
from url_store import UrlDeduplicator

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}
_VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".flv", ".ts", ".m4v", ".wmv", ".mpd", ".ism"}
_AUDIO_EXTS = {".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".wma"}
_SUBTITLE_EXTS = {".vtt", ".srt", ".ass", ".ssa"}
_FILE_EXTS = {
    ".pdf",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
    ".csv",
    ".json",
    ".xml",
    ".txt",
    ".epub",
    ".mobi",
}


def _classify_asset_url(url: str) -> str | None:
    lower = url.lower()
    if ".m3u8" in lower:
        return "hls"
    if ".mpd" in lower or "format=mpd" in lower:
        return "dash"
    if ".ism/manifest" in lower or (
        "manifest" in lower and "format=mp4" in lower
    ):
        return "smooth"
    suffix = Path(urllib.parse.urlsplit(url).path).suffix.lower()
    if suffix in _IMAGE_EXTS:
        return "image"
    if suffix in _VIDEO_EXTS:
        return "video"
    if suffix in _AUDIO_EXTS:
        return "audio"
    if suffix in _SUBTITLE_EXTS:
        return "subtitle"
    if suffix in _FILE_EXTS:
        return "file"
    return None


@dataclass
class CrawlConfig:
    """Configuration for one deep crawl run."""

    seeds: list[str] = field(default_factory=list)
    max_depth: int = 2
    max_pages: int = 50
    same_host: bool = True
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    sitemap: bool = True
    respect_robots: bool = True
    skip_blocked: bool = True
    user_agent: str = "MediaPipeline/1.0"
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[dict[str, Any]] = field(default_factory=list)
    proxy: str | None = None
    proxy_pool: ProxyPool | None = None
    min_interval: float = 0.0
    jitter: float = 0.2
    max_retries: int = 0
    backoff_base: float = 0.5
    backoff_max: float = 30.0
    timeout: float = 20.0
    max_sitemap_urls: int = 1000
    fetch_backend: str = "standard"
    fetch_auto_install: bool | None = None
    fetch_browser: dict[str, Any] | None = None
    collect_param_hints: bool = True
    max_param_hints: int = 200
    crawl_api_endpoints: bool = False
    max_api_calls: int = 100
    api_max_payload_bytes: int = 262144
    block_retries: int = 2
    block_retry_delay: float = 2.0
    block_retry_backoff: float = 2.0
    rotate_proxy_on_block: bool = True
    alternate_on_block: bool = True
    browser_on_block: bool = False
    extension_skip: tuple[str, ...] = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".ico",
        ".bmp",
        ".mp4",
        ".webm",
        ".mkv",
        ".mp3",
        ".wav",
        ".flac",
        ".m3u8",
        ".zip",
        ".rar",
        ".7z",
        ".gz",
        ".tar",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".exe",
        ".msi",
        ".dmg",
        ".apk",
        ".ipa",
    )
    url_store_path: str | None = None
    jsonl_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CrawlConfig:
        values = dict(data or {})
        return cls(
            seeds=[str(item) for item in values.get("seeds") or []],
            max_depth=int(values.get("max_depth", 2)),
            max_pages=int(values.get("max_pages", 50)),
            same_host=bool(values.get("same_host", True)),
            include=[str(item) for item in values.get("include") or []],
            exclude=[str(item) for item in values.get("exclude") or []],
            sitemap=bool(values.get("sitemap", True)),
            respect_robots=bool(values.get("respect_robots", True)),
            skip_blocked=bool(values.get("skip_blocked", True)),
            user_agent=str(values.get("user_agent") or cls().user_agent),
            headers=dict(values.get("headers") or {}),
            cookies=list(values.get("cookies") or []),
            proxy=values.get("proxy"),
            proxy_pool=values.get("proxy_pool"),
            min_interval=float(values.get("min_interval", 0.0)),
            jitter=float(values.get("jitter", 0.2)),
            max_retries=int(values.get("max_retries", 0)),
            backoff_base=float(values.get("backoff_base", 0.5)),
            backoff_max=float(values.get("backoff_max", 30.0)),
            timeout=float(values.get("timeout", 20.0)),
            max_sitemap_urls=int(values.get("max_sitemap_urls", 1000)),
            fetch_backend=str(values.get("fetch_backend") or "standard"),
            fetch_auto_install=values.get("fetch_auto_install"),
            fetch_browser=dict(values["fetch_browser"]) if values.get("fetch_browser") else None,
            collect_param_hints=bool(values.get("collect_param_hints", True)),
            max_param_hints=int(values.get("max_param_hints", 200)),
            crawl_api_endpoints=bool(values.get("crawl_api_endpoints", False)),
            max_api_calls=int(values.get("max_api_calls", 100)),
            api_max_payload_bytes=int(values.get("api_max_payload_bytes", 262144)),
            block_retries=int(values.get("block_retries", 2)),
            block_retry_delay=float(values.get("block_retry_delay", 2.0)),
            block_retry_backoff=float(values.get("block_retry_backoff", 2.0)),
            rotate_proxy_on_block=bool(values.get("rotate_proxy_on_block", True)),
            alternate_on_block=bool(values.get("alternate_on_block", True)),
            browser_on_block=bool(values.get("browser_on_block", False)),
            url_store_path=values.get("url_store_path"),
            jsonl_path=values.get("jsonl_path"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "max_depth": self.max_depth,
            "max_pages": self.max_pages,
            "same_host": self.same_host,
            "include": self.include,
            "exclude": self.exclude,
            "sitemap": self.sitemap,
            "respect_robots": self.respect_robots,
            "skip_blocked": self.skip_blocked,
            "user_agent": self.user_agent,
            "headers": self.headers,
            "proxy": self.proxy,
            "min_interval": self.min_interval,
            "jitter": self.jitter,
            "max_retries": self.max_retries,
            "backoff_base": self.backoff_base,
            "backoff_max": self.backoff_max,
            "timeout": self.timeout,
            "max_sitemap_urls": self.max_sitemap_urls,
            "fetch_backend": self.fetch_backend,
            "fetch_auto_install": self.fetch_auto_install,
            "fetch_browser": self.fetch_browser,
            "collect_param_hints": self.collect_param_hints,
            "max_param_hints": self.max_param_hints,
            "crawl_api_endpoints": self.crawl_api_endpoints,
            "max_api_calls": self.max_api_calls,
            "api_max_payload_bytes": self.api_max_payload_bytes,
            "block_retries": self.block_retries,
            "block_retry_delay": self.block_retry_delay,
            "block_retry_backoff": self.block_retry_backoff,
            "rotate_proxy_on_block": self.rotate_proxy_on_block,
            "alternate_on_block": self.alternate_on_block,
            "browser_on_block": self.browser_on_block,
            "extension_skip": list(self.extension_skip),
            "url_store_path": self.url_store_path,
            "jsonl_path": self.jsonl_path,
        }


@dataclass
class CrawledResponse:
    """A fetched page/response that the crawler can classify and analyze."""

    url: str
    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


@dataclass
class CrawlPage:
    """One visited page and its analysis."""

    url: str
    depth: int
    status: int | None = None
    html: str = ""
    error: str | None = None
    skipped_reason: str | None = None
    security: SecurityReport | None = None
    analysis: PageDataAnalysis | None = None
    links: list[str] = field(default_factory=list)
    api_endpoints: list[dict[str, str]] = field(default_factory=list)
    api_params: dict[str, list[str]] = field(default_factory=dict)
    api_responses: list[dict[str, Any]] = field(default_factory=list)
    api_response_urls: list[str] = field(default_factory=list)
    recovery: list[dict[str, Any]] = field(default_factory=list)
    media: dict[str, list[str]] = field(default_factory=dict)
    assets: dict[str, list[str]] = field(default_factory=dict)
    streams: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "depth": self.depth,
            "status": self.status,
            "error": self.error,
            "skipped_reason": self.skipped_reason,
            "blocked": self.blocked,
            "security": self.security.to_dict() if self.security else None,
            "analysis": self.analysis.summary() if self.analysis else None,
            "links": self.links,
            "api_endpoints": self.api_endpoints,
            "api_params": self.api_params,
            "api_responses": self.api_responses,
            "api_response_urls": self.api_response_urls,
            "recovery": self.recovery,
            "media": self.media,
            "assets": self.assets,
            "streams": self.streams,
            "events": self.events,
        }


@dataclass
class CrawlResult:
    """Full crawl output plus a compact summary."""

    pages: list[CrawlPage]
    config: dict[str, Any] = field(default_factory=dict)
    sitemap_urls: list[str] = field(default_factory=list)
    url_store_seen: int = 0
    jsonl_lines: int = 0

    def summary(self) -> dict[str, Any]:
        ok = sum(1 for page in self.pages if not page.error and not page.blocked)
        blocked = sum(1 for page in self.pages if page.blocked)
        errors = sum(1 for page in self.pages if page.error)
        robots = sum(1 for page in self.pages if page.skipped_reason == "robots")
        api_count = sum(len(page.api_endpoints) for page in self.pages)
        param_hint_count = sum(len(page.api_params) for page in self.pages)
        api_response_count = sum(len(page.api_responses) for page in self.pages)
        api_url_count = sum(len(page.api_response_urls) for page in self.pages)
        recovery_count = sum(len(page.recovery) for page in self.pages)
        recovered = sum(
            1
            for page in self.pages
            if page.recovery and not page.blocked and not page.error
        )
        media_count = sum(len(values) for page in self.pages for values in page.media.values())
        asset_count = sum(len(values) for page in self.pages for values in page.assets.values())
        css_count = sum(len(page.assets.get("css", [])) for page in self.pages)
        js_count = sum(len(page.assets.get("js", [])) for page in self.pages)
        stream_count = sum(len(page.streams) for page in self.pages)
        event_count = sum(len(page.events) for page in self.pages)
        file_count = sum(len(page.media.get("files", [])) for page in self.pages)
        subtitle_count = sum(len(page.media.get("subtitles", [])) for page in self.pages)
        link_count = sum(len(page.links) for page in self.pages)
        security_kinds: dict[str, int] = {}
        for page in self.pages:
            if page.security is None:
                continue
            for finding in page.security.findings:
                security_kinds[finding.kind] = security_kinds.get(finding.kind, 0) + 1
        depths: dict[int, int] = {}
        for page in self.pages:
            depths[page.depth] = depths.get(page.depth, 0) + 1
        return {
            "pages_visited": len(self.pages),
            "pages_ok": ok,
            "blocked": blocked,
            "errors": errors,
            "robots_skipped": robots,
            "sitemap_urls": len(self.sitemap_urls),
            "api_endpoints": api_count,
            "param_hints": param_hint_count,
            "api_responses": api_response_count,
            "api_response_urls": api_url_count,
            "block_recoveries": recovery_count,
            "recovered_pages": recovered,
            "media_urls": media_count,
            "url_store_seen": self.url_store_seen,
            "jsonl_lines": self.jsonl_lines,
            "assets": asset_count,
            "css": css_count,
            "js": js_count,
            "streams": stream_count,
            "events": event_count,
            "files": file_count,
            "subtitles": subtitle_count,
            "links": link_count,
            "security_findings": security_kinds,
            "depths": {str(key): value for key, value in sorted(depths.items())},
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "sitemap_urls": self.sitemap_urls,
            "summary": self.summary(),
            "pages": [page.to_dict() for page in self.pages],
            "url_store_seen": self.url_store_seen,
            "jsonl_lines": self.jsonl_lines,
        }


class DeepCrawler:
    """BFS crawler with robots, sitemap, security classification, and limits."""

    def __init__(
        self,
        config: CrawlConfig,
        session: MediaSession | None = None,
        fetch_page: Callable[[str], CrawledResponse] | None = None,
        progress: Callable[[str, float, str], None] | None = None,
    ) -> None:
        self.config = config
        self.session = session
        self.fetch_page = fetch_page
        self.progress = progress
        self.seen: set[str] = set()
        self.url_store = (
            UrlDeduplicator(config.url_store_path)
            if config.url_store_path
            else None
        )
        self.url_store_seen = 0
        self._jsonl_handle = (
            open(config.jsonl_path, "a", encoding="utf-8")  # noqa: SIM115
            if config.jsonl_path
            else None
        )
        self.jsonl_lines = 0
        self.sitemap_urls: list[str] = []
        self._robots_cache: dict[str, RobotsPolicy | None] = {}
        self._robots_raw: dict[str, str] = {}
        self._seed_urls = {self._normalize_url(url, url) for url in config.seeds}
        self._seed_hosts = {self._host(url) for url in config.seeds if self._host(url)}

    def _default_session(self) -> MediaSession:
        if self.session is None:
            self.session = create_fetch_session(
                {
                    "backend": self.config.fetch_backend,
                    "auto_install": self.config.fetch_auto_install,
                    "browser": self.config.fetch_browser,
                },
                headers=self.config.headers,
                proxy=self.config.proxy,
                proxy_pool=self.config.proxy_pool,
                timeout=self.config.timeout,
                min_interval=self.config.min_interval,
                jitter=self.config.jitter,
                max_retries=self.config.max_retries,
                backoff_base=self.config.backoff_base,
                backoff_max=self.config.backoff_max,
            )
            if self.config.cookies:
                self.session.load_cookies(self.config.cookies)
        return self.session

    @staticmethod
    def _host(url: str) -> str:
        return urllib.parse.urlsplit(url).netloc.lower()

    def _normalize_url(self, url: str, base: str | None = None) -> str | None:
        if not url or url.startswith(("#", "javascript:", "mailto:", "tel:", "data:", "blob:")):
            return None
        if not url.startswith(("http://", "https://")):
            if base is None:
                return None
            url = urllib.parse.urljoin(base, url)
        parts = urllib.parse.urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            return None
        return urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, "")
        )

    def _allowed(self, url: str, *, is_seed: bool = False) -> bool:
        if is_seed:
            return True
        parts = urllib.parse.urlsplit(url)
        if self.config.same_host and self._host(url) not in self._seed_hosts:
            return False
        suffix = Path(parts.path).suffix.lower()
        if suffix in self.config.extension_skip:
            return False
        if self.config.include and not any(
            self._match(pattern, url) for pattern in self.config.include
        ):
            return False
        return not any(self._match(pattern, url) for pattern in self.config.exclude)

    @staticmethod
    def _match(pattern: str, url: str) -> bool:
        try:
            return re.search(pattern, url) is not None
        except re.error:
            return pattern in url

    def _robots_for(self, url: str) -> RobotsPolicy | None:
        if not self.config.respect_robots:
            return None
        host = self._host(url)
        if host in self._robots_cache:
            return self._robots_cache[host]
        parts = urllib.parse.urlsplit(url)
        robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        policy: RobotsPolicy | None = None
        raw = ""
        try:
            body, status, _ = self._default_session().get_bytes_with_meta(robots_url)
            if status == 200:
                raw = body.decode("utf-8", "replace")
                policy = RobotsPolicy(user_agent=self.config.user_agent)
                policy.load_text(raw)
        except Exception:
            policy = None
        self._robots_cache[host] = policy
        self._robots_raw[host] = raw
        return policy

    def _sitemap_candidates(self, seed_url: str) -> list[str]:
        candidates: list[str] = []
        parts = urllib.parse.urlsplit(seed_url)
        candidates.append(
            urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/sitemap.xml", "", ""))
        )
        policy = self._robots_for(seed_url)
        if policy is not None and policy.loaded:
            raw = self._robots_raw.get(self._host(seed_url), "")
            for match in re.finditer(r"(?im)^\s*Sitemap\s*:\s*(\S+)", raw):
                candidates.append(match.group(1).strip())
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_url(candidate, seed_url)
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _parse_sitemap(self, text: str) -> tuple[bool, list[str]]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return False, []
        locations = [element.text or "" for element in root.findall(f".//{SITEMAP_NS}loc")]
        if not locations:
            locations = [element.text or "" for element in root.findall(".//loc")]
        is_index = root.tag.endswith("sitemapindex") or root.tag == "sitemapindex"
        return is_index, [item.strip() for item in locations if item.strip()]

    def _collect_sitemap(self, sitemap_url: str, depth: int = 0) -> list[str]:
        if depth > 2 or len(self.sitemap_urls) >= self.config.max_sitemap_urls:
            return []
        found: list[str] = []
        try:
            body, status, _ = self._default_session().get_bytes_with_meta(sitemap_url)
        except Exception:
            return found
        if status != 200:
            return found
        is_index, locations = self._parse_sitemap(body.decode("utf-8", "replace"))
        if is_index:
            for location in locations:
                normalized = self._normalize_url(location, sitemap_url)
                if normalized:
                    found.extend(self._collect_sitemap(normalized, depth + 1))
        else:
            for location in locations:
                normalized = self._normalize_url(location, sitemap_url)
                if normalized is None or normalized in self.sitemap_urls:
                    continue
                self.sitemap_urls.append(normalized)
                found.append(normalized)
                if len(self.sitemap_urls) >= self.config.max_sitemap_urls:
                    break
        return found

    def _fetch(self, url: str) -> CrawledResponse:
        if self.fetch_page is not None:
            return self.fetch_page(url)
        body, status, headers = self._default_session().get_bytes_with_meta(url)
        return CrawledResponse(url=url, status=status, headers=headers, body=body)

    def _report(self, percent: float, message: str) -> None:
        if self.progress is not None:
            self.progress("crawl", percent, message)

    def _write_page_jsonl(self, page: CrawlPage) -> None:
        if self._jsonl_handle is not None:
            self._jsonl_handle.write(
                json.dumps(page.to_dict(), ensure_ascii=False) + "\n"
            )
            self.jsonl_lines += 1

    def _clean_links(self, raw_links: list[str], base_url: str) -> list[str]:
        cleaned: list[str] = []
        for raw in raw_links:
            normalized = self._normalize_url(raw, base_url)
            if normalized is not None and self._allowed(normalized) and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _crawl_page_apis(self, page: CrawlPage) -> None:
        if not self.config.crawl_api_endpoints:
            return
        from param_augmenter import extract_api_urls

        endpoint_urls = {
            str(endpoint.get("url") or "")
            for endpoint in page.api_endpoints
        }
        pending = list(page.api_endpoints)
        fetched: set[str] = set()
        calls = 0
        while pending and calls < self.config.max_api_calls:
            endpoint = pending.pop(0)
            method = str(endpoint.get("method") or "GET").upper()
            endpoint_url = str(endpoint.get("url") or "")
            if method != "GET" or not endpoint_url.startswith(("http://", "https://")):
                continue
            if endpoint_url in fetched:
                continue
            fetched.add(endpoint_url)
            calls += 1
            try:
                response = self._fetch(endpoint_url)
                body = response.body[: self.config.api_max_payload_bytes]
                text = body.decode("utf-8", "replace")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = None
                page.api_responses.append(
                    {
                        "url": endpoint_url,
                        "status": response.status,
                        "error": None,
                        "keys": list(data.keys())[:50] if isinstance(data, dict) else None,
                        "bytes": len(response.body),
                    }
                )
                if data is not None:
                    for nested in extract_api_urls(data, base_url=endpoint_url):
                        if nested in endpoint_urls or not self._allowed(nested):
                            continue
                        endpoint_urls.add(nested)
                        page.api_response_urls.append(nested)
                        nested_endpoint = {
                            "method": "GET",
                            "url": nested,
                            "source": "response-url",
                        }
                        page.api_endpoints.append(nested_endpoint)
                        pending.append(nested_endpoint)
            except Exception as exc:
                page.api_responses.append(
                    {
                        "url": endpoint_url,
                        "status": None,
                        "error": str(exc),
                        "keys": None,
                        "bytes": 0,
                    }
                )

    def _recover_blocked(
        self,
        url: str,
        response: CrawledResponse,
        report: SecurityReport,
    ) -> tuple[CrawledResponse, SecurityReport, list[dict[str, Any]]] | None:
        if not report.is_blocked or self.config.block_retries <= 0:
            return None
        recovery: list[dict[str, Any]] = []
        session = self._default_session()
        for attempt in range(1, self.config.block_retries + 1):
            wait = self.config.block_retry_delay * (
                self.config.block_retry_backoff ** (attempt - 1)
            )
            time.sleep(wait + random.uniform(0.0, min(1.0, wait * 0.1)))
            strategies: list[str] = []
            if self.config.rotate_proxy_on_block and session is not None:
                clear_pinned = getattr(session, "clear_pinned_proxy", None)
                if clear_pinned is not None:
                    clear_pinned()
                current_proxy = getattr(session, "_current_proxy", lambda: None)()
                if session.proxy_pool is not None:
                    session.proxy_pool.report_failure(current_proxy)
                strategies.append("proxy-rotate")
            rotate_backend = getattr(session, "rotate_backend", None)
            if rotate_backend is not None:
                backend = rotate_backend()
                if backend:
                    strategies.append(f"backend:{backend}")
            try:
                response = self._fetch(url)
            except urllib.error.HTTPError as exc:
                recovery.append(
                    {
                        "attempt": attempt,
                        "strategies": strategies,
                        "status": int(exc.code),
                        "error": f"HTTP {exc.code}",
                        "recovered": False,
                    }
                )
                continue
            except Exception as exc:
                recovery.append(
                    {
                        "attempt": attempt,
                        "strategies": strategies,
                        "status": None,
                        "error": str(exc),
                        "recovered": False,
                    }
                )
                continue
            html = response.body.decode("utf-8", "replace")
            report = detect_security_mechanisms(
                response.status,
                url,
                response.headers,
                html,
                html=html,
                page_url=url,
            )
            recovery.append(
                {
                    "attempt": attempt,
                    "strategies": strategies,
                    "status": response.status,
                    "error": None,
                    "recovered": not report.is_blocked,
                }
            )
            if not report.is_blocked:
                break
        if report.is_blocked and self.config.alternate_on_block:
            try:
                from alternate_access import try_alternate_access

                proxy = self.config.proxy
                if session is not None and getattr(session, "proxy_pool", None) is not None:
                    proxy = session.proxy_pool.get_proxy()
                alt = try_alternate_access(
                    url,
                    {"alternate": {"enabled": True, "max_variants": 4}},
                    proxy=proxy,
                    timeout=3.0,
                    max_variants=4,
                )
                if alt.passed:
                    body = (
                        alt.body.encode("utf-8")
                        if isinstance(alt.body, str)
                        else alt.body
                    )
                    response = CrawledResponse(
                        url=url,
                        status=alt.status,
                        headers=alt.headers,
                        body=body,
                    )
                    html = response.body.decode("utf-8", "replace")
                    report = detect_security_mechanisms(
                        response.status,
                        url,
                        response.headers,
                        html,
                        html=html,
                        page_url=url,
                    )
                    recovery.append(
                        {
                            "attempt": "alternate",
                            "strategies": ["alternate-access"],
                            "status": response.status,
                            "error": None,
                            "recovered": not report.is_blocked,
                        }
                    )
            except Exception as exc:
                recovery.append(
                    {
                        "attempt": "alternate",
                        "strategies": ["alternate-access"],
                        "status": None,
                        "error": str(exc),
                        "recovered": False,
                    }
                )
        if report.is_blocked and self.config.browser_on_block:
            try:
                from stealth_browser import solve_cloudflare_with_stealth_browser

                proxy = self.config.proxy
                if session is not None and getattr(session, "proxy_pool", None) is not None:
                    proxy = session.proxy_pool.get_proxy()
                browser_result = solve_cloudflare_with_stealth_browser(
                    url,
                    engine="auto",
                    proxy=proxy,
                    headless=True,
                    auto_install=False,
                    max_attempts=1,
                )
                if browser_result is not None and browser_result.html:
                    body = browser_result.html.encode("utf-8")
                    response = CrawledResponse(
                        url=url,
                        status=200,
                        headers={},
                        body=body,
                    )
                    html = response.body.decode("utf-8", "replace")
                    report = detect_security_mechanisms(
                        response.status,
                        url,
                        response.headers,
                        html,
                        html=html,
                        page_url=url,
                    )
                    recovery.append(
                        {
                            "attempt": "browser",
                            "strategies": ["browser-escalation"],
                            "status": response.status,
                            "error": None,
                            "recovered": not report.is_blocked,
                        }
                    )
            except Exception as exc:
                recovery.append(
                    {
                        "attempt": "browser",
                        "strategies": ["browser-escalation"],
                        "status": None,
                        "error": str(exc),
                        "recovered": False,
                    }
                )
        return response, report, recovery

    def crawl(self) -> CrawlResult:
        queue: deque[tuple[str, int]] = deque()
        for seed in self.config.seeds:
            normalized = self._normalize_url(seed, seed)
            if normalized is None:
                continue
            queue.append((normalized, 0))
            self.seen.add(normalized)

        if self.config.sitemap:
            for seed in self.config.seeds:
                for sitemap_url in self._sitemap_candidates(seed):
                    for found in self._collect_sitemap(sitemap_url):
                        if found not in self.seen and self._allowed(found):
                            self.seen.add(found)
                            queue.append((found, 1))

        pages: list[CrawlPage] = []
        while queue and len(pages) < self.config.max_pages:
            url, depth = queue.popleft()
            is_seed = url in self._seed_urls
            if not self._allowed(url, is_seed=is_seed):
                continue

            policy = self._robots_for(url)
            if policy is not None and policy.loaded and not policy.can_fetch(url):
                skipped_page = CrawlPage(
                    url=url,
                    depth=depth,
                    skipped_reason="robots",
                    status=403,
                )
                pages.append(skipped_page)
                self._write_page_jsonl(skipped_page)
                self._report(len(pages) / self.config.max_pages, f"robots denied: {url}")
                continue

            try:
                response = self._fetch(url)
            except urllib.error.HTTPError as exc:
                body = exc.read() if hasattr(exc, "read") else b""
                response = CrawledResponse(
                    url=url,
                    status=int(exc.code),
                    headers=dict(exc.headers.items()) if exc.headers else {},
                    body=body,
                )
            except Exception as exc:
                error_page = CrawlPage(url=url, depth=depth, error=str(exc))
                pages.append(error_page)
                self._write_page_jsonl(error_page)
                self._report(len(pages) / self.config.max_pages, f"fetch error: {url}")
                continue

            html = response.body.decode("utf-8", "replace")
            report = detect_security_mechanisms(
                response.status,
                url,
                response.headers,
                html,
                html=html,
                page_url=url,
            )
            recovery: list[dict[str, Any]] = []
            if report.is_blocked:
                recovered = self._recover_blocked(url, response, report)
                if recovered is not None:
                    response, report, recovery = recovered
                    html = response.body.decode("utf-8", "replace")
            page = CrawlPage(
                url=url,
                depth=depth,
                status=response.status,
                html=html,
                security=report,
                blocked=report.is_blocked,
                recovery=recovery,
            )
            if report.is_blocked and self.config.skip_blocked:
                pages.append(page)
                self._write_page_jsonl(page)
                self._report(
                    len(pages) / self.config.max_pages,
                    f"blocked ({report.primary_kind}): {url}",
                )
                continue

            analysis = analyze_page(html, base_url=url)
            page.analysis = analysis
            page.links = self._clean_links(list(analysis.media.links), url)
            page.api_endpoints = [item.to_dict() for item in analysis.api_endpoints]
            if self.config.collect_param_hints:
                from param_augmenter import collect_page_param_hints

                page.api_params = collect_page_param_hints(
                    url,
                    analysis,
                    links=list(analysis.media.links),
                    max_values=self.config.max_param_hints,
                    max_keys=self.config.max_param_hints,
                )
            self._crawl_page_apis(page)
            asset_files: list[str] = []
            subtitles: list[str] = []
            for link_url in analysis.media.links:
                asset_kind = _classify_asset_url(link_url)
                if asset_kind == "subtitle":
                    subtitles.append(link_url)
                elif asset_kind == "file":
                    asset_files.append(link_url)
            page.media = {
                "videos": analysis.media.videos,
                "audios": analysis.media.audios,
                "images": analysis.media.images,
                "hls": analysis.media.hls,
                "dash": analysis.media.dash,
                "smooth": analysis.media.smooth,
                "subtitles": subtitles,
                "files": asset_files,
                "links": analysis.media.links,
            }
            page.assets = analysis.assets
            page.streams = list(analysis.streams)
            page.events = list(analysis.events)
            pages.append(page)
            self._write_page_jsonl(page)

            if depth < self.config.max_depth:
                for link in page.links:
                    if len(pages) + len(queue) >= self.config.max_pages:
                        break
                    if link not in self.seen:
                        self.seen.add(link)
                        queue.append((link, depth + 1))
            self._report(
                len(pages) / self.config.max_pages,
                f"crawled {len(pages)}/{self.config.max_pages}: {url}",
            )

        if self.url_store is not None:
            discovered: list[str] = []
            for page in pages:
                discovered.append(page.url)
                discovered.extend(page.links)
                for values in page.media.values():
                    discovered.extend(values)
                for values in page.assets.values():
                    discovered.extend(values)
                for stream in page.streams:
                    stream_url = str(stream.get("url") or "")
                    if stream_url:
                        discovered.append(stream_url)
            self.url_store.add_many(discovered)
            checkpoint = self.url_store.checkpoint()
            self.url_store_seen = int(checkpoint.get("seen_urls") or 0)
            self.url_store.close()
            self.url_store = None

        if self._jsonl_handle is not None:
            self._jsonl_handle.close()
            self._jsonl_handle = None

        return CrawlResult(
            pages=pages,
            config=self.config.to_dict(),
            sitemap_urls=list(self.sitemap_urls),
            url_store_seen=self.url_store_seen,
            jsonl_lines=self.jsonl_lines,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deep-crawl pages via links and sitemaps with auto security handling."
    )
    parser.add_argument("--seed", action="append", required=True, help="seed URL (repeatable)")
    parser.add_argument("--max-depth", type=int, default=2)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--include", action="append", default=[], help="regex include pattern")
    parser.add_argument("--exclude", action="append", default=[], help="regex exclude pattern")
    parser.add_argument("--no-sitemap", action="store_true", help="disable sitemap discovery")
    parser.add_argument("--no-robots", action="store_true", help="disable robots.txt checks")
    parser.add_argument(
        "--no-skip-blocked",
        action="store_true",
        help="record blocked pages as visited instead of skipping children",
    )
    parser.add_argument("--output", default=None, help="write crawl JSON to a file")
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--min-interval", type=float, default=0.0)
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument(
        "--fetch-backend",
        default="standard",
        help="standard or auto (curl_cffi -> cloudscraper -> httpx -> urllib)",
    )
    parser.add_argument(
        "--auto-install",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="auto-install missing optional web-fetch packages (default: auto mode installs)",
    )
    parser.add_argument(
        "--crawl-api",
        action="store_true",
        help="fetch discovered API endpoints during the crawl and discover nested API URLs",
    )
    parser.add_argument("--max-api-calls", type=int, default=100)
    args = parser.parse_args(argv)

    config = CrawlConfig(
        seeds=args.seed,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        include=args.include,
        exclude=args.exclude,
        sitemap=not args.no_sitemap,
        respect_robots=not args.no_robots,
        skip_blocked=not args.no_skip_blocked,
        proxy=args.proxy,
        min_interval=args.min_interval,
        max_retries=args.max_retries,
        fetch_backend=args.fetch_backend,
        fetch_auto_install=args.auto_install,
        crawl_api_endpoints=args.crawl_api,
        max_api_calls=args.max_api_calls,
    )
    result = DeepCrawler(config).crawl()
    text = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
