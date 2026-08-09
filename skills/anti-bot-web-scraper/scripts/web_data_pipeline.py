"""End-to-end web data pipeline for authorized desktop automation.

Orchestrates the existing skill templates into one flow:

1. Optional fingerprint browser session (stable profile, cookies, proxy)
2. Optional automatic CAPTCHA solving (third-party service / manual fallback)
3. Page + API analysis (static parse and runtime network capture)
4. API data fetching with rate limits and retries
5. Declarative data processing (data_processor.py)
6. JSON / JSONL / CSV output

The CLI takes one JSON config file so a desktop UI can run the same pipeline
as a worker task.
"""

from __future__ import annotations

import argparse
import http.server
import json
import sys
import tempfile
import threading
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from alternate_access import try_alternate_access
from api_client import ApiClient, ApiSpec, build_api_specs
from browser_session import BrowserSession, FingerprintOptions, NetworkCaptureOptions, PageCapture
from captcha_solver import AutoCaptchaSolver, CaptchaSolver, ManualCaptchaSolver
from cloudflare_challenge import (
    CloudflareChallengeConfig,
    CloudflareChallengeHandler,
    CloudflareChallengeResult,
)
from data_processor import load_records, process_records, save_records
from deep_crawler import CrawlConfig, CrawledResponse, DeepCrawler
from fingerprint_binding import binding_from_fetch_config
from page_data_parser import analyze_page
from proxy_pool import ProxyPool
from security_detector import detect_security_mechanisms
from smart_fetch import create_fetch_session


def _read_config(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _unwrap_data(data: Any, depth: int = 0) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and depth < 4:
        for key in ("items", "data", "records", "list", "rows", "results"):
            value = data.get(key)
            if isinstance(value, list | dict):
                found = _unwrap_data(value, depth + 1)
                if found:
                    return found
        return [data]
    return []


def _build_captcha_solver(config: dict[str, Any]) -> AutoCaptchaSolver | None:
    captcha = config.get("captcha") or {}
    if not captcha.get("enabled", False):
        return None
    api_key = str(captcha.get("api_key", "") or "")
    manual = ManualCaptchaSolver()
    if api_key:
        solver = CaptchaSolver(
            api_key=api_key,
            base_url=str(captcha.get("base_url", "https://2captcha.com") or "https://2captcha.com"),
        )
    else:
        solver = None
    if solver is None and not captcha.get("allow_manual_fallback", False):
        return None
    if solver is None:
        return AutoCaptchaSolver(
            solver=CaptchaSolver(api_key=""),
            allow_manual_fallback=True,
            manual_solver=manual,
        )
    return AutoCaptchaSolver(
        solver=solver,
        allow_manual_fallback=bool(captcha.get("allow_manual_fallback", False)),
        manual_solver=manual,
    )


class WebDataPipeline:
    """Run one configured page/API collection + processing job."""

    def __init__(
        self,
        config: dict[str, Any],
        output: str | Path | None = None,
    ) -> None:
        self.config = config
        self.output = Path(output) if output else Path(config.get("output", "output.json"))
        self.browser_config = config.get("browser") or {}
        self.api_config = config.get("api") or {}
        self.security_config = config.get("security") or {}
        self.crawl_config = config.get("crawl") or {}
        self.cloudflare_config = config.get("cloudflare") or {}
        self.fetch_config = config.get("fetch") or {}
        self.crawl_result: Any = None
        self._browser_captures: dict[str, PageCapture] = {}
        self.api_security_findings = 0
        self._cloudflare_result: CloudflareChallengeResult | None = None
        self._last_cloudflare_result: CloudflareChallengeResult | None = None
        account = config.get("account") or {}
        self._account_cookies: list[dict[str, Any]] = []
        if isinstance(account, dict):
            browser = dict(self.browser_config)
            api = dict(self.api_config)
            if account.get("storage_state"):
                browser["storage_state"] = account["storage_state"]
            if account.get("cookies_path"):
                browser.setdefault("cookies_path", account["cookies_path"])
                api.setdefault("cookies_path", account["cookies_path"])
            if account.get("user_data_dir"):
                browser["user_data_dir"] = account["user_data_dir"]
            if account.get("proxy"):
                browser["proxy"] = account["proxy"]
                api["proxy"] = account["proxy"]
            if account.get("headers"):
                merged_headers = dict(api.get("headers") or {})
                merged_headers.update(account["headers"])
                api["headers"] = merged_headers
            if account.get("login"):
                merged_login = dict(browser.get("login") or {})
                merged_login.update(account["login"])
                browser["login"] = merged_login
            self.browser_config = browser
            self.api_config = api
            self._account_cookies = list(account.get("cookies") or [])
        self.proxy_pool = ProxyPool.from_config(
            config.get("proxy_pool")
            or self.api_config.get("proxy_pool")
            or self.browser_config.get("proxy_pool")
        )
        self._api_cookies: list[dict[str, Any]] = list(self._account_cookies)
        api_cookies_path = self.api_config.get("cookies_path") or self.browser_config.get(
            "cookies_path"
        )
        if api_cookies_path and Path(api_cookies_path).exists():
            try:
                loaded = json.loads(Path(api_cookies_path).read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    self._api_cookies.extend(loaded)
            except (OSError, json.JSONDecodeError):
                pass
        self.pages = [str(page) for page in config.get("pages", [])]
        self.captcha_solver = _build_captcha_solver(config)
        self.session: BrowserSession | None = None
        self.captures: list[PageCapture] = []
        self.specs: list[ApiSpec] = []
        self._browser_cookies: list[dict[str, Any]] = []
        self.hls_results: list[dict[str, Any]] = []
        self.last_summary: dict[str, Any] | None = None

    def _fingerprint(self) -> FingerprintOptions:
        fingerprint_cfg = self.browser_config.get("fingerprint") or {}
        fingerprint_path = self.browser_config.get("fingerprint_path")
        if fingerprint_path and Path(fingerprint_path).exists():
            return FingerprintOptions.load(fingerprint_path)
        if isinstance(fingerprint_cfg, dict) and fingerprint_cfg:
            return FingerprintOptions.from_dict(fingerprint_cfg)
        seed = fingerprint_cfg.get("seed") if isinstance(fingerprint_cfg, dict) else None
        return FingerprintOptions.generate(
            seed=int(seed) if seed is not None else None,
            locale=str(
                fingerprint_cfg.get("locale", "zh-CN")
                if isinstance(fingerprint_cfg, dict)
                else "zh-CN"
            ),
            timezone_id=str(
                fingerprint_cfg.get("timezone_id", "Asia/Shanghai")
                if isinstance(fingerprint_cfg, dict)
                else "Asia/Shanghai"
            ),
        )

    def _binding(self):
        return (
            binding_from_fetch_config(self.config)
            or binding_from_fetch_config(self.fetch_config)
            or binding_from_fetch_config(self.browser_config)
        )

    def _open_browser(self) -> BrowserSession:
        proxy = self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        session = BrowserSession(
            headless=bool(self.browser_config.get("headless", True)),
            proxy=proxy,
            user_data_dir=self.browser_config.get("user_data_dir"),
            fingerprint=self._fingerprint(),
            storage_state=self.browser_config.get("storage_state"),
            action_interval=float(self.browser_config.get("action_interval", 0.0)),
            action_jitter=float(self.browser_config.get("action_jitter", 0.2)),
            engine=self.browser_config.get("engine", "playwright"),
            fingerprint_binding=self._binding(),
            cloudflare_config=self.cloudflare_config,
            captcha_solver=self._cloudflare_captcha_solver(),
        )
        session.start()
        cookies_path = self.browser_config.get("cookies_path")
        if cookies_path and Path(cookies_path).exists():
            session.load_cookies(cookies_path)
        login = self.browser_config.get("login")
        if isinstance(login, dict) and login.get("url"):
            login_url = str(login["url"])
            username = str(login.get("username", ""))
            password = str(login.get("password", ""))
            username_selector = str(login.get("username_selector", "") or "")
            password_selector = str(login.get("password_selector", "") or "")
            submit_selector = str(login.get("submit_selector", "") or "")
            auto_login = bool(login.get("auto", not (username_selector and password_selector)))
            if auto_login:
                session.auto_login(
                    login_url,
                    username,
                    password,
                    auto_captcha_solver=self.captcha_solver,
                    captcha_image_paths=login.get("captcha_image_paths"),
                    max_captcha_retries=int(login.get("max_captcha_retries", 2)),
                    success_selector=login.get("success_selector"),
                    success_markers=tuple(login.get("success_markers") or ()),
                    timeout=float(login.get("timeout", 30000)),
                    storage_state=login.get("storage_state")
                    or self.browser_config.get("storage_state"),
                    cookies_path=login.get("cookies_path") or cookies_path,
                )
            else:
                session.login(
                    login_url,
                    username,
                    password,
                    username_selector,
                    password_selector,
                    submit_selector,
                    auto_captcha_solver=self.captcha_solver,
                    captcha_image_paths=login.get("captcha_image_paths"),
                    max_captcha_retries=int(login.get("max_captcha_retries", 2)),
                    success_selector=login.get("success_selector"),
                    success_markers=tuple(login.get("success_markers") or ()),
                    timeout=float(login.get("timeout", 30000)),
                )
        return session

    def _cloudflare_captcha_solver(self) -> Any | None:
        if self.captcha_solver is None:
            return None
        solver = getattr(self.captcha_solver, "solver", None)
        if solver is not None and hasattr(solver, "solve_turnstile"):
            return solver
        return self.captcha_solver if hasattr(self.captcha_solver, "solve_turnstile") else None

    def _capture_browser_page(self, session: BrowserSession, url: str) -> PageCapture:
        capture_cfg = self.browser_config.get("network_capture") or {}
        options = NetworkCaptureOptions(
            capture_types=tuple(
                capture_cfg.get("capture_types") or NetworkCaptureOptions().capture_types
            ),
            include_bodies=bool(capture_cfg.get("include_bodies", True)),
            include_headers=bool(capture_cfg.get("include_headers", False)),
            max_body_bytes=int(capture_cfg.get("max_body_bytes", 2 * 1024 * 1024)),
        )
        session.start_capture(options)
        html = ""
        try:
            session.goto(url, timeout=float(self.browser_config.get("goto_timeout", 30000)))
            if self.browser_config.get("network_idle", True):
                with suppress(Exception):
                    session.page.wait_for_load_state(
                        "networkidle",
                        timeout=float(self.browser_config.get("network_idle_timeout", 15000)),
                    )
            if self.cloudflare_config.get("enabled", True):
                handler = CloudflareChallengeHandler(
                    CloudflareChallengeConfig.from_dict(self.cloudflare_config),
                    captcha_solver=self._cloudflare_captcha_solver(),
                )
                cloudflare_result = handler.run(session.page, session.context, url)
                self._last_cloudflare_result = cloudflare_result
                if cloudflare_result.passed and (
                    self._cloudflare_result is None or cloudflare_result.clearance_cookie
                ):
                    self._cloudflare_result = cloudflare_result
                elif self.security_config.get("auto_handle", True) and self.browser_config.get(
                    "wait_for_challenge", True
                ):
                    session.wait_for_challenge(
                        timeout=float(self.browser_config.get("challenge_timeout", 60000))
                    )
            elif self.security_config.get("auto_handle", True) and self.browser_config.get(
                "wait_for_challenge", True
            ):
                session.wait_for_challenge(
                    timeout=float(self.browser_config.get("challenge_timeout", 60000))
                )
            if self.captcha_solver is not None:
                session.solve_captchas_auto(
                    self.captcha_solver,
                    page_url=url,
                    max_challenges=int((self.config.get("captcha") or {}).get("max_challenges", 5)),
                )
            html = session.page.content()
        finally:
            network = session.stop_capture()
        security = None
        if self.security_config.get("enabled", True):
            report = detect_security_mechanisms(
                200,
                url,
                {},
                html,
                html=html,
                page_url=url,
            )
            security = report.to_dict()
        return PageCapture(
            url=url,
            html=html,
            network=network,
            analysis=analyze_page(html, base_url=url),
            security=security,
        )

    def _capture_http_page(self, url: str) -> PageCapture:
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        session = create_fetch_session(
            self.fetch_config,
            headers=self.api_config.get("headers"),
            proxy=proxy,
            proxy_pool=self.proxy_pool,
            captcha_solver=self._cloudflare_captcha_solver(),
            min_interval=float(self.api_config.get("min_interval", 0.0)),
            max_retries=int(self.api_config.get("max_retries", 0)),
            backoff_base=float(self.api_config.get("backoff_base", 0.5)),
            backoff_max=float(self.api_config.get("backoff_max", 30.0)),
        )
        if self._api_cookies:
            session.load_cookies(self._api_cookies)
        try:
            body, status, headers = session.get_bytes_with_meta(url)
        finally:
            session.close()
        html = body.decode("utf-8", "replace")
        security = None
        if self.security_config.get("enabled", True):
            report = detect_security_mechanisms(
                status,
                url,
                headers,
                html,
                html=html,
                page_url=url,
            )
            security = report.to_dict()
        return PageCapture(
            url=url,
            html=html,
            network=[],
            analysis=analyze_page(html, base_url=url),
            security=security,
        )

    def _deep_crawl(self) -> Any:
        crawl = self.crawl_config
        seeds = [str(item) for item in crawl.get("seeds") or self.pages]
        browser_mode = bool(self.browser_config.get("enabled", False))
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        min_interval = float(crawl.get("min_interval", self.api_config.get("min_interval", 0.0)))
        max_retries = int(crawl.get("max_retries", self.api_config.get("max_retries", 0)))
        session = create_fetch_session(
            self.fetch_config,
            headers=self.api_config.get("headers"),
            proxy=proxy,
            proxy_pool=self.proxy_pool,
            captcha_solver=self._cloudflare_captcha_solver(),
            min_interval=min_interval,
            max_retries=max_retries,
            backoff_base=float(crawl.get("backoff_base", self.api_config.get("backoff_base", 0.5))),
            backoff_max=float(crawl.get("backoff_max", self.api_config.get("backoff_max", 30.0))),
        )
        if self._api_cookies:
            session.load_cookies(self._api_cookies)
        config = CrawlConfig.from_dict(
            {
                "seeds": seeds,
                "max_depth": int(crawl.get("max_depth", 2)),
                "max_pages": int(crawl.get("max_pages", 50)),
                "same_host": bool(crawl.get("same_host", True)),
                "include": list(crawl.get("include") or []),
                "exclude": list(crawl.get("exclude") or []),
                "sitemap": bool(crawl.get("sitemap", True)),
                "respect_robots": bool(crawl.get("respect_robots", True)),
                "skip_blocked": bool(
                    crawl.get(
                        "skip_blocked",
                        self.security_config.get("skip_blocked", True),
                    )
                ),
                "user_agent": str(
                    crawl.get("user_agent")
                    or self.api_config.get("user_agent")
                    or "MediaPipeline/1.0"
                ),
                "headers": dict(self.api_config.get("headers") or {}),
                "cookies": self._api_cookies,
                "proxy": proxy,
                "proxy_pool": self.proxy_pool,
                "min_interval": min_interval,
                "max_retries": max_retries,
                "fetch_backend": self.fetch_config.get(
                    "backend",
                    self.api_config.get("backend", "standard"),
                ),
                "fetch_auto_install": self.fetch_config.get("auto_install"),
                "fetch_browser": self.fetch_config.get("browser") or self.browser_config,
            }
        )
        self._browser_captures = {}
        if browser_mode:
            self.session = self._open_browser()
        try:
            crawler = DeepCrawler(
                config,
                session=session,
                fetch_page=self._crawl_fetch_browser if browser_mode else None,
            )
            result = crawler.crawl()
        finally:
            session.close()
            if browser_mode and self.session is not None:
                if self.session.context is not None:
                    self._browser_cookies = list(self.session.context.cookies())
                cookies_path = self.browser_config.get("cookies_path")
                if cookies_path:
                    self.session.save_cookies(cookies_path)
                self.session.close()
                self.session = None
        self.crawl_result = result
        return result

    def _crawl_fetch_browser(self, url: str) -> CrawledResponse:
        if self.session is None:
            raise RuntimeError("browser session is not open")
        capture = self._capture_browser_with_rotation(url)
        self._browser_captures[url] = capture
        return CrawledResponse(
            url=url,
            status=200,
            headers={},
            body=capture.html.encode("utf-8"),
        )

    def _crawl_page_to_capture(self, page: Any) -> PageCapture:
        capture = self._browser_captures.get(page.url)
        if capture is not None:
            return capture
        return PageCapture(
            url=page.url,
            html=page.html,
            network=[],
            analysis=page.analysis,
            security=page.security.to_dict() if page.security else None,
        )

    def _rotate_browser_session(self, old_session: BrowserSession) -> BrowserSession:
        if self.proxy_pool is not None and old_session.proxy:
            self.proxy_pool.report_failure(old_session.proxy)
        if old_session.context is not None:
            self._browser_cookies = list(old_session.context.cookies())
        cookies_path = self.browser_config.get("cookies_path")
        if cookies_path:
            old_session.save_cookies(cookies_path)
        old_session.close()
        return self._open_browser()

    def _capture_browser_with_rotation(self, url: str) -> PageCapture:
        if self.session is None:
            raise RuntimeError("browser session is not open")
        capture = self._capture_browser_page(self.session, url)
        max_rotations = int(self.cloudflare_config.get("max_rotation_attempts", 1))
        for _ in range(max(0, max_rotations)):
            result = self._last_cloudflare_result
            if result is None or not result.needs_new_session or self.proxy_pool is None:
                break
            self.session = self._rotate_browser_session(self.session)
            self._last_cloudflare_result = None
            capture = self._capture_browser_page(self.session, url)
        return capture

    def _escalate_blocked_to_browser(self) -> None:
        security = self.security_config
        if not security.get("escalate_to_browser", True):
            return
        if self.browser_config.get("enabled", False):
            return
        blocked = [
            index
            for index, capture in enumerate(self.captures)
            if capture.security and capture.security.get("blocked")
        ]
        if not blocked:
            return
        stealth_engine = self.browser_config.get("stealth_engine")
        if not stealth_engine:
            configured_engine = str(
                self.browser_config.get("engine", "playwright") or "playwright"
            ).lower()
            if configured_engine not in {"playwright", "patchright"}:
                stealth_engine = configured_engine
        if stealth_engine:
            self._stealth_escalate_blocked(blocked, str(stealth_engine))
            return
        try:
            session = self._open_browser()
        except Exception:
            return
        self.session = session
        try:
            for index in blocked:
                replacement = self._capture_browser_with_rotation(self.captures[index].url)
                self.captures[index] = replacement
                self._browser_captures[replacement.url] = replacement
        finally:
            if self.session is not None:
                if self.session.context is not None:
                    self._browser_cookies = list(self.session.context.cookies())
                cookies_path = self.browser_config.get("cookies_path")
                if cookies_path:
                    self.session.save_cookies(cookies_path)
                self.session.close()
                self.session = None

    def _stealth_escalate_blocked(
        self,
        blocked: list[int],
        engine: str,
    ) -> None:
        from stealth_browser import solve_cloudflare_with_stealth_browser

        proxy = self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        for index in blocked:
            url = self.captures[index].url
            alt_config = self.browser_config.get("alternate")
            if alt_config is None or alt_config.get("enabled", True):
                try:
                    alt_result = try_alternate_access(
                        url,
                        {"alternate": alt_config if isinstance(alt_config, dict) else {}},
                        proxy=proxy,
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
                        security = None
                        if self.security_config.get("enabled", True):
                            report = detect_security_mechanisms(
                                alt_result.status,
                                alt_result.url,
                                alt_result.headers,
                                alt_result.body,
                                html=alt_result.body,
                                page_url=alt_result.url,
                            )
                            security = report.to_dict()
                        capture = PageCapture(
                            url=url,
                            html=alt_result.body,
                            network=[],
                            analysis=analyze_page(alt_result.body, base_url=alt_result.url),
                            security=security,
                        )
                        self.captures[index] = capture
                        self._browser_captures[url] = capture
                        continue
                except Exception:
                    pass
            try:
                result = solve_cloudflare_with_stealth_browser(
                    url,
                    engine=engine,
                    engine_order=self.browser_config.get("stealth_engine_order"),
                    proxy=proxy,
                    browser_path=self.browser_config.get("browser_path"),
                    headless=bool(self.browser_config.get("headless", True)),
                    headless_fallback=bool(
                        self.browser_config.get("headless_fallback", True)
                    ),
                    storage_state=self.browser_config.get("storage_state"),
                    timeout_ms=float(self.browser_config.get("challenge_timeout", 60000)),
                    auto_install=bool(self.browser_config.get("auto_install", True)),
                    max_attempts=int(
                        self.browser_config.get(
                            "challenge_attempts",
                            self.browser_config.get("max_attempts", 2),
                        )
                    ),
                    retry_delay=float(self.browser_config.get("retry_delay", 2.0)),
                    rotate_proxy_on_fail=bool(
                        self.browser_config.get("rotate_proxy_on_fail", True)
                    ),
                    proxy_pool=self.proxy_pool,
                )
            except Exception:
                continue
            if result is None or not result.html:
                continue
            cookies = list(result.cookies or [])
            self._api_cookies.extend(cookies)
            self._browser_cookies.extend(cookies)
            security = None
            if self.security_config.get("enabled", True):
                report = detect_security_mechanisms(
                    200,
                    url,
                    {},
                    result.html,
                    html=result.html,
                    page_url=url,
                )
                security = report.to_dict()
            capture = PageCapture(
                url=url,
                html=result.html,
                network=[],
                analysis=analyze_page(result.html, base_url=url),
                security=security,
            )
            self.captures[index] = capture
            self._browser_captures[url] = capture

    def _download_hls_streams(self) -> None:
        media_config = self.config.get("media") or self.config.get("hls") or {}
        if not media_config.get("enabled", False):
            return
        from hls_client import HLSClient

        urls: list[str] = []
        for capture in self.captures:
            if hasattr(capture, "hls_urls"):
                urls.extend(capture.hls_urls())
        urls.extend(str(url) for url in media_config.get("urls") or [])
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if url and url not in seen:
                seen.add(url)
                unique.append(url)
        if not unique:
            return
        output_dir = Path(media_config.get("output_dir", "media"))
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        session = create_fetch_session(
            self.fetch_config,
            headers=self.api_config.get("headers"),
            proxy=proxy,
            proxy_pool=self.proxy_pool,
            min_interval=float(self.api_config.get("min_interval", 0.0)),
            max_retries=int(
                media_config.get(
                    "max_retries",
                    self.api_config.get("max_retries", 2),
                )
            ),
        )
        cookies = list(self._api_cookies) + list(self._browser_cookies)
        if cookies:
            session.load_cookies(cookies)
        client = HLSClient(
            session=session,
        )
        try:
            preferred_height = media_config.get("preferred_height")
            max_bandwidth = media_config.get("max_bandwidth")
            for url in unique:
                try:
                    result = client.download(
                        url,
                        output_dir,
                        preferred_height=(
                            int(preferred_height) if preferred_height is not None else None
                        ),
                        max_bandwidth=(
                            int(max_bandwidth) if max_bandwidth is not None else None
                        ),
                        include_segments=bool(media_config.get("include_segments", True)),
                        combine=bool(media_config.get("combine", True)),
                        decrypt=bool(media_config.get("decrypt", True)),
                        overwrite=bool(media_config.get("overwrite", False)),
                    )
                    self.hls_results.append(result.to_dict())
                except Exception as exc:
                    self.hls_results.append({"url": url, "error": str(exc)})
        finally:
            client.close()
            session.close()

    def collect(self) -> list[PageCapture]:
        if self.crawl_config.get("enabled", False):
            result = self._deep_crawl()
            self.pages = [page.url for page in result.pages]
            self.captures = [self._crawl_page_to_capture(page) for page in result.pages]
            self._escalate_blocked_to_browser()
            return self.captures
        if self.browser_config.get("enabled", False):
            self.session = self._open_browser()
            try:
                for url in self.pages:
                    self.captures.append(self._capture_browser_with_rotation(url))
            finally:
                if self.session.context is not None:
                    self._browser_cookies = list(self.session.context.cookies())
                cookies_path = self.browser_config.get("cookies_path")
                if cookies_path:
                    self.session.save_cookies(cookies_path)
                self.session.close()
        else:
            for url in self.pages:
                self.captures.append(self._capture_http_page(url))
        self._escalate_blocked_to_browser()
        return self.captures

    def discover(self) -> list[ApiSpec]:
        self.specs = []
        for capture in self.captures:
            if capture.security and capture.security.get("blocked"):
                continue
            self.specs.extend(
                build_api_specs(
                    capture,
                    include_captured=bool(self.api_config.get("include_captured", True)),
                    include_static=bool(self.api_config.get("include_static", True)),
                    max_specs=int(self.api_config.get("max_specs", 200)),
                )
            )
        seen: set[tuple[str, str]] = set()
        deduped: list[ApiSpec] = []
        for spec in self.specs:
            key = (spec.method.upper(), spec.url)
            if key not in seen:
                seen.add(key)
                deduped.append(spec)
        self.specs = deduped
        pagination_cfg = self.api_config.get("pagination")
        if not (
            isinstance(pagination_cfg, dict) and pagination_cfg.get("type")
        ) and self.api_config.get("auto_pagination", True):
            from api_analyzer import analyze_captures

            inferred = analyze_captures(self.captures).pagination
            if inferred:
                pagination_cfg = inferred
        if isinstance(pagination_cfg, dict) and pagination_cfg.get("type"):
            for spec in self.specs:
                spec.pagination = dict(pagination_cfg)
        return self.specs

    def fetch(self) -> list[dict[str, Any]]:
        headers = dict(self.api_config.get("headers") or {})
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        proxy_pool = self.proxy_pool
        cookies = list(self._browser_cookies or []) + list(self._api_cookies)
        if self._cloudflare_result is not None and self._cloudflare_result.passed:
            if self._cloudflare_result.user_agent:
                headers["User-Agent"] = self._cloudflare_result.user_agent
            if self._cloudflare_result.clearance_cookie:
                cookies.append(self._cloudflare_result.clearance_cookie)
                proxy = self._cloudflare_result.proxy or proxy
                proxy_pool = None
        client = ApiClient(
            headers=headers,
            proxy=proxy,
            proxy_pool=proxy_pool,
            min_interval=float(self.api_config.get("min_interval", 0.0)),
            jitter=float(self.api_config.get("jitter", 0.2)),
            max_retries=int(self.api_config.get("max_retries", 0)),
            backoff_base=float(self.api_config.get("backoff_base", 0.5)),
            backoff_max=float(self.api_config.get("backoff_max", 30.0)),
            cookies=cookies,
            backend=self.fetch_config.get(
                "backend",
                self.api_config.get("backend", "standard"),
            ),
            auto_install=self.fetch_config.get("auto_install"),
            browser_config=self.fetch_config.get("browser") or self.browser_config,
            header_fingerprint=self.fetch_config.get("header_fingerprint", "chrome"),
            fingerprint_binding=self._binding(),
        )
        try:
            results = client.fetch_all(
                self.specs, concurrency=int(self.api_config.get("concurrency", 1))
            )
        finally:
            client.close()
        records: list[dict[str, Any]] = []
        self.api_security_findings = 0
        for result in results:
            if result.error:
                print(
                    f"API fetch failed: {result.spec.method} {result.spec.url}: {result.error}",
                    file=sys.stderr,
                )
                continue
            if result.security and result.security.get("blocked"):
                self.api_security_findings += 1
                print(
                    f"API fetch blocked: {result.spec.method} {result.spec.url}: "
                    f"{result.security.get('primary_kind')}",
                    file=sys.stderr,
                )
                continue
            records.extend(_unwrap_data(result.data))
        return records

    def run(
        self,
        progress: Callable[[str, float, str], None] | None = None,
    ) -> dict[str, Any]:
        def report(stage: str, percent: float, message: str) -> None:
            if progress is not None:
                progress(stage, percent, message)

        report("collect", 0.1, f"collecting {len(self.pages)} page(s)")
        self.collect()
        report("hls", 0.25, "processing detected HLS streams")
        self._download_hls_streams()
        report("discover", 0.4, "analyzing page/API endpoints")
        self.discover()
        manifest_output = self.api_config.get("manifest_output")
        if manifest_output:
            from api_analyzer import analyze_captures, save_manifest

            manifest = analyze_captures(
                self.captures,
                include_secrets=bool(self.api_config.get("include_secrets", False)),
            )
            save_manifest(manifest, manifest_output)
            report("manifest", 0.5, f"API manifest written to {manifest_output}")
        report("fetch", 0.55, f"fetching {len(self.specs)} API spec(s)")
        records = self.fetch()
        processing = self.config.get("processing") or {}
        report("process", 0.8, f"processing {len(records)} raw record(s)")
        processed = process_records(records, processing)
        report("save", 0.95, f"saving {len(processed)} record(s)")
        save_records(processed, self.output)
        report("done", 1.0, "web data pipeline finished")
        security_findings = sum(
            len(capture.security.get("findings", []))
            for capture in self.captures
            if capture.security and capture.security.get("findings")
        )
        self.last_summary = {
            "pages": len(self.pages),
            "captures": len(self.captures),
            "crawl_pages": len(self.crawl_result.pages) if self.crawl_result else 0,
            "api_specs": len(self.specs),
            "manifest_output": str(manifest_output) if manifest_output else None,
            "raw_records": len(records),
            "processed_records": len(processed),
            "security_findings": security_findings + self.api_security_findings,
            "crawl_summary": self.crawl_result.summary() if self.crawl_result else None,
            "cloudflare": (self._cloudflare_result.to_dict() if self._cloudflare_result else None),
            "hls_downloads": sum(1 for item in self.hls_results if "error" not in item),
            "hls_errors": sum(1 for item in self.hls_results if "error" in item),
            "hls_output_dir": str(
                (self.config.get("media") or self.config.get("hls") or {}).get(
                    "output_dir",
                    "media",
                )
            ),
            "fetch_backend": self.fetch_config.get(
                "backend",
                self.api_config.get("backend", "standard"),
            ),
            "output": str(self.output),
        }
        return self.last_summary

    def final_summary_report(self, summary: dict[str, Any] | None = None) -> dict[str, Any]:
        """Build the end-of-run report with save paths and per-resource status."""
        from run_summary import pipeline_report

        resources: list[dict[str, Any]] = []
        for capture in self.captures:
            security = capture.security or {}
            resources.append(
                {
                    "kind": "page",
                    "url": capture.url,
                    "status": "blocked" if security.get("blocked") else "success",
                    "path": None,
                    "error": None,
                    "blocked": bool(security.get("blocked")),
                    "security": security,
                }
            )
        for item in self.hls_results:
            error = item.get("error")
            resources.append(
                {
                    "kind": "hls",
                    "url": item.get("url"),
                    "path": item.get("combined_path") or item.get("path"),
                    "size": item.get("total_bytes") or item.get("size"),
                    "status": "failed" if error else "success",
                    "error": error,
                    "details": item,
                }
            )
        media_output = (
            self.config.get("media") or self.config.get("hls") or {}
        ).get("output_dir")
        return pipeline_report(
            output=self.output,
            manifest_output=self.api_config.get("manifest_output"),
            media_output=media_output,
            resources=resources,
            summary=summary or self.last_summary,
        )


class _SelfTestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/list":
            body = (
                b"<!doctype html><html><head><title>list</title></head><body>"
                b'<script>fetch("/api/items?page=1"); axios.get("/api/config");</script>'
                b"</body></html>"
            )
        elif self.path.startswith("/api/items"):
            body = json.dumps(
                {
                    "items": [
                        {"id": 1, "name": "Alpha", "price": 10},
                        {"id": 2, "name": "Beta", "price": 20},
                    ]
                }
            ).encode("utf-8")
        elif self.path.startswith("/api/config"):
            body = json.dumps({"enabled": True}).encode("utf-8")
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _self_test() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "result.json"
            config = {
                "pages": [f"{base}/list"],
                "api": {
                    "min_interval": 0.0,
                    "max_retries": 0,
                    "include_static": True,
                    "include_captured": False,
                },
                "processing": {
                    "steps": [
                        {
                            "op": "filter",
                            "params": {
                                "conditions": [{"field": "price", "op": "gte", "value": 10}]
                            },
                        },
                        {"op": "select", "params": {"fields": ["id", "name"]}},
                        {"op": "sort", "params": {"keys": [{"field": "id", "desc": False}]}},
                    ]
                },
            }
            config_path = Path(tmp) / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            pipeline = WebDataPipeline(_read_config(config_path), output=out)
            summary = pipeline.run()
            assert summary["api_specs"] >= 2, summary
            assert summary["processed_records"] == 2, summary
            records = load_records(out)
            assert records == [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}], records
    finally:
        server.shutdown()
        server.server_close()
    print("web_data_pipeline self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the web data pipeline")
    parser.add_argument("--config", help="JSON pipeline config")
    parser.add_argument("--output", help="override config output path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.config:
        parser.error("--config is required unless --self-test is used")
    config = _read_config(args.config)
    pipeline = WebDataPipeline(config, output=args.output)
    summary = pipeline.run()
    from run_summary import print_report, write_report

    report = pipeline.final_summary_report(summary)
    summary_output = config.get("summary_output")
    if summary_output:
        write_report(report, summary_output)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
