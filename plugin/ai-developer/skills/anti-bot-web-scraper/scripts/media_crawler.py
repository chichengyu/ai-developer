"""Concurrent media crawler with incremental JSONL output and resume.

The crawler walks same-host pages via links/sitemaps, applies robots.txt and
rate limits, classifies blocks with `block_diagnoser.py`, escalates blocked
pages through proxy rotation / stealth browsers when enabled, and downloads
images, videos, audio, and HLS streams into a stable output layout.

Every page and media result is appended to JSONL as it finishes, so the
crawler can be stopped and resumed later without re-downloading completed
work.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alternate_access import try_alternate_access
from block_diagnoser import diagnose_response
from media_parser import normalize_url
from media_session import MediaSession, guess_filename
from page_data_parser import analyze_page
from proxy_pool import ProxyPool
from resource_store import ResourceStore
from scrape_guard import RateLimiter, RobotsPolicy
from smart_fetch import create_fetch_session

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico"}
_VIDEO_EXTS = {
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
    ".flv",
    ".ts",
    ".m4v",
    ".wmv",
    ".mpd",
    ".ism",
}
_AUDIO_EXTS = {".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".wma"}
_ASSET_EXTS = (
    _IMAGE_EXTS
    | _VIDEO_EXTS
    | _AUDIO_EXTS
    | {
        ".vtt",
        ".srt",
        ".ass",
        ".ssa",
        ".css",
        ".js",
        ".mjs",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
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
)
_DOCUMENT_EXTS = {
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
    ".epub",
    ".mobi",
}
_DATA_EXTS = {".json", ".xml", ".csv", ".txt"}
_FONT_EXTS = {".woff", ".woff2", ".ttf", ".otf", ".eot"}
_SUBTITLE_EXTS = {".vtt", ".srt", ".ass", ".ssa"}


@dataclass
class MediaCrawlConfig:
    """Configuration for one concurrent media crawl."""

    seeds: list[str] = field(default_factory=list)
    max_pages: int = 100
    max_depth: int = 3
    same_host: bool = True
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    respect_robots: bool = True
    sitemap: bool = True
    max_workers: int = 4
    min_interval: float = 0.5
    jitter: float = 0.2
    max_retries: int = 3
    backoff_base: float = 0.5
    backoff_max: float = 30.0
    timeout: float = 20.0
    user_agent: str = "MediaCrawler/1.0"
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[dict[str, Any]] = field(default_factory=list)
    proxy: str | None = None
    proxy_config: Any = None
    fetch_backend: str = "auto"
    fetch_auto_install: bool = False
    browser_config: dict[str, Any] | None = None
    media_types: tuple[str, ...] = (
        "image",
        "video",
        "audio",
        "hls",
        "dash",
        "smooth",
        "subtitle",
        "file",
        "css",
        "js",
        "font",
        "data",
    )
    download_media: bool = True
    auto_adjust_max_pages: bool = False
    max_pages_cap: int = 1000
    output_dir: str = "media"
    jsonl_path: str | None = None
    resource_db_path: str | None = None
    resume: bool = True
    max_media_workers: int = 4
    min_media_interval: float = 0.2
    max_media_per_page: int = 200
    preferred_height: int | None = None
    max_bandwidth: int | None = None
    overwrite: bool = False
    resume_downloads: bool = True
    escalate_blocked: bool = True
    retry_blocked: bool = True
    max_sitemap_urls: int = 1000
    proxy_health_check: bool = False
    proxy_health_url: str = "https://example.com"
    summary_output: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MediaCrawlConfig:
        values = dict(data or {})
        media_types = tuple(
            values.get("media_types")
            or (
                "image",
                "video",
                "audio",
                "hls",
                "dash",
                "smooth",
                "subtitle",
                "file",
                "css",
                "js",
                "font",
                "data",
            )
        )
        return cls(
            seeds=[str(item) for item in values.get("seeds") or []],
            max_pages=int(values.get("max_pages", 100)),
            max_depth=int(values.get("max_depth", 3)),
            same_host=bool(values.get("same_host", True)),
            include=[str(item) for item in values.get("include") or []],
            exclude=[str(item) for item in values.get("exclude") or []],
            respect_robots=bool(values.get("respect_robots", True)),
            sitemap=bool(values.get("sitemap", True)),
            max_workers=max(1, int(values.get("max_workers", 4))),
            min_interval=float(values.get("min_interval", 0.5)),
            jitter=float(values.get("jitter", 0.2)),
            max_retries=int(values.get("max_retries", 3)),
            backoff_base=float(values.get("backoff_base", 0.5)),
            backoff_max=float(values.get("backoff_max", 30.0)),
            timeout=float(values.get("timeout", 20.0)),
            user_agent=str(values.get("user_agent") or cls().user_agent),
            headers=dict(values.get("headers") or {}),
            cookies=list(values.get("cookies") or []),
            proxy=values.get("proxy"),
            proxy_config=values.get("proxy_pool") or values.get("proxies"),
            fetch_backend=str(values.get("fetch_backend") or "auto"),
            fetch_auto_install=bool(values.get("fetch_auto_install", False)),
            browser_config=dict(values["browser"]) if values.get("browser") else None,
            media_types=media_types,
            download_media=bool(values.get("download_media", True)),
            auto_adjust_max_pages=bool(values.get("auto_adjust_max_pages", False)),
            max_pages_cap=max(1, int(values.get("max_pages_cap", 1000))),
            output_dir=str(values.get("output_dir") or "media"),
            jsonl_path=values.get("jsonl_path"),
            resource_db_path=values.get("resource_db_path"),
            resume=bool(values.get("resume", True)),
            max_media_workers=max(1, int(values.get("max_media_workers", 4))),
            min_media_interval=float(values.get("min_media_interval", 0.2)),
            max_media_per_page=int(values.get("max_media_per_page", 200)),
            preferred_height=(
                int(values["preferred_height"])
                if values.get("preferred_height") is not None
                else None
            ),
            max_bandwidth=(
                int(values["max_bandwidth"])
                if values.get("max_bandwidth") is not None
                else None
            ),
            overwrite=bool(values.get("overwrite", False)),
            resume_downloads=bool(values.get("resume_downloads", True)),
            escalate_blocked=bool(values.get("escalate_blocked", True)),
            retry_blocked=bool(values.get("retry_blocked", True)),
            max_sitemap_urls=int(values.get("max_sitemap_urls", 1000)),
            proxy_health_check=bool(values.get("proxy_health_check", False)),
            proxy_health_url=str(values.get("proxy_health_url") or "https://example.com"),
            summary_output=values.get("summary_output"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "same_host": self.same_host,
            "include": self.include,
            "exclude": self.exclude,
            "respect_robots": self.respect_robots,
            "sitemap": self.sitemap,
            "max_workers": self.max_workers,
            "min_interval": self.min_interval,
            "max_retries": self.max_retries,
            "fetch_backend": self.fetch_backend,
            "download_media": self.download_media,
            "auto_adjust_max_pages": self.auto_adjust_max_pages,
            "max_pages_cap": self.max_pages_cap,
            "output_dir": self.output_dir,
            "jsonl_path": self.jsonl_path,
            "resource_db_path": self.resource_db_path,
            "resume": self.resume,
            "media_types": list(self.media_types),
            "preferred_height": self.preferred_height,
            "max_bandwidth": self.max_bandwidth,
            "overwrite": self.overwrite,
            "resume_downloads": self.resume_downloads,
            "proxy_health_check": self.proxy_health_check,
            "proxy_health_url": self.proxy_health_url,
            "summary_output": self.summary_output,
        }


class JsonlCrawlStore:
    """Thread-safe append-only JSONL store used for incremental crawl output."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self.visited_pages: set[str] = set()
        self.visited_media: set[str] = set()
        self.media_records: list[dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or not record.get("url"):
                continue
            kind = record.get("kind")
            if kind == "page":
                self.visited_pages.add(str(record["url"]))
            elif kind in {"image", "video", "audio", "hls"} and record.get("downloaded"):
                self.visited_media.add(str(record["url"]))
            elif kind in {"image", "video", "audio", "hls"}:
                self.media_records.append(record)

    def append(self, record: dict[str, Any]) -> None:
        if self.path is None:
            return
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()


@dataclass
class MediaAsset:
    url: str
    kind: str
    source_page: str
    depth: int = 0
    path: str | None = None
    size: int | None = None
    status: int | None = None
    content_type: str | None = None
    error: str | None = None
    downloaded: bool = False
    sha256: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "url": self.url,
            "source_page": self.source_page,
            "depth": self.depth,
            "path": self.path,
            "size": self.size,
            "status": self.status,
            "content_type": self.content_type,
            "error": self.error,
            "downloaded": self.downloaded,
            "sha256": self.sha256,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MediaAsset:
        return cls(
            url=str(data.get("url") or ""),
            kind=str(data.get("kind") or ""),
            source_page=str(data.get("source_page") or ""),
            depth=int(data.get("depth") or 0),
            path=data.get("path"),
            size=data.get("size"),
            status=data.get("status"),
            content_type=data.get("content_type"),
            error=data.get("error"),
            downloaded=bool(data.get("downloaded")),
            sha256=data.get("sha256"),
            details=dict(data.get("details") or {}),
        )


@dataclass
class MediaPage:
    url: str
    depth: int
    status: int | None = None
    error: str | None = None
    skipped_reason: str | None = None
    blocked: bool = False
    security: dict[str, Any] | None = None
    diagnosis: dict[str, Any] | None = None
    links: list[str] = field(default_factory=list)
    media: list[str] = field(default_factory=list)
    visited_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "page",
            "url": self.url,
            "depth": self.depth,
            "status": self.status,
            "error": self.error,
            "skipped_reason": self.skipped_reason,
            "blocked": self.blocked,
            "security": self.security,
            "diagnosis": self.diagnosis,
            "links": list(self.links),
            "media": list(self.media),
            "visited_at": self.visited_at,
        }


@dataclass
class MediaCrawlResult:
    pages: list[MediaPage]
    media: list[MediaAsset]
    config: dict[str, Any]
    sitemap_urls: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "pages": len(self.pages),
            "pages_ok": sum(1 for page in self.pages if not page.error and not page.blocked),
            "blocked": sum(1 for page in self.pages if page.blocked),
            "errors": sum(1 for page in self.pages if page.error),
            "media_discovered": len(self.media),
            "media_downloaded": sum(1 for asset in self.media if asset.downloaded),
            "media_failed": sum(1 for asset in self.media if asset.error),
            "sitemap_urls": len(self.sitemap_urls),
            "media_kinds": {
                kind: sum(1 for asset in self.media if asset.kind == kind)
                for kind in ("image", "video", "audio", "hls")
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "summary": self.summary(),
            "sitemap_urls": list(self.sitemap_urls),
            "pages": [page.to_dict() for page in self.pages],
            "media": [asset.to_dict() for asset in self.media],
        }


class MediaCrawler:
    """Concurrent, resumable crawler for pages, media, and HLS streams."""

    def __init__(
        self,
        config: MediaCrawlConfig,
        *,
        session: MediaSession | None = None,
        progress: Callable[[str, float, str], None] | None = None,
    ) -> None:
        self.config = config
        self.progress = progress
        self.session = session
        self.proxy_pool = ProxyPool.from_config(config.proxy_config)
        if config.proxy and self.proxy_pool is None:
            self.proxy_pool = ProxyPool([config.proxy])
        self.store = JsonlCrawlStore(config.jsonl_path)
        self.resource_store = (
            ResourceStore(config.resource_db_path)
            if config.resource_db_path
            else None
        )
        self._visited: set[str] = set()
        self._queued: set[str] = set()
        self._shared_cookies = list(config.cookies)
        self._page_limiter = RateLimiter(
            min_interval=config.min_interval,
            jitter=config.jitter,
        )
        self._media_limiter = RateLimiter(
            min_interval=config.min_media_interval,
            jitter=config.jitter,
        )
        self._lock = threading.Lock()
        self._processed = 0
        self._effective_max_pages = config.max_pages
        self._pages: list[MediaPage] = []
        self._media: list[MediaAsset] = []
        self._media_seen: set[str] = set()
        self._robots_cache: dict[str, RobotsPolicy | None] = {}
        self._robots_raw: dict[str, str] = {}
        self.sitemap_urls: list[str] = []
        self._seed_urls = {
            normalized
            for url in config.seeds
            if (normalized := self._normalize_url(url, url)) is not None
        }
        self._seed_hosts = {
            self._host(url) for url in config.seeds if self._host(url)
        }

    @staticmethod
    def _host(url: str) -> str:
        return urllib.parse.urlsplit(url).netloc.lower()

    @staticmethod
    def _normalize_url(url: str, base: str | None = None) -> str | None:
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
        if suffix in _ASSET_EXTS or ".m3u8" in url.lower():
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

    def _get_proxy(self) -> str | None:
        if self.proxy_pool is not None:
            return self.proxy_pool.get_proxy()
        return self.config.proxy

    def _new_session(self) -> MediaSession:
        session = create_fetch_session(
            {
                "backend": self.config.fetch_backend,
                "auto_install": self.config.fetch_auto_install,
                "browser": self.config.browser_config,
            },
            headers=self.config.headers,
            proxy=self._get_proxy(),
            proxy_pool=self.proxy_pool,
            timeout=self.config.timeout,
            min_interval=0.0,
            max_retries=self.config.max_retries,
            backoff_base=self.config.backoff_base,
            backoff_max=self.config.backoff_max,
        )
        if self._shared_cookies:
            session.load_cookies(self._shared_cookies)
        return session

    def _report(self, percent: float, message: str) -> None:
        if self.progress is not None:
            self.progress("crawl", percent, message)

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
        session: MediaSession | None = None
        try:
            session = self._new_session()
            body, status, _ = session.get_bytes_with_meta(robots_url)
            if status == 200:
                raw = body.decode("utf-8", "replace")
                policy = RobotsPolicy(user_agent=self.config.user_agent)
                policy.load_text(raw)
        except Exception:
            policy = None
        finally:
            with suppress(Exception):
                if session is not None:
                    session.close()
        self._robots_cache[host] = policy
        self._robots_raw[host] = raw
        return policy

    def _sitemap_candidates(self, seed_url: str) -> list[str]:
        parts = urllib.parse.urlsplit(seed_url)
        candidates = [
            urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/sitemap.xml", "", ""))
        ]
        policy = self._robots_for(seed_url)
        if policy is not None and policy.loaded:
            for match in re.finditer(r"(?im)^\s*Sitemap\s*:\s*(\S+)", self._robots_raw.get(self._host(seed_url), "")):
                candidates.append(match.group(1).strip())
        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_url(candidate, seed_url)
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _collect_sitemap(self, sitemap_url: str, depth: int = 0) -> list[str]:
        if depth > 2 or len(self.sitemap_urls) >= self.config.max_sitemap_urls:
            return []
        found: list[str] = []
        session: MediaSession | None = None
        try:
            session = self._new_session()
            body, status, _ = session.get_bytes_with_meta(sitemap_url)
        except Exception:
            if session is not None:
                session.close()
            return found
        finally:
            if session is not None:
                session.close()
        if status != 200:
            return found
        try:
            root = ET.fromstring(body.decode("utf-8", "replace"))
        except ET.ParseError:
            return found
        locations = [element.text or "" for element in root.findall(f".//{SITEMAP_NS}loc")]
        if not locations:
            locations = [element.text or "" for element in root.findall(".//loc")]
        is_index = root.tag.endswith("sitemapindex") or root.tag == "sitemapindex"
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

    def _clean_links(self, raw_links: list[str], base_url: str) -> list[str]:
        cleaned: list[str] = []
        for raw in raw_links:
            normalized = self._normalize_url(raw, base_url)
            if normalized is not None and self._allowed(normalized) and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _mark_visited(self, url: str) -> bool:
        with self._lock:
            if url in self._visited or self._processed >= self._effective_max_pages:
                return False
            self._visited.add(url)
            self._processed += 1
            return True

    def _process_page(self, url: str, depth: int) -> MediaPage | None:
        if not self._mark_visited(url):
            return None
        page = MediaPage(url=url, depth=depth, visited_at=time.time())
        policy = self._robots_for(url)
        if policy is not None and policy.loaded and not policy.can_fetch(url):
            page.status = 403
            page.skipped_reason = "robots"
            return page
        self._page_limiter.wait()
        session = self._new_session()
        try:
            try:
                body, status, headers = session.get_bytes_with_meta(url)
            except urllib.error.HTTPError as exc:
                body = exc.read() if hasattr(exc, "read") else b""
                status = int(getattr(exc, "code", 0))
                headers = dict(exc.headers.items()) if exc.headers else {}
            html = body.decode("utf-8", "replace")
            page.status = status
            diagnosis = diagnose_response(
                url,
                status,
                headers,
                html,
                page_url=url,
            )
            page.diagnosis = diagnosis.to_dict()
            page.security = diagnosis.security.to_dict()
            page.blocked = diagnosis.security.is_blocked
            if (
                page.blocked
                and self.config.retry_blocked
                and status in {403, 429, 503}
            ):
                retried = self._retry_blocked(url, status, headers, html)
                if retried is not None:
                    body, status, headers, html = retried
                    page.status = status
                    diagnosis = diagnose_response(url, status, headers, html, page_url=url)
                    page.diagnosis = diagnosis.to_dict()
                    page.security = diagnosis.security.to_dict()
                    page.blocked = diagnosis.security.is_blocked
            if page.blocked:
                return page
            analysis = analyze_page(html, base_url=url)
            page.links = self._clean_links(list(analysis.media.links), url)
            page.media = self._collect_media_urls(analysis, url)
            with self._lock:
                self._media.extend(
                    MediaAsset(
                        url=media_url,
                        kind=kind,
                        source_page=url,
                        depth=depth,
                    )
                    for media_url, kind in page.media
                )
            page.media = [item[0] for item in page.media]
        except Exception as exc:
            page.error = str(exc)
        finally:
            session.close()
        return page

    def _retry_blocked(
        self,
        url: str,
        status: int,
        headers: dict[str, str],
        html: str,
    ) -> tuple[bytes, int, dict[str, str], str] | None:
        if self.proxy_pool is not None:
            proxy = self.session.proxy if self.session is not None else None
            if proxy:
                self.proxy_pool.report_failure(proxy)
        alt_config = None
        if isinstance(self.config.browser_config, dict):
            alt_config = self.config.browser_config.get("alternate")
        if alt_config is None or alt_config.get("enabled", True):
            try:
                alt_result = try_alternate_access(
                    url,
                    {"alternate": alt_config if isinstance(alt_config, dict) else {}},
                    proxy=self._get_proxy(),
                    timeout=float(
                        (alt_config if isinstance(alt_config, dict) else {}).get(
                            "timeout", 3.0
                        )
                    ),
                    max_variants=int(
                        (alt_config if isinstance(alt_config, dict) else {}).get(
                            "max_variants", 8
                        )
                    ),
                )
                if alt_result.passed:
                    return (
                        alt_result.body.encode("utf-8"),
                        int(alt_result.status or 200),
                        alt_result.headers,
                        alt_result.body,
                    )
            except Exception:
                pass
        if not self.config.escalate_blocked or not self.config.browser_config:
            return None
        try:
            from stealth_browser import solve_cloudflare_with_stealth_browser

            result = solve_cloudflare_with_stealth_browser(
                url,
                engine=self.config.browser_config.get("engine", "auto"),
                engine_order=self.config.browser_config.get("engine_order"),
                proxy=self._get_proxy(),
                browser_path=self.config.browser_config.get("browser_path"),
                headless=bool(self.config.browser_config.get("headless", True)),
                headless_fallback=bool(
                    self.config.browser_config.get("headless_fallback", True)
                ),
                storage_state=self.config.browser_config.get("storage_state"),
                timeout_ms=float(
                    self.config.browser_config.get("challenge_timeout", 60000)
                ),
                auto_install=bool(
                    self.config.browser_config.get("auto_install", self.config.fetch_auto_install)
                ),
                max_attempts=int(self.config.browser_config.get("max_attempts", 2)),
                retry_delay=float(self.config.browser_config.get("retry_delay", 2.0)),
                rotate_proxy_on_fail=bool(
                    self.config.browser_config.get("rotate_proxy_on_fail", True)
                ),
                proxy_pool=self.proxy_pool,
            )
            if result.html and not result.error:
                for cookie in result.cookies or []:
                    with self._lock:
                        if (
                            cookie.get("name")
                            and cookie.get("domain")
                            and cookie not in self._shared_cookies
                        ):
                            self._shared_cookies.append(cookie)
                return (
                    result.html.encode("utf-8"),
                    int(result.status or 200),
                    {"Content-Type": "text/html; charset=utf-8"},
                    result.html,
                )
        except Exception:
            return None
        return None

    def _collect_media_urls(
        self,
        analysis: Any,
        page_url: str,
    ) -> list[tuple[str, str]]:
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        sources = []
        if hasattr(analysis, "media"):
            sources.append(analysis.media)
        if hasattr(analysis, "json_media"):
            sources.append(analysis.json_media)
        attr_by_kind = {
            "image": "images",
            "video": "videos",
            "audio": "audios",
            "hls": "hls",
            "dash": "dash",
            "smooth": "smooth",
        }
        for source in sources:
            for kind in self.config.media_types:
                attr = attr_by_kind.get(kind, kind)
                values = getattr(source, attr, []) or []
                for raw in values:
                    media_url = normalize_url(raw, page_url)
                    if media_url not in seen:
                        seen.add(media_url)
                        found.append((media_url, kind))
        for raw in getattr(getattr(analysis, "media", None), "links", []) or []:
            media_url = normalize_url(raw, page_url)
            kind = _classify_media_url(media_url)
            if kind and kind in self.config.media_types and media_url not in seen:
                seen.add(media_url)
                found.append((media_url, kind))
        return found[: self.config.max_media_per_page]

    def _download_all_media(self) -> None:
        if not self.config.download_media:
            return
        assets = list(self._media)
        if not assets:
            return
        output = Path(self.config.output_dir)
        seen_media = self._media_seen
        deduped: list[MediaAsset] = []
        for asset in assets:
            if asset.url not in seen_media:
                seen_media.add(asset.url)
                deduped.append(asset)
        assets = deduped
        assets = [
            asset
            for asset in assets
            if not (self.config.resume and asset.url in self.store.visited_media)
        ]
        if self.resource_store is not None and not self.config.overwrite:
            assets = [
                asset
                for asset in assets
                if self.resource_store.status(asset.url) != "success"
            ]
        if not assets:
            return
        completed = 0
        total = len(assets)
        with ThreadPoolExecutor(max_workers=self.config.max_media_workers) as pool:
            futures = {
                pool.submit(self._download_asset, asset, output): asset for asset in assets
            }
            for future in as_completed(futures):
                asset = futures[future]
                try:
                    record = future.result()
                except Exception as exc:
                    asset.error = str(exc)
                    record = asset.to_dict()
                self.store.append(record)
                if self.resource_store is not None:
                    if record.get("downloaded"):
                        self.resource_store.mark_success(
                            asset.url,
                            path=record.get("path") or "",
                            size=int(record.get("size") or 0),
                            sha256=record.get("sha256"),
                            kind=record.get("kind"),
                        )
                    elif record.get("error"):
                        self.resource_store.mark_failed(
                            asset.url,
                            record.get("error") or "download failed",
                            kind=record.get("kind"),
                        )
                completed += 1
                self._report(
                    0.8 + 0.2 * (completed / total),
                    f"media: {record.get('kind')} {record.get('url')}",
                )
        with self._lock:
            has_new_nested = any(
                asset.url not in self._media_seen for asset in self._media
            )
        if has_new_nested:
            self._download_all_media()

    def _download_asset(self, asset: MediaAsset, output: Path) -> dict[str, Any]:
        if asset.kind == "hls":
            return self._download_hls(asset, output)
        if asset.kind == "dash":
            return self._download_dash(asset, output)
        return self._download_binary(asset, output)

    def _download_binary(self, asset: MediaAsset, output: Path) -> dict[str, Any]:
        from resource_downloader import ResourceDownloader

        self._media_limiter.wait()
        session = self._new_session()
        try:
            result = ResourceDownloader(
                session,
                timeout=self.config.timeout,
            ).download(
                asset.url,
                output / asset.kind,
                filename=_asset_filename(asset, {}),
                overwrite=self.config.overwrite,
                resume=self.config.resume_downloads,
            )
            asset.path = result.path
            asset.status = result.status
            asset.content_type = result.content_type
            asset.size = result.size
            asset.sha256 = result.sha256
            asset.details = result.details
            asset.downloaded = result.error is None
            if result.error:
                asset.error = result.error
            nested_assets = (result.details or {}).get("nested_assets") or []
            if nested_assets:
                with self._lock:
                    for nested_url in nested_assets:
                        nested_kind = _classify_media_url(nested_url)
                        if (
                            nested_kind
                            and nested_kind in self.config.media_types
                            and nested_url not in self._media_seen
                            and not any(item.url == nested_url for item in self._media)
                        ):
                            self._media.append(
                                MediaAsset(
                                    url=nested_url,
                                    kind=nested_kind,
                                    source_page=asset.source_page,
                                    depth=asset.depth,
                                )
                            )
        except Exception as exc:
            asset.error = str(exc)
        finally:
            session.close()
        return asset.to_dict()

    def _download_hls(self, asset: MediaAsset, output: Path) -> dict[str, Any]:
        from hls_client import HLSClient

        self._media_limiter.wait()
        session = self._new_session()
        client = HLSClient(session=session)
        try:
            result = client.download(
                asset.url,
                output / "hls",
                preferred_height=self.config.preferred_height,
                max_bandwidth=self.config.max_bandwidth,
                include_segments=True,
                combine=True,
                decrypt=True,
                overwrite=self.config.overwrite,
            )
            asset.path = result.combined_path or str(output / "hls")
            asset.size = result.total_bytes
            asset.status = 200
            asset.downloaded = result.failed_segments == 0 and result.combined_path is not None
            asset.details = result.summary()
            if result.failed_segments:
                asset.error = "; ".join(result.errors[:5])
        except Exception as exc:
            asset.error = str(exc)
        finally:
            client.close()
            session.close()
        return asset.to_dict()

    def _download_dash(self, asset: MediaAsset, output: Path) -> dict[str, Any]:
        from dash_client import DASHClient

        self._media_limiter.wait()
        session = self._new_session()
        client = DASHClient(session=session)
        try:
            result = client.download(
                asset.url,
                output / "dash",
                preferred_height=self.config.preferred_height,
                max_bandwidth=self.config.max_bandwidth,
                include_segments=True,
                combine=True,
                save_manifest=True,
                overwrite=self.config.overwrite,
            )
            asset.path = result.combined_path or str(output / "dash")
            asset.size = result.total_bytes
            asset.status = 200
            asset.downloaded = result.failed_segments == 0 and result.combined_path is not None
            asset.details = result.summary()
            if result.failed_segments:
                asset.error = "; ".join(result.errors[:5])
        except Exception as exc:
            asset.error = str(exc)
        finally:
            client.close()
            session.close()
        return asset.to_dict()

    def run(self) -> MediaCrawlResult:
        if self.proxy_pool is not None and self.config.proxy_health_check:
            self.proxy_pool.check_all(self.config.proxy_health_url)
        if self.store.path is not None and self.config.resume:
            self._visited.update(self.store.visited_pages)
            self._queued.update(self.store.visited_pages)
            self._processed = len(self._visited)
            self._media.extend(
                MediaAsset.from_dict(record)
                for record in self.store.media_records
                if not record.get("downloaded")
            )
        if self.resource_store is not None and self.config.resume:
            for item in self.resource_store.failed():
                self._media.append(
                    MediaAsset(
                        url=str(item.get("url") or ""),
                        kind=str(item.get("kind") or "resource"),
                        source_page=str(item.get("url") or ""),
                        path=item.get("path"),
                        size=item.get("size"),
                        sha256=item.get("sha256"),
                        error=item.get("last_error"),
                    )
                )
        current: list[tuple[str, int]] = []
        for seed in self.config.seeds:
            normalized = self._normalize_url(seed, seed)
            direct_kind = _classify_media_url(seed)
            if (
                direct_kind
                and direct_kind in self.config.media_types
                and normalized is not None
            ):
                with self._lock:
                    self._media.append(
                        MediaAsset(
                            url=normalized,
                            kind=direct_kind,
                            source_page=seed,
                            depth=0,
                        )
                    )
                self._visited.add(normalized)
                continue
            if normalized and normalized not in self._visited:
                current.append((normalized, 0))
        if self.config.sitemap:
            for seed in self.config.seeds:
                for sitemap_url in self._sitemap_candidates(seed):
                    for found in self._collect_sitemap(sitemap_url):
                        if (
                            found not in self._visited
                            and found not in self._queued
                            and self._allowed(found)
                        ):
                            self._queued.add(found)
                            current.append((found, 1))
        for depth in range(self.config.max_depth + 1):
            if self.config.auto_adjust_max_pages:
                self._effective_max_pages = min(
                    self.config.max_pages_cap,
                    max(self.config.max_pages, self._processed + len(current)),
                )
            if not current or self._processed >= self._effective_max_pages:
                break
            batch: list[tuple[str, int]] = []
            with ThreadPoolExecutor(max_workers=self.config.max_workers) as pool:
                futures = {
                    pool.submit(self._process_page, url, page_depth): (url, page_depth)
                    for url, page_depth in current
                }
                for future in as_completed(futures):
                    page = future.result()
                    if page is None:
                        continue
                    self._pages.append(page)
                    self.store.append(page.to_dict())
                    if depth < self.config.max_depth:
                        for link in page.links:
                            if (
                                link not in self._visited
                                and link not in self._queued
                            ):
                                self._queued.add(link)
                                batch.append((link, depth + 1))
                    self._report(
                        self._processed / self._effective_max_pages,
                        f"crawled {self._processed}/{self._effective_max_pages}: {page.url}",
                    )
            current = batch
        self._download_all_media()
        if self.resource_store is not None:
            self.resource_store.close()
        return MediaCrawlResult(
            pages=self._pages,
            media=self._media,
            config=self.config.to_dict(),
            sitemap_urls=list(self.sitemap_urls),
        )


def _classify_media_url(url: str) -> str | None:
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
    if suffix == ".css":
        return "css"
    if suffix in {".js", ".mjs"}:
        return "js"
    if suffix in _FONT_EXTS:
        return "font"
    if suffix in _DOCUMENT_EXTS:
        return "file"
    if suffix in _DATA_EXTS:
        return "data"
    return None


def _header_value(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


def _asset_filename(asset: MediaAsset, headers: dict[str, str]) -> str:
    filename = guess_filename(asset.url, _header_value(headers, "content-disposition"))
    if not filename:
        path = urllib.parse.urlsplit(asset.url).path
        filename = path.rstrip("/").rsplit("/", 1)[-1] if path.rstrip("/") else asset.kind
    digest = hashlib.sha1(asset.url.encode("utf-8")).hexdigest()[:8]
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
    return f"{digest}-{safe}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Concurrent media crawler")
    parser.add_argument("--config", help="JSON config file")
    args = parser.parse_args(argv)
    if not args.config:
        parser.error("--config is required")
    config = MediaCrawlConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
    result = MediaCrawler(config).run()
    from run_summary import media_result_report, print_report, write_report

    report = media_result_report(result)
    if config.summary_output:
        write_report(report, config.summary_output)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
