"""Autonomous async crawler for million-scale, unattended collection.

The crawler combines asyncio scheduling, disk-backed URL deduplication,
human-like UA/rate behavior, proxy rotation, automatic page analysis,
schema-free record extraction/validation, dynamic browser rendering, and
JSONL output. It is designed to run 24/7 and resume from its SQLite state
when interrupted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from alternate_access import try_alternate_access
from block_diagnoser import diagnose_response
from data_extractor import AutoDataExtractor, ExtractionResult
from human_behavior import HumanBehavior
from page_data_parser import analyze_page
from proxy_pool import ProxyPool
from scrape_guard import RobotsPolicy
from url_store import UrlDeduplicator

SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


@dataclass
class AutonomousCrawlerConfig:
    seeds: list[str] = field(default_factory=list)
    max_urls: int = 10_000_000
    max_depth: int = 10
    same_host: bool = True
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    max_concurrency: int = 16
    min_delay: float = 0.2
    max_delay: float = 1.2
    jitter: float = 0.3
    max_retries: int = 3
    backoff_base: float = 0.5
    backoff_max: float = 30.0
    timeout: float = 20.0
    headers: dict[str, str] = field(default_factory=dict)
    user_agents: list[str] = field(default_factory=list)
    proxies: list[str] = field(default_factory=list)
    proxy_config: Any = None
    respect_robots: bool = True
    sitemap: bool = True
    dynamic_render: bool = True
    browser_config: dict[str, Any] | None = None
    url_db_path: str = "crawl_urls.sqlite3"
    jsonl_path: str = "crawl.jsonl"
    output_media: bool = True
    checkpoint_interval: int = 100
    proxy_health_check: bool = False
    proxy_health_url: str = "https://example.com"
    summary_output: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AutonomousCrawlerConfig:
        values = dict(data or {})
        return cls(
            seeds=[str(item) for item in values.get("seeds") or []],
            max_urls=int(values.get("max_urls", 10_000_000)),
            max_depth=int(values.get("max_depth", 10)),
            same_host=bool(values.get("same_host", True)),
            include=[str(item) for item in values.get("include") or []],
            exclude=[str(item) for item in values.get("exclude") or []],
            max_concurrency=max(1, int(values.get("max_concurrency", 16))),
            min_delay=float(values.get("min_delay", 0.2)),
            max_delay=float(values.get("max_delay", 1.2)),
            jitter=float(values.get("jitter", 0.3)),
            max_retries=int(values.get("max_retries", 3)),
            backoff_base=float(values.get("backoff_base", 0.5)),
            backoff_max=float(values.get("backoff_max", 30.0)),
            timeout=float(values.get("timeout", 20.0)),
            headers=dict(values.get("headers") or {}),
            user_agents=[str(item) for item in values.get("user_agents") or []],
            proxies=[str(item) for item in values.get("proxies") or []],
            proxy_config=values.get("proxy_pool"),
            respect_robots=bool(values.get("respect_robots", True)),
            sitemap=bool(values.get("sitemap", True)),
            dynamic_render=bool(values.get("dynamic_render", True)),
            browser_config=dict(values["browser"]) if values.get("browser") else None,
            url_db_path=str(values.get("url_db_path") or "crawl_urls.sqlite3"),
            jsonl_path=str(values.get("jsonl_path") or "crawl.jsonl"),
            output_media=bool(values.get("output_media", True)),
            checkpoint_interval=int(values.get("checkpoint_interval", 100)),
            proxy_health_check=bool(values.get("proxy_health_check", False)),
            proxy_health_url=str(values.get("proxy_health_url") or "https://example.com"),
            summary_output=values.get("summary_output"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "seeds": self.seeds,
            "max_urls": self.max_urls,
            "max_depth": self.max_depth,
            "same_host": self.same_host,
            "max_concurrency": self.max_concurrency,
            "min_delay": self.min_delay,
            "max_delay": self.max_delay,
            "max_retries": self.max_retries,
            "respect_robots": self.respect_robots,
            "sitemap": self.sitemap,
            "dynamic_render": self.dynamic_render,
            "url_db_path": self.url_db_path,
            "jsonl_path": self.jsonl_path,
            "proxy_health_check": self.proxy_health_check,
            "proxy_health_url": self.proxy_health_url,
            "summary_output": self.summary_output,
        }


class AutonomousCrawler:
    """Asyncio crawler with automatic analysis, validation, and recovery."""

    def __init__(
        self,
        config: AutonomousCrawlerConfig,
        progress: Callable[[str, float, str], None] | None = None,
    ) -> None:
        self.config = config
        self.progress = progress
        self.human = HumanBehavior(
            config.user_agents,
            min_delay=config.min_delay,
            max_delay=config.max_delay,
            jitter=config.jitter,
        )
        self.proxy_pool = ProxyPool.from_config(config.proxy_config)
        if config.proxies and self.proxy_pool is None:
            self.proxy_pool = ProxyPool(config.proxies)
        self.extractor = AutoDataExtractor()
        self._dedup: UrlDeduplicator | None = None
        self._json_lock: asyncio.Lock | None = None
        self._started_at = time.time()
        self._stats: dict[str, int] = {
            "seen": 0,
            "fetched": 0,
            "blocked": 0,
            "records": 0,
            "media": 0,
            "errors": 0,
        }
        self._stop = False
        self._robots_cache: dict[str, RobotsPolicy | None] = {}
        self._robots_raw: dict[str, str] = {}
        self._shared_cookies: list[dict[str, Any]] = []

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
        if self.config.same_host and self._host(url) not in {
            self._host(seed) for seed in self.config.seeds
        }:
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

    def run(self) -> dict[str, Any]:
        return asyncio.run(self.arun())

    async def arun(self) -> dict[str, Any]:
        self._dedup = UrlDeduplicator(self.config.url_db_path)
        self._json_lock = asyncio.Lock()
        if self.proxy_pool is not None and self.config.proxy_health_check:
            await asyncio.to_thread(
                self.proxy_pool.check_all,
                self.config.proxy_health_url,
            )
        queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        seed_hosts = {self._host(seed) for seed in self.config.seeds if self._host(seed)}
        initial: list[tuple[str, int]] = []
        for seed in self.config.seeds:
            normalized = self._normalize_url(seed, seed)
            if not normalized:
                continue
            if await self._robots_allowed(normalized):
                initial.append((normalized, 0))
        if self.config.sitemap:
            for seed in list(self.config.seeds):
                for found in await self._collect_sitemap_for_seed(seed):
                    if (
                        self._allowed(found)
                        and not self._dedup.contains(found)
                    ):
                        initial.append((found, 1))
        for item in initial:
            await queue.put(item)
        workers = [
            asyncio.create_task(self._worker(queue, seed_hosts))
            for _ in range(self.config.max_concurrency)
        ]
        await queue.join()
        self._stop = True
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
        self._dedup.checkpoint()
        self._dedup.close()
        return {
            "duration_seconds": round(time.time() - self._started_at, 3),
            "stats": dict(self._stats),
            "config": self.config.to_dict(),
        }

    async def _worker(
        self,
        queue: asyncio.Queue[tuple[str, int]],
        seed_hosts: set[str],
    ) -> None:
        while not self._stop:
            try:
                url, depth = await asyncio.wait_for(queue.get(), timeout=0.3)
            except asyncio.TimeoutError:
                continue
            try:
                await self._process(queue, url, depth, seed_hosts)
            except Exception as exc:
                self._stats["errors"] += 1
                await self._write_record(
                    {"kind": "error", "url": url, "depth": depth, "error": str(exc)}
                )
            finally:
                queue.task_done()

    async def _process(
        self,
        queue: asyncio.Queue[tuple[str, int]],
        url: str,
        depth: int,
        seed_hosts: set[str],
    ) -> None:
        if self._dedup is None or self._dedup.contains(url):
            return
        if self._stats["seen"] >= self.config.max_urls:
            return
        self._dedup.add(url)
        self._stats["seen"] += 1
        await asyncio.sleep(self.human.delay())
        try:
            body, status, headers = await self._fetch(url)
        except Exception as exc:
            self._stats["errors"] += 1
            await self._write_record(
                {"kind": "error", "url": url, "depth": depth, "error": str(exc)}
            )
            return
        self._stats["fetched"] += 1
        html = body.decode("utf-8", "replace")
        diagnosis = diagnose_response(url, status, headers, html, page_url=url)
        if diagnosis.security.is_blocked and self.config.dynamic_render:
            rendered = await asyncio.to_thread(self._render_dynamic, url)
            if rendered is not None:
                body, status, headers, html = rendered
                diagnosis = diagnose_response(url, status, headers, html, page_url=url)
        page_record = {
            "kind": "page",
            "url": url,
            "depth": depth,
            "status": status,
            "blocked": diagnosis.security.is_blocked,
            "diagnosis": diagnosis.to_dict(),
            "ts": time.time(),
        }
        await self._write_record(page_record)
        if diagnosis.security.is_blocked:
            self._stats["blocked"] += 1
            return
        analysis = analyze_page(html, base_url=url)
        extraction: ExtractionResult = await asyncio.to_thread(
            self.extractor.analyze,
            html,
            url,
        )
        for record in extraction.records:
            record.setdefault("_url", url)
            self._stats["records"] += 1
            await self._write_record({"kind": "record", **record})
        if self.config.output_media:
            for kind, values in (
                ("image", analysis.media.images),
                ("video", analysis.media.videos),
                ("audio", analysis.media.audios),
                ("hls", analysis.media.hls),
            ):
                for media_url in values:
                    self._stats["media"] += 1
                    await self._write_record(
                        {
                            "kind": "media",
                            "media_type": kind,
                            "url": media_url,
                            "source_page": url,
                            "depth": depth,
                        }
                    )
        if depth < self.config.max_depth:
            for link in analysis.media.links:
                normalized = self._normalize_url(link, url)
                if (
                    normalized
                    and self._allowed(normalized)
                    and not self._dedup.contains(normalized)
                    and self._stats["seen"] < self.config.max_urls
                ):
                    await queue.put((normalized, depth + 1))
        if self._stats["seen"] % self.config.checkpoint_interval == 0:
            self._dedup.checkpoint()
            if self.progress is not None:
                self.progress(
                    "autonomous",
                    min(1.0, self._stats["seen"] / self.config.max_urls),
                    f"seen={self._stats['seen']} records={self._stats['records']}",
                )

    async def _fetch(self, url: str) -> tuple[bytes, int, dict[str, str]]:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("autonomous crawler requires httpx") from exc
        proxy = (
            self.proxy_pool.get_sticky_proxy(self._host(url))
            if self.proxy_pool
            else None
        )
        headers = dict(self.config.headers)
        headers["User-Agent"] = self.human.next_user_agent()
        cookie_header = self._cookie_header(url)
        if cookie_header:
            headers.setdefault("Cookie", cookie_header)
        for attempt in range(self.config.max_retries + 1):
            try:
                async with httpx.AsyncClient(
                    proxy=proxy,
                    headers=headers,
                    timeout=self.config.timeout,
                    follow_redirects=True,
                    http2=True,
                ) as client:
                    response = await client.get(url)
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.config.max_retries:
                    await asyncio.sleep(self.human.backoff_delay(attempt))
                    continue
                return response.content, response.status_code, dict(response.headers)
            except Exception:
                if attempt >= self.config.max_retries:
                    raise
                await asyncio.sleep(self.human.backoff_delay(attempt))
        raise RuntimeError("fetch failed")

    def _cookie_header(self, url: str) -> str:
        host = urllib.parse.urlsplit(url).hostname or ""
        parts: list[str] = []
        for item in self._shared_cookies:
            domain = str(item.get("domain") or "").lower().lstrip(".")
            if domain and host != domain and not host.endswith("." + domain):
                continue
            parts.append(f"{item.get('name')}={item.get('value')}")
        return "; ".join(parts)

    def _render_dynamic(
        self,
        url: str,
    ) -> tuple[bytes, int, dict[str, str], str] | None:
        if not self.config.browser_config:
            return None
        alt_config = self.config.browser_config.get("alternate")
        if alt_config is None or alt_config.get("enabled", True):
            try:
                alt_result = try_alternate_access(
                    url,
                    {"alternate": alt_config if isinstance(alt_config, dict) else {}},
                    proxy=(
                        self.proxy_pool.get_sticky_proxy(self._host(url))
                        if self.proxy_pool
                        else None
                    ),
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
        try:
            from stealth_browser import solve_cloudflare_with_stealth_browser

            result = solve_cloudflare_with_stealth_browser(
                url,
                engine=self.config.browser_config.get("engine", "auto"),
                engine_order=self.config.browser_config.get("engine_order"),
                proxy=(
                    self.proxy_pool.get_sticky_proxy(self._host(url))
                    if self.proxy_pool
                    else None
                ),
                browser_path=self.config.browser_config.get("browser_path"),
                headless=bool(self.config.browser_config.get("headless", True)),
                headless_fallback=bool(
                    self.config.browser_config.get("headless_fallback", True)
                ),
                storage_state=self.config.browser_config.get("storage_state"),
                timeout_ms=float(self.config.browser_config.get("challenge_timeout", 60000)),
                auto_install=bool(self.config.browser_config.get("auto_install", False)),
                max_attempts=int(self.config.browser_config.get("max_attempts", 2)),
                retry_delay=float(self.config.browser_config.get("retry_delay", 2.0)),
                rotate_proxy_on_fail=bool(
                    self.config.browser_config.get("rotate_proxy_on_fail", True)
                ),
                proxy_pool=self.proxy_pool,
            )
            if not result.html or result.error:
                return None
            for cookie in result.cookies or []:
                if cookie.get("name") and cookie.get("domain") and cookie not in self._shared_cookies:
                    self._shared_cookies.append(cookie)
            return (
                result.html.encode("utf-8"),
                int(result.status or 200),
                {"Content-Type": "text/html; charset=utf-8"},
                result.html,
            )
        except Exception:
            return None

    async def _robots_allowed(self, url: str) -> bool:
        if not self.config.respect_robots:
            return True
        host = self._host(url)
        if host in self._robots_cache:
            policy = self._robots_cache[host]
            return policy is None or not policy.loaded or policy.can_fetch(url)
        parts = urllib.parse.urlsplit(url)
        robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        policy: RobotsPolicy | None = None
        raw = ""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                response = await client.get(robots_url)
            if response.status_code == 200:
                raw = response.text
                policy = RobotsPolicy(user_agent=self.config.headers.get("User-Agent", "Autonomous/1.0"))
                policy.load_text(raw)
        except Exception:
            policy = None
        self._robots_cache[host] = policy
        self._robots_raw[host] = raw
        return policy is None or not policy.loaded or policy.can_fetch(url)

    async def _collect_sitemap_for_seed(self, seed: str) -> list[str]:
        if not self.config.sitemap:
            return []
        normalized_seed = self._normalize_url(seed, seed)
        if normalized_seed is None:
            return []
        parts = urllib.parse.urlsplit(normalized_seed)
        candidates = [
            urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/sitemap.xml", "", ""))
        ]
        raw = self._robots_raw.get(self._host(normalized_seed), "")
        for match in re.finditer(r"(?im)^\s*Sitemap\s*:\s*(\S+)", raw):
            candidates.append(match.group(1).strip())
        found: list[str] = []
        for candidate in candidates:
            found.extend(await self._fetch_sitemap(candidate, 0))
        return found

    async def _fetch_sitemap(self, url: str, depth: int) -> list[str]:
        if depth > 2:
            return []
        found: list[str] = []
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(url)
            if response.status_code != 200:
                return found
            root = ET.fromstring(response.text)
        except Exception:
            return found
        locations = [element.text or "" for element in root.findall(f".//{SITEMAP_NS}loc")]
        if not locations:
            locations = [element.text or "" for element in root.findall(".//loc")]
        if root.tag.endswith("sitemapindex") or root.tag == "sitemapindex":
            for location in locations:
                found.extend(await self._fetch_sitemap(location, depth + 1))
        else:
            for location in locations:
                normalized = self._normalize_url(location, url)
                if normalized and normalized not in found:
                    found.append(normalized)
        return found

    async def _write_record(self, record: dict[str, Any]) -> None:
        if self._json_lock is None:
            return
        async with self._json_lock:
            path = Path(self.config.jsonl_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous async web crawler")
    parser.add_argument("--config", required=True, help="JSON config file")
    args = parser.parse_args(argv)
    config = AutonomousCrawlerConfig.from_dict(
        json.loads(Path(args.config).read_text(encoding="utf-8"))
    )
    summary = AutonomousCrawler(config).run()
    from run_summary import (
        _path_info,
        final_report,
        jsonl_report,
        print_report,
        write_report,
    )

    replay = jsonl_report(config.jsonl_path)
    report = final_report(
        save_paths=[
            _path_info(config.url_db_path, "url_db"),
            _path_info(config.jsonl_path, "crawl_jsonl"),
        ],
        resources=replay["resources"],
        summary={"autonomous": summary, "jsonl": replay["summary"]},
    )
    if config.summary_output:
        write_report(report, config.summary_output)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
