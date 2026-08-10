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
import urllib.parse
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

from alternate_access import try_alternate_access
from api_client import ApiClient, ApiSpec, build_api_specs
from browser_session import BrowserSession, FingerprintOptions, NetworkCaptureOptions, PageCapture
from captcha_solver import (
    AutoCaptchaSolver,
    CaptchaSolver,
    ManualCaptchaSolver,
    OcrCaptchaSolver,
    build_captcha_provider,
)
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
    if not captcha or captcha.get("enabled") is False:
        return None
    manual = ManualCaptchaSolver()
    solver = build_captcha_provider(captcha)
    if solver is None:
        if captcha.get("allow_manual_fallback", False):
            return AutoCaptchaSolver(
                solver=CaptchaSolver(api_key=""),
                allow_manual_fallback=True,
                manual_solver=manual,
            )
        if captcha.get("ocr", True):
            return AutoCaptchaSolver(
                solver=CaptchaSolver(api_key=""),
                manual_solver=manual,
                ocr_solver=OcrCaptchaSolver(
                    auto_install=bool(captcha.get("auto_install_ocr", True)),
                    priority=captcha.get("ocr_priority"),
                ),
            )
        return None
    return AutoCaptchaSolver(
        solver=solver,
        allow_manual_fallback=bool(captcha.get("allow_manual_fallback", False)),
        manual_solver=manual,
    )


def _captcha_mode(captcha: dict[str, Any], solver: AutoCaptchaSolver | None) -> str:
    if not captcha or captcha.get("enabled") is False or solver is None:
        return "off"
    if solver.has_service:
        return "provider"
    if solver.allow_manual_fallback and solver.manual_solver is not None:
        return "manual"
    return "ocr"


class WebDataPipeline:
    """Run one configured page/API collection + processing job."""

    def __init__(
        self,
        config: dict[str, Any],
        output: str | Path | None = None,
    ) -> None:
        self.config = dict(config)
        self.mode = str(self.config.get("mode") or "auto").lower()
        if self.mode == "auto":
            fetch = dict(self.config.get("fetch") or {})
            fetch.setdefault("backend", "auto")
            fetch.setdefault("fingerprint_binding", "chrome124")
            self.config["fetch"] = fetch
            browser = dict(self.config.get("browser") or {})
            browser.setdefault("engine", "auto")
            browser.setdefault("headless", True)
            self.config["browser"] = browser
            captcha = dict(self.config.get("captcha") or {})
            captcha.setdefault("ocr", True)
            captcha.setdefault("auto_install_ocr", True)
            self.config["captcha"] = captcha
        config = self.config
        self.output = Path(output) if output else Path(config.get("output", "output.json"))
        self.browser_config = config.get("browser") or {}
        self.api_config = config.get("api") or {}
        self.security_config = config.get("security") or {}
        self.crawl_config = config.get("crawl") or config.get("subpages") or {}
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
        self.captcha_mode = _captcha_mode(config.get("captcha") or {}, self.captcha_solver)
        self.session: BrowserSession | None = None
        self.captures: list[PageCapture] = []
        self.specs: list[ApiSpec] = []
        self._browser_cookies: list[dict[str, Any]] = []
        self.hls_results: list[dict[str, Any]] = []
        self.media_assets: list[dict[str, Any]] = []
        self.last_summary: dict[str, Any] | None = None
        self.augment_stats: Any = None
        self.site_index: dict[str, Any] | None = None
        self.stream_specs: list[ApiSpec] = []
        self.chain_rounds = 0
        self.chain_new_specs = 0

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
            container=bool(self.browser_config.get("container", False)),
            container_dir=self.browser_config.get("container_dir"),
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
        if self.captcha_solver is None or not self.captcha_solver.has_service:
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
            if self.browser_config.get("trigger_events"):
                session.trigger_page_events(
                    event_names=tuple(
                        self.browser_config.get("trigger_events") or ("click",)
                    ),
                    max_actions=int(self.browser_config.get("max_event_actions", 20)),
                )
                with suppress(Exception):
                    session.page.wait_for_load_state(
                        "networkidle",
                        timeout=float(
                            self.browser_config.get("event_network_timeout", 5000)
                        ),
                    )
            storage = (
                session.capture_storage()
                if self.browser_config.get("capture_storage", False)
                else None
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
            storage=storage,
        )

    def _capture_http_page(self, url: str) -> PageCapture:
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        session = create_fetch_session(
            self._fetch_config_for_url(url),
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
            try:
                from captcha_solver import detect_captchas

                challenges = detect_captchas(html, page_url=url)
                if challenges:
                    security["auto_captcha"] = True
                    security["captcha_kinds"] = sorted(
                        {challenge.kind for challenge in challenges}
                    )
            except Exception:
                pass
        return PageCapture(
            url=url,
            html=html,
            network=[],
            analysis=analyze_page(html, base_url=url),
            security=security,
        )

    def _fetch_config_for_url(self, url: str) -> dict[str, Any]:
        host = urllib.parse.urlsplit(url).hostname or ""
        if host in {"127.0.0.1", "localhost", "::1", "0.0.0.0"}:
            cfg = dict(self.fetch_config)
            cfg["backend"] = "standard"
            return cfg
        return self.fetch_config

    def _deep_crawl(self) -> Any:
        crawl = self.crawl_config
        seeds = [str(item) for item in crawl.get("seeds") or self.pages]
        fetch_config = (
            self._fetch_config_for_url(seeds[0]) if seeds else self.fetch_config
        )
        browser_mode = bool(self.browser_config.get("enabled", False))
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        min_interval = float(crawl.get("min_interval", self.api_config.get("min_interval", 0.0)))
        max_retries = int(crawl.get("max_retries", self.api_config.get("max_retries", 0)))
        session = create_fetch_session(
            fetch_config,
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
                "collect_param_hints": bool(crawl.get("collect_param_hints", True)),
                "max_param_hints": int(crawl.get("max_param_hints", 200)),
                "crawl_api_endpoints": bool(crawl.get("crawl_api_endpoints", False)),
                "max_api_calls": int(crawl.get("max_api_calls", 100)),
                "api_max_payload_bytes": int(crawl.get("api_max_payload_bytes", 262144)),
                "block_retries": int(crawl.get("block_retries", 2)),
                "block_retry_delay": float(crawl.get("block_retry_delay", 2.0)),
                "block_retry_backoff": float(crawl.get("block_retry_backoff", 2.0)),
                "rotate_proxy_on_block": bool(crawl.get("rotate_proxy_on_block", True)),
                "alternate_on_block": bool(crawl.get("alternate_on_block", True)),
                "browser_on_block": bool(crawl.get("browser_on_block", False)),
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
            if capture.security
            and (
                capture.security.get("blocked")
                or capture.security.get("auto_captcha")
            )
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
                    max_engines_per_round=int(
                        self.browser_config.get("max_engines_per_round", 3)
                    ),
                    initial_cookies=(self._api_cookies or self._browser_cookies) or None,
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
        urls: list[str] = []
        for capture in self.captures:
            if hasattr(capture, "hls_urls"):
                urls.extend(capture.hls_urls())
            if hasattr(capture, "dash_urls"):
                urls.extend(capture.dash_urls())
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
        try:
            preferred_height = media_config.get("preferred_height")
            max_bandwidth = media_config.get("max_bandwidth")
            client = None
            for url in unique:
                is_dash = ".mpd" in url.lower() or "format=mpd" in url.lower()
                try:
                    if is_dash:
                        from dash_client import DASHClient

                        client = DASHClient(session=session)
                    else:
                        from hls_client import HLSClient

                        client = HLSClient(session=session)
                    if is_dash:
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
                            save_manifest=True,
                            overwrite=bool(media_config.get("overwrite", False)),
                        )
                    else:
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
                    if client is not None:
                        client.close()
                    client = None
        finally:
            session.close()

    def _download_media_assets(self) -> None:
        media_config = self.config.get("media") or self.config.get("hls") or {}
        if not media_config.get("enabled", False):
            return
        if not media_config.get("download_assets", True):
            return
        from media_crawler import _classify_media_url
        from resource_downloader import ResourceDownloader

        candidates: dict[str, str] = {}

        def add_candidate(url: str, kind: str) -> None:
            if url and kind not in {"hls", "dash", "smooth"}:
                candidates.setdefault(url, kind)

        for capture in self.captures:
            analysis = capture.analysis
            if analysis is None:
                continue
            media = analysis.media
            if media is not None:
                for url in media.images:
                    add_candidate(url, "image")
                for url in media.audios:
                    add_candidate(url, "audio")
                for url in media.videos:
                    add_candidate(url, "video")
                for url in media.links:
                    kind = _classify_media_url(url)
                    if kind:
                        add_candidate(url, kind)
            assets = getattr(analysis, "assets", None) or {}
            for kind, urls in assets.items():
                for url in urls:
                    if kind == "images":
                        add_candidate(url, "image")
                    elif kind == "fonts":
                        add_candidate(url, "font")
                    elif kind in {"css", "js", "data"}:
                        add_candidate(url, kind)
                    elif kind == "documents":
                        detected = _classify_media_url(url)
                        if detected:
                            add_candidate(url, detected)

        max_assets = int(media_config.get("max_assets", 200))
        selected = list(candidates.items())[:max_assets]
        if not selected:
            return
        output_dir = Path(media_config.get("output_dir", "media"))
        proxy = self.api_config.get("proxy") or self.browser_config.get("proxy")
        if not proxy and self.proxy_pool is not None:
            proxy = self.proxy_pool.get_proxy()
        for url, kind in selected:
            session = create_fetch_session(
                self.fetch_config,
                headers=self.api_config.get("headers"),
                proxy=proxy,
                proxy_pool=self.proxy_pool,
                min_interval=float(self.api_config.get("min_interval", 0.0)),
                max_retries=int(media_config.get("max_retries", 2)),
                timeout=float(media_config.get("timeout", 30.0)),
            )
            try:
                result = ResourceDownloader(
                    session,
                    timeout=float(media_config.get("timeout", 30.0)),
                ).download(
                    url,
                    output_dir / kind,
                    overwrite=bool(media_config.get("overwrite", False)),
                    resume=bool(media_config.get("resume_downloads", True)),
                )
                record = result.to_dict()
                record["kind"] = kind
                self.media_assets.append(record)
            except Exception as exc:
                self.media_assets.append({"url": url, "kind": kind, "error": str(exc)})
            finally:
                session.close()

    def collect(self) -> list[PageCapture]:
        if self.crawl_config.get("enabled", bool(self.config.get("subpages"))):
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
        seen: set[tuple[str, str, str]] = set()
        deduped: list[ApiSpec] = []
        for spec in self.specs:
            body_key = (
                json.dumps(spec.body, sort_keys=True, ensure_ascii=False, default=str)
                if spec.body is not None
                else ""
            )
            key = (spec.method.upper(), spec.url, body_key)
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
        augment_cfg = self.api_config.get("augment") or {}
        if augment_cfg.get("enabled", self.api_config.get("auto_augment_params", False)):
            from param_augmenter import augment_specs

            augment_config = dict(augment_cfg)
            augment_config.setdefault("max_specs", int(self.api_config.get("max_specs", 500)))
            self.specs, self.augment_stats = augment_specs(
                self.specs,
                self.captures,
                augment_config,
            )
        self.stream_specs = [
            spec for spec in self.specs if self._is_stream_spec(spec)
        ]
        return self.specs

    def _new_api_client(self) -> ApiClient:
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
        fetch_cfg = self._fetch_config_for_url(self.specs[0].url) if self.specs else self.fetch_config
        client = ApiClient(
            headers=headers,
            proxy=proxy,
            proxy_pool=proxy_pool,
            min_interval=float(self.api_config.get("min_interval", 0.0)),
            jitter=float(self.api_config.get("jitter", 0.2)),
            max_retries=int(self.api_config.get("max_retries", 0)),
            backoff_base=float(self.api_config.get("backoff_base", 0.5)),
            backoff_max=float(self.api_config.get("backoff_max", 30.0)),
            block_retries=int(self.api_config.get("block_retries", 2)),
            block_retry_delay=float(self.api_config.get("block_retry_delay", 2.0)),
            block_retry_backoff=float(self.api_config.get("block_retry_backoff", 2.0)),
            rotate_proxy_on_block=bool(
                self.api_config.get("rotate_proxy_on_block", True)
            ),
            cookies=cookies,
            backend=fetch_cfg.get(
                "backend",
                self.api_config.get("backend", "standard"),
            ),
            auto_install=fetch_cfg.get("auto_install"),
            browser_config=fetch_cfg.get("browser") or self.browser_config,
            header_fingerprint=fetch_cfg.get("header_fingerprint", "chrome"),
            fingerprint_binding=(
                binding_from_fetch_config(fetch_cfg) or self._binding()
            ),
        )
        return client

    @staticmethod
    def _api_spec_key(spec: ApiSpec) -> tuple[str, str, str]:
        params = spec.params or {}
        canonical = json.dumps(
            {str(key): params[key] for key in sorted(params)},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        body = (
            json.dumps(spec.body, sort_keys=True, ensure_ascii=False, default=str)
            if spec.body is not None
            else ""
        )
        return (spec.method.upper(), spec.url, f"{canonical}|{body}")

    @staticmethod
    def _is_stream_spec(spec: ApiSpec) -> bool:
        return spec.method in {"WS", "SSE"} or str(spec.source) in {
            "websocket",
            "event-source",
        }

    @staticmethod
    def _response_pages_from_results(results: list[Any]) -> list[dict[str, Any]]:
        pages: list[dict[str, Any]] = []
        for result in results:
            if result.error or result.data is None:
                continue
            if result.security and result.security.get("blocked"):
                continue
            from param_augmenter import extract_api_urls

            response_endpoints = [
                {"method": "GET", "url": url, "source": "response-url"}
                for url in extract_api_urls(result.data, result.spec.url)
            ]
            pages.append(
                {
                    "url": result.spec.url,
                    "links": [],
                    "analysis": {
                        "api_endpoints": response_endpoints,
                        "json_api_fields": [],
                        "pagination": {},
                        "form_fields": [],
                        "embedded_json": [{"data": result.data}],
                    },
                }
            )
        return pages

    def _results_to_records(self, results: list[Any]) -> list[dict[str, Any]]:
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

    def fetch_chained(self) -> list[dict[str, Any]]:
        """Fetch APIs in rounds, feeding response data back as new parameters."""

        chain_cfg = self.api_config.get("chain") or {}
        max_rounds = max(1, int(chain_cfg.get("max_rounds", 3)))
        concurrency = int(self.api_config.get("concurrency", 1))
        augment_cfg = dict(self.api_config.get("augment") or {})
        augment_cfg.setdefault("max_specs", int(self.api_config.get("max_specs", 500)))
        from param_augmenter import augment_specs, discover_specs_from_pages

        client = self._new_api_client()
        all_results: list[Any] = []
        seen_keys: set[tuple[str, str, str]] = set()
        current_specs = [
            spec for spec in self.specs if not self._is_stream_spec(spec)
        ]
        rounds = 0
        round_spec_counts: list[int] = []
        try:
            while rounds < max_rounds and current_specs:
                results = client.fetch_all(
                    current_specs,
                    concurrency=concurrency,
                )
                all_results.extend(results)
                round_spec_counts.append(len(current_specs))
                for result in results:
                    seen_keys.add(self._api_spec_key(result.spec))
                rounds += 1
                if rounds >= max_rounds:
                    break
                response_pages = self._response_pages_from_results(all_results)
                if not response_pages:
                    break
                discovered = discover_specs_from_pages(response_pages, augment_cfg)
                augmented, _stats = augment_specs(
                    current_specs + discovered,
                    response_pages,
                    augment_cfg,
                )
                new_specs: list[ApiSpec] = []
                seen_new: set[tuple[str, str, str]] = set()
                for spec in augmented:
                    key = self._api_spec_key(spec)
                    if key in seen_keys or key in seen_new:
                        continue
                    seen_new.add(key)
                    new_specs.append(spec)
                    if len(new_specs) >= int(chain_cfg.get("max_specs_per_round", 50)):
                        break
                if not new_specs:
                    break
                current_specs = [
                    spec for spec in new_specs if not self._is_stream_spec(spec)
                ]
            self.chain_rounds = rounds
            self.chain_new_specs = max(0, sum(round_spec_counts[1:]))
            return self._results_to_records(all_results)
        finally:
            client.close()

    def fetch(self) -> list[dict[str, Any]]:
        chain_cfg = self.api_config.get("chain") or {}
        if chain_cfg.get("enabled", False):
            return self.fetch_chained()
        client = self._new_api_client()
        try:
            fetchable = [
                spec for spec in self.specs if not self._is_stream_spec(spec)
            ]
            results = client.fetch_all(
                fetchable, concurrency=int(self.api_config.get("concurrency", 1))
            )
        finally:
            client.close()
        return self._results_to_records(results)

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
        report("assets", 0.3, "downloading discovered media assets")
        self._download_media_assets()
        report("discover", 0.4, "analyzing page/API endpoints")
        self.discover()
        site_index_output = self.api_config.get("site_index_output")
        if site_index_output:
            from param_augmenter import build_site_api_index

            self.site_index = build_site_api_index(
                self.captures,
                self.api_config.get("augment") or {},
            )
            Path(site_index_output).write_text(
                json.dumps(self.site_index, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            report("index", 0.45, f"site API index written to {site_index_output}")
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
            "mode": self.mode,
            "captcha_mode": self.captcha_mode,
            "pages": len(self.pages),
            "captures": len(self.captures),
            "crawl_pages": len(self.crawl_result.pages) if self.crawl_result else 0,
            "api_specs": len(self.specs),
            "stream_specs": len(self.stream_specs),
            "augment_variants": self.augment_stats.variants if self.augment_stats else 0,
            "augment_param_keys": self.augment_stats.added_keys if self.augment_stats else 0,
            "augment_harvested_values": (
                self.augment_stats.harvested_values if self.augment_stats else 0
            ),
            "site_index_output": str(site_index_output) if site_index_output else None,
            "site_pages": (
                self.site_index["summary"]["pages"] if self.site_index else 0
            ),
            "site_endpoints": (
                self.site_index["summary"]["endpoints"] if self.site_index else 0
            ),
            "site_templates": (
                self.site_index["summary"]["templates"] if self.site_index else 0
            ),
            "site_param_keys": (
                self.site_index["summary"]["param_keys"] if self.site_index else 0
            ),
            "chain_rounds": self.chain_rounds,
            "chain_new_specs": self.chain_new_specs,
            "manifest_output": str(manifest_output) if manifest_output else None,
            "raw_records": len(records),
            "processed_records": len(processed),
            "security_findings": security_findings + self.api_security_findings,
            "api_blocks": self.api_security_findings,
            "crawl_summary": self.crawl_result.summary() if self.crawl_result else None,
            "crawl_api_responses": (
                self.crawl_result.summary().get("api_responses", 0)
                if self.crawl_result
                else 0
            ),
            "crawl_api_response_urls": (
                self.crawl_result.summary().get("api_response_urls", 0)
                if self.crawl_result
                else 0
            ),
            "block_recoveries": (
                self.crawl_result.summary().get("block_recoveries", 0)
                if self.crawl_result
                else 0
            ),
            "recovered_pages": (
                self.crawl_result.summary().get("recovered_pages", 0)
                if self.crawl_result
                else 0
            ),
            "cloudflare": (self._cloudflare_result.to_dict() if self._cloudflare_result else None),
            "hls_downloads": sum(1 for item in self.hls_results if "error" not in item),
            "hls_errors": sum(1 for item in self.hls_results if "error" in item),
            "asset_downloads": sum(
                1 for item in self.media_assets if "error" not in item
            ),
            "asset_errors": sum(
                1 for item in self.media_assets if "error" in item
            ),
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
        elif self.path == "/sub/list":
            body = (
                b"<!doctype html><html><head><title>sub list</title></head><body>"
                b'<a href="/sub/item/1">item 1</a>'
                b'<a href="/sub/item/2">item 2</a>'
                b"</body></html>"
            )
        elif self.path == "/chain/list":
            body = (
                b"<!doctype html><html><head><title>chain list</title></head><body>"
                b'<script>fetch("/api/chain/list"); fetch("/api/chain/detail");</script>'
                b"</body></html>"
            )
        elif self.path.startswith("/sub/item/"):
            item_id = self.path.rsplit("/", 1)[-1]
            script = f'fetch("/api/sub-data?id={item_id}")'.encode()
            body = (
                b"<!doctype html><html><head><title>item</title></head><body><script>"
                + script
                + b"</script></body></html>"
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
        elif self.path.startswith("/api/sub-data"):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            item_id = int((query.get("id") or ["1"])[0])
            body = json.dumps(
                {
                    "items": [
                        {"id": item_id, "name": f"Sub {item_id}"},
                    ]
                }
            ).encode("utf-8")
        elif self.path.startswith("/api/chain/list"):
            body = json.dumps(
                {
                    "items": [
                        {"id": 10, "name": "Base"},
                    ]
                }
            ).encode("utf-8")
        elif self.path.startswith("/api/chain/detail"):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            detail_id = int((query.get("id") or ["1"])[0])
            body = json.dumps(
                {
                    "items": [
                        {"id": detail_id, "name": f"Detail {detail_id}"},
                    ]
                }
            ).encode("utf-8")
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

            sub_out = Path(tmp) / "sub-result.json"
            sub_config = {
                "subpages": {
                    "seeds": [f"{base}/sub/list"],
                    "max_depth": 2,
                    "max_pages": 10,
                    "sitemap": False,
                    "respect_robots": False,
                },
                "api": {
                    "min_interval": 0.0,
                    "max_retries": 0,
                    "include_static": True,
                    "include_captured": False,
                    "auto_augment_params": True,
                    "augment": {"max_variants": 20},
                    "site_index_output": str(Path(tmp) / "site-index.json"),
                },
                "processing": {
                    "steps": [
                        {"op": "select", "params": {"fields": ["id", "name"]}},
                        {"op": "sort", "params": {"keys": [{"field": "id", "desc": False}]}},
                    ]
                },
            }
            sub_config_path = Path(tmp) / "sub-config.json"
            sub_config_path.write_text(json.dumps(sub_config), encoding="utf-8")
            sub_pipeline = WebDataPipeline(_read_config(sub_config_path), output=sub_out)
            sub_summary = sub_pipeline.run()
            assert sub_summary["crawl_pages"] == 3, sub_summary
            assert sub_summary["augment_variants"] >= 1, sub_summary
            assert sub_summary["site_pages"] == 3, sub_summary
            assert sub_summary["site_endpoints"] >= 1, sub_summary
            assert sub_summary["processed_records"] == 2, sub_summary
            sub_records = load_records(sub_out)
            assert sub_records == [
                {"id": 1, "name": "Sub 1"},
                {"id": 2, "name": "Sub 2"},
            ], sub_records

            chain_out = Path(tmp) / "chain-result.json"
            chain_config = {
                "pages": [f"{base}/chain/list"],
                "api": {
                    "min_interval": 0.0,
                    "max_retries": 0,
                    "include_static": True,
                    "include_captured": False,
                    "auto_augment_params": True,
                    "augment": {"max_variants": 20},
                    "chain": {
                        "enabled": True,
                        "max_rounds": 3,
                        "max_specs_per_round": 10,
                    },
                },
                "processing": {
                    "steps": [
                        {"op": "select", "params": {"fields": ["id", "name"]}},
                        {"op": "sort", "params": {"keys": [{"field": "id", "desc": False}]}},
                    ]
                },
            }
            chain_config_path = Path(tmp) / "chain-config.json"
            chain_config_path.write_text(json.dumps(chain_config), encoding="utf-8")
            chain_pipeline = WebDataPipeline(_read_config(chain_config_path), output=chain_out)
            chain_summary = chain_pipeline.run()
            assert chain_summary["chain_rounds"] >= 2, chain_summary
            assert chain_summary["chain_new_specs"] >= 2, chain_summary
            assert chain_summary["processed_records"] >= 3, chain_summary
    finally:
        server.shutdown()
        server.server_close()
    print("web_data_pipeline self-test OK")


def _config_from_url(
    url: str,
    *,
    max_depth: int = 3,
    max_pages: int = 200,
    crawl_api: bool = False,
    site_index: str | None = None,
    browser: bool = False,
    trigger_events: bool = False,
    capture_storage: bool = False,
    min_interval: float = 1.0,
    jitter: float = 0.5,
    max_retries: int = 2,
    backoff_base: float = 2.0,
    backoff_max: float = 60.0,
    respect_robots: bool = True,
    skip_blocked: bool = False,
    block_retries: int = 2,
    block_retry_delay: float = 2.0,
    block_retry_backoff: float = 2.0,
    rotate_proxy_on_block: bool = True,
    retry_on_block: bool = True,
    alternate_on_block: bool = True,
    browser_on_block: bool = False,
) -> dict[str, Any]:
    """Build an auto full-site crawl config from one seed URL."""
    config: dict[str, Any] = {
        "subpages": {
            "enabled": True,
            "seeds": [url],
            "max_depth": max_depth,
            "max_pages": max_pages,
            "sitemap": True,
            "respect_robots": respect_robots,
            "crawl_api_endpoints": crawl_api,
            "min_interval": min_interval,
            "jitter": jitter,
            "max_retries": max_retries,
            "backoff_base": backoff_base,
            "backoff_max": backoff_max,
            "skip_blocked": skip_blocked,
            "block_retries": block_retries,
            "block_retry_delay": block_retry_delay,
            "block_retry_backoff": block_retry_backoff,
            "rotate_proxy_on_block": rotate_proxy_on_block,
            "alternate_on_block": alternate_on_block,
            "browser_on_block": browser_on_block,
        },
        "api": {
            "auto_augment_params": True,
            "include_captured": True,
            "include_static": True,
            "min_interval": min_interval,
            "jitter": jitter,
            "max_retries": max_retries,
            "backoff_base": backoff_base,
            "backoff_max": backoff_max,
            "retry_on_block": retry_on_block,
            "block_retries": block_retries,
            "block_retry_delay": block_retry_delay,
            "block_retry_backoff": block_retry_backoff,
            "rotate_proxy_on_block": rotate_proxy_on_block,
        },
        "fetch": {
            "retry_on_block": retry_on_block,
        },
        "processing": {},
    }
    if site_index:
        config["api"]["site_index_output"] = site_index
    if browser:
        browser_config: dict[str, Any] = {
            "enabled": True,
            "headless": True,
        }
        if trigger_events:
            browser_config["trigger_events"] = ["click", "change", "input"]
        if capture_storage:
            browser_config["capture_storage"] = True
        config["browser"] = browser_config
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the web data pipeline")
    parser.add_argument("--config", help="JSON pipeline config")
    parser.add_argument(
        "--url",
        default=None,
        help="one URL to auto-crawl as a full site (pages, APIs, events, streams)",
    )
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument(
        "--crawl-api",
        action="store_true",
        help="fetch discovered API endpoints during the deep crawl",
    )
    parser.add_argument(
        "--site-index",
        default=None,
        help="write whole-site API index JSON (URL mode)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="render pages with a stealth browser and capture runtime APIs",
    )
    parser.add_argument(
        "--trigger-events",
        action="store_true",
        help="trigger inline event handlers in browser mode",
    )
    parser.add_argument(
        "--capture-storage",
        action="store_true",
        help="capture localStorage/sessionStorage in browser mode",
    )
    parser.add_argument("--output", help="override config output path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if args.config and args.url:
        parser.error("use --config OR --url, not both")
    if args.url:
        config = _config_from_url(
            args.url,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            crawl_api=args.crawl_api,
            site_index=args.site_index,
            browser=args.browser,
            trigger_events=args.trigger_events,
            capture_storage=args.capture_storage,
        )
    elif args.config:
        config = _read_config(args.config)
    else:
        parser.error("--config or --url is required unless --self-test is used")
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
