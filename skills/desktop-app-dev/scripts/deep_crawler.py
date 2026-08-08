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
import re
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

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


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
            "extension_skip": list(self.extension_skip),
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
    media: dict[str, list[str]] = field(default_factory=dict)
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
            "media": self.media,
        }


@dataclass
class CrawlResult:
    """Full crawl output plus a compact summary."""

    pages: list[CrawlPage]
    config: dict[str, Any] = field(default_factory=dict)
    sitemap_urls: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        ok = sum(1 for page in self.pages if not page.error and not page.blocked)
        blocked = sum(1 for page in self.pages if page.blocked)
        errors = sum(1 for page in self.pages if page.error)
        robots = sum(1 for page in self.pages if page.skipped_reason == "robots")
        api_count = sum(len(page.api_endpoints) for page in self.pages)
        media_count = sum(len(values) for page in self.pages for values in page.media.values())
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
            "media_urls": media_count,
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
        self.sitemap_urls: list[str] = []
        self._robots_cache: dict[str, RobotsPolicy | None] = {}
        self._robots_raw: dict[str, str] = {}
        self._seed_urls = {self._normalize_url(url, url) for url in config.seeds}
        self._seed_hosts = {self._host(url) for url in config.seeds if self._host(url)}

    def _default_session(self) -> MediaSession:
        if self.session is None:
            self.session = MediaSession(
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

    def _clean_links(self, raw_links: list[str], base_url: str) -> list[str]:
        cleaned: list[str] = []
        for raw in raw_links:
            normalized = self._normalize_url(raw, base_url)
            if normalized is not None and self._allowed(normalized) and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

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
                pages.append(
                    CrawlPage(
                        url=url,
                        depth=depth,
                        skipped_reason="robots",
                        status=403,
                    )
                )
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
                pages.append(CrawlPage(url=url, depth=depth, error=str(exc)))
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
            page = CrawlPage(
                url=url,
                depth=depth,
                status=response.status,
                html=html,
                security=report,
                blocked=report.is_blocked,
            )
            if report.is_blocked and self.config.skip_blocked:
                pages.append(page)
                self._report(
                    len(pages) / self.config.max_pages,
                    f"blocked ({report.primary_kind}): {url}",
                )
                continue

            analysis = analyze_page(html, base_url=url)
            page.analysis = analysis
            page.links = self._clean_links(list(analysis.media.links), url)
            page.api_endpoints = [item.to_dict() for item in analysis.api_endpoints]
            page.media = {
                "videos": analysis.media.videos,
                "audios": analysis.media.audios,
                "images": analysis.media.images,
                "hls": analysis.media.hls,
                "links": analysis.media.links,
            }
            pages.append(page)

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

        return CrawlResult(
            pages=pages,
            config=self.config.to_dict(),
            sitemap_urls=list(self.sitemap_urls),
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
