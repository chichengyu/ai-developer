"""Playwright browser session for login, cookies, consistent fingerprint,
and runtime network/API capture.

This template is for automating flows the user is authorized to automate.
It keeps one session and one fingerprint per account, persists cookies, and
lets AutoCaptchaSolver solve automatically, or the UI provide a manual
answer when a third-party service is unavailable.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from captcha_solver import AutoCaptchaSolver, CaptchaChallenge, detect_captchas
from cloudflare_challenge import (
    CloudflareChallengeConfig,
    CloudflareChallengeHandler,
    CloudflareChallengeResult,
    extract_cloudflare_state,
)
from fingerprint_bank import BrowserFingerprint
from fingerprint_binding import FingerprintBinding, resolve_binding
from fingerprint_manager import fingerprint_patch_values
from login_detector import detect_login_form, detect_login_state, detect_login_urls
from page_data_parser import PageDataAnalysis, analyze_page
from scrape_guard import RateLimiter
from slider_solver import SliderCaptchaSolver, SliderChallenge
from stealth_patches import apply_playwright_stealth

_USER_AGENT_TEMPLATES = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)


class LoginError(RuntimeError):
    """Raised when a login flow does not reach the success state."""


@dataclass
class FingerprintOptions:
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )
    locale: str = "zh-CN"
    timezone_id: str = "Asia/Shanghai"
    viewport: dict[str, int] | None = None
    platform: str = "Windows"
    languages: tuple[str, ...] = ("zh-CN", "zh", "en-US", "en")
    hardware_concurrency: int = 8
    device_memory: int = 8
    color_scheme: str = "light"
    screen: dict[str, int] | None = None
    extra_http_headers: dict[str, str] | None = None

    def to_context_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user_agent": self.user_agent,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "color_scheme": self.color_scheme,
            "extra_http_headers": {
                "Accept-Language": ", ".join(self.languages),
            },
        }
        if self.extra_http_headers:
            kwargs["extra_http_headers"].update(self.extra_http_headers)
        if self.viewport:
            kwargs["viewport"] = self.viewport
        if self.screen:
            kwargs["screen"] = self.screen
        return kwargs

    def init_script(self) -> str:
        """Keep navigator/screen signals consistent with the profile."""
        languages = json.dumps(list(self.languages), ensure_ascii=False)
        return f"""
        Object.defineProperty(navigator, "languages", {{
          get: () => {languages}
        }});
        Object.defineProperty(navigator, "hardwareConcurrency", {{
          get: () => {self.hardware_concurrency}
        }});
        Object.defineProperty(navigator, "deviceMemory", {{
          get: () => {self.device_memory}
        }});
        """

    def patch_values(self) -> dict[str, Any]:
        viewport = self.viewport or {"width": 1920, "height": 1080}
        screen = self.screen or {"width": 1920, "height": 1080}
        browser = BrowserFingerprint(
            user_agent=self.user_agent,
            platform=self.platform,
            languages=self.languages,
            timezone_id=self.timezone_id,
            viewport=(int(viewport.get("width", 1920)), int(viewport.get("height", 1080))),
            screen_width=int(screen.get("width", 1920)),
            screen_height=int(screen.get("height", 1080)),
            screen_avail_width=int(screen.get("width", 1920)),
            screen_avail_height=max(
                0,
                int(screen.get("height", 1080)) - 40,
            ),
            outer_width=int(screen.get("width", 1920)),
            outer_height=int(screen.get("height", 1080)),
            device_pixel_ratio=float(screen.get("devicePixelRatio", 1.0)),
            color_depth=int(screen.get("colorDepth", 24)),
            max_touch_points=int(screen.get("maxTouchPoints", 0)),
            hardware_concurrency=self.hardware_concurrency,
            device_memory=self.device_memory,
        )
        return fingerprint_patch_values(browser)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
            "viewport": self.viewport,
            "platform": self.platform,
            "languages": list(self.languages),
            "hardware_concurrency": self.hardware_concurrency,
            "device_memory": self.device_memory,
            "color_scheme": self.color_scheme,
            "screen": self.screen,
            "extra_http_headers": self.extra_http_headers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FingerprintOptions:
        return cls(
            user_agent=str(data.get("user_agent") or cls().user_agent),
            locale=str(data.get("locale") or cls().locale),
            timezone_id=str(data.get("timezone_id") or cls().timezone_id),
            viewport=data.get("viewport"),
            platform=str(data.get("platform") or cls().platform),
            languages=tuple(data.get("languages") or cls().languages),
            hardware_concurrency=int(data.get("hardware_concurrency") or 8),
            device_memory=int(data.get("device_memory") or 8),
            color_scheme=str(data.get("color_scheme") or "light"),
            screen=data.get("screen"),
            extra_http_headers=data.get("extra_http_headers"),
        )

    @classmethod
    def generate(
        cls,
        seed: int | None = None,
        locale: str = "zh-CN",
        timezone_id: str = "Asia/Shanghai",
    ) -> FingerprintOptions:
        """Generate a stable pseudo-random profile for one account."""
        rng = random.Random(seed)
        width = rng.choice((1366, 1440, 1536, 1920))
        height = rng.choice((768, 900, 1024, 1080))
        return cls(
            user_agent=rng.choice(_USER_AGENT_TEMPLATES),
            locale=locale,
            timezone_id=timezone_id,
            viewport={"width": width, "height": height},
            platform="Windows",
            languages=(locale, "zh", "en-US", "en"),
            hardware_concurrency=rng.choice((4, 8, 12, 16)),
            device_memory=rng.choice((4, 8)),
            color_scheme="light",
            screen={
                "width": width,
                "height": height,
                "availWidth": width,
                "availHeight": height,
            },
        )

    @classmethod
    def from_binding(cls, binding: FingerprintBinding) -> FingerprintOptions:
        extra_headers = binding.to_header_headers()
        extra_headers.pop("User-Agent", None)
        extra_headers.pop("Accept-Language", None)
        return cls(
            user_agent=binding.user_agent,
            locale=binding.languages[0] if binding.languages else "en-US",
            timezone_id=binding.timezone_id,
            viewport={
                "width": binding.viewport[0],
                "height": binding.viewport[1],
            }
            if binding.viewport
            else None,
            platform=binding.platform,
            languages=binding.languages,
            hardware_concurrency=binding.hardware_concurrency,
            device_memory=binding.device_memory,
            extra_http_headers=extra_headers,
        )

    def save(self, path: str | Path) -> Path:
        out = Path(path)
        out.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out

    @classmethod
    def load(cls, path: str | Path) -> FingerprintOptions:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


@dataclass
class NetworkCaptureOptions:
    capture_types: tuple[str, ...] = ("document", "xhr", "fetch", "websocket", "media")
    include_bodies: bool = True
    include_headers: bool = False
    max_body_bytes: int = 2 * 1024 * 1024


@dataclass
class NetworkEntry:
    method: str
    url: str
    resource_type: str
    status: int | None = None
    content_type: str | None = None
    size: int | None = None
    json_data: Any = None
    body_text: str | None = None
    request_headers: dict[str, str] | None = None
    response_headers: dict[str, str] | None = None
    post_data: str | None = None
    request_content_type: str | None = None
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def is_api(self) -> bool:
        return self.resource_type in {"xhr", "fetch", "websocket"} or self.json_data is not None

    def to_dict(self, include_body: bool = True) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "resource_type": self.resource_type,
            "status": self.status,
            "content_type": self.content_type,
            "size": self.size,
            "json": self.json_data if include_body else None,
            "body": self.body_text if include_body else None,
            "request_headers": self.request_headers,
            "response_headers": self.response_headers,
            "post_data": self.post_data,
            "request_content_type": self.request_content_type,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


@dataclass
class PageCapture:
    url: str
    html: str
    network: list[NetworkEntry]
    analysis: PageDataAnalysis | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    security: dict[str, Any] | None = None

    def api_calls(self) -> list[NetworkEntry]:
        return [entry for entry in self.network if entry.is_api]

    def hls_urls(self) -> list[str]:
        """Return HLS URLs from page analysis plus runtime network capture."""
        urls: list[str] = []
        if self.analysis is not None:
            urls.extend(self.analysis.media.hls)
            urls.extend(self.analysis.json_media.hls)
        for entry in self.network:
            if ".m3u8" in entry.url.lower():
                urls.append(entry.url)
        seen: set[str] = set()
        unique: list[str] = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique

    def to_dict(
        self,
        include_html: bool = False,
        include_body: bool = True,
    ) -> dict[str, Any]:
        return {
            "url": self.url,
            "html": self.html if include_html else None,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "network": [entry.to_dict(include_body=include_body) for entry in self.network],
            "analysis": self.analysis.to_dict() if self.analysis is not None else None,
            "security": self.security,
        }

    def save(
        self,
        path: str | Path,
        include_html: bool = False,
        include_body: bool = True,
    ) -> Path:
        out = Path(path)
        out.write_text(
            json.dumps(
                self.to_dict(include_html=include_html, include_body=include_body),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return out


def _header_value(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return str(value)
    return None


_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies",
    "cf-chl",
    "challenge-platform",
    "attention required",
)


class BrowserSession:
    """One persistent Chromium session per account."""

    def __init__(
        self,
        headless: bool = True,
        proxy: str | None = None,
        user_data_dir: str | Path | None = None,
        fingerprint: FingerprintOptions | None = None,
        action_interval: float = 0.0,
        action_jitter: float = 0.2,
        storage_state: str | Path | None = None,
        engine: str = "playwright",
        fingerprint_binding: str | dict[str, Any] | FingerprintBinding | None = None,
        cloudflare_config: dict[str, Any] | None = None,
        captcha_solver: Any | None = None,
        slider_solver: Any | None = None,
        audio_solver: Any | None = None,
    ) -> None:
        self.headless = headless
        self.proxy = proxy
        self.user_data_dir = Path(user_data_dir) if user_data_dir else None
        self.binding = resolve_binding(fingerprint_binding)
        self.cloudflare_config = dict(cloudflare_config or {})
        self.captcha_solver = captcha_solver
        self.slider_solver = slider_solver or SliderCaptchaSolver()
        self.audio_solver = audio_solver
        self.fingerprint = (
            FingerprintOptions.from_binding(self.binding)
            if self.binding is not None
            else fingerprint or FingerprintOptions()
        )
        self.engine = str(engine or "playwright").lower()
        self._storage_state_path = Path(storage_state) if storage_state else None
        self._action_limiter = (
            RateLimiter(min_interval=action_interval, jitter=action_jitter)
            if action_interval > 0
            else None
        )
        self._playwright: Any = None
        self._browser: Any = None
        self.context: Any = None
        self.page: Any = None
        self._capture_options: NetworkCaptureOptions | None = None
        self._capture_attached = False
        self._network: list[NetworkEntry] = []

    def start(self) -> None:
        if self.engine == "patchright":
            try:
                from patchright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError(
                    "pip install patchright && python -m patchright install chromium"
                ) from exc
        else:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError as exc:
                raise RuntimeError("pip install playwright && playwright install chromium") from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        kwargs = self.fingerprint.to_context_kwargs()
        if self.proxy:
            kwargs["proxy"] = {"server": self.proxy}
        if self.user_data_dir:
            kwargs["user_data_dir"] = str(self.user_data_dir)
        if self._storage_state_path is not None and self._storage_state_path.exists():
            kwargs["storage_state"] = str(self._storage_state_path)
        self.context = self._browser.new_context(**kwargs)
        self.context.add_init_script(self.fingerprint.init_script())
        apply_playwright_stealth(
            self.context,
            None,
            values=self.fingerprint.patch_values(),
        )
        self.page = self.context.new_page()

    def goto(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: float = 30000,
    ) -> None:
        if self._action_limiter is not None:
            self._action_limiter.wait()
        self.page.goto(url, wait_until=wait_until, timeout=timeout)

    def is_challenge_page(self) -> bool:
        """Return True when the current page still shows a browser challenge."""
        if self.page is None:
            return False
        text = str(getattr(self.page, "title", lambda: "")() or "").lower()
        if not any(marker in text for marker in _CHALLENGE_MARKERS):
            with suppress(Exception):
                text += "\n" + self.page.content().lower()
        return any(marker in text for marker in _CHALLENGE_MARKERS)

    def wait_for_challenge(
        self,
        timeout: float = 60000,
        poll_interval: float = 1.0,
    ) -> bool:
        """Wait for a Cloudflare-style challenge to clear without user input."""
        if self.cloudflare_config or self.captcha_solver is not None:
            result = self.solve_challenge(timeout=timeout)
            return result.passed
        if not self.is_challenge_page():
            return True
        deadline = time.monotonic() + timeout / 1000.0
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            if not self.is_challenge_page():
                return True
        return not self.is_challenge_page()

    def solve_challenge(
        self,
        *,
        url: str | None = None,
        timeout: float = 60000,
    ) -> CloudflareChallengeResult:
        """Run the full challenge handler against the current browser page."""
        if self.page is None or self.context is None:
            return CloudflareChallengeResult(passed=False, error="browser page is not open")
        config = CloudflareChallengeConfig.from_dict(self.cloudflare_config)
        config.wait_timeout = max(float(config.wait_timeout), float(timeout))
        config.clearance_timeout = min(
            float(config.clearance_timeout),
            float(config.wait_timeout),
        )
        handler = CloudflareChallengeHandler(
            config=config,
            captcha_solver=self.captcha_solver,
        )
        page_url = url or str(getattr(self.page, "url", "") or "")
        state = extract_cloudflare_state(
            self.page.content(),
            page_url=page_url,
            cookies=self.context.cookies(),
            title=str(getattr(self.page, "title", lambda: "")() or ""),
        )
        return handler.run(self.page, self.context, page_url, state)

    def start_capture(self, options: NetworkCaptureOptions | None = None) -> None:
        """Start recording page requests/responses; safe to call repeatedly."""
        if self.page is None:
            raise RuntimeError("browser session must be started before network capture")
        self._capture_options = options or NetworkCaptureOptions()
        self._network = []
        if not self._capture_attached:
            self.page.on("request", self._on_request)
            self.page.on("response", self._on_response)
            self._capture_attached = True

    def stop_capture(self) -> list[NetworkEntry]:
        """Stop recording and return the captured network entries."""
        self._capture_options = None
        return list(self._network)

    def _on_request(self, request: Any) -> None:
        options = self._capture_options
        if options is None:
            return
        resource_type = str(getattr(request, "resource_type", "") or "")
        if options.capture_types and resource_type not in options.capture_types:
            return
        headers = dict(request.headers) if options.include_headers else None
        post_data = None
        request_content_type = None
        if options.include_bodies:
            post_data = getattr(request, "post_data", None)
            request_headers = getattr(request, "headers", {}) or {}
            request_content_type = _header_value(request_headers, "content-type")
        self._network.append(
            NetworkEntry(
                method=str(getattr(request, "method", "GET") or "GET"),
                url=str(getattr(request, "url", "") or ""),
                resource_type=resource_type,
                request_headers=headers,
                post_data=post_data,
                request_content_type=request_content_type,
                started_at=time.monotonic(),
            )
        )

    def _on_response(self, response: Any) -> None:
        options = self._capture_options
        if options is None:
            return
        entry = None
        try:
            request = getattr(response, "request", None)
            url = str(getattr(request, "url", "") or "")
            method = str(getattr(request, "method", "") or "")
            entry = next(
                (
                    item
                    for item in reversed(self._network)
                    if item.status is None
                    and item.url == url
                    and (not method or item.method == method)
                ),
                None,
            )
            if entry is None:
                return
            entry.status = int(getattr(response, "status", 0) or 0)
            headers = dict(getattr(response, "headers", {}) or {})
            entry.response_headers = headers if options.include_headers else None
            entry.content_type = _header_value(headers, "content-type")
            if options.include_bodies:
                try:
                    self._capture_body(entry, response, headers, options.max_body_bytes)
                except Exception as exc:
                    entry.error = str(exc)
        except Exception as exc:
            if entry is None:
                entry = next(
                    (item for item in reversed(self._network) if item.status is None),
                    None,
                )
            if entry is not None:
                entry.error = str(exc)
        finally:
            if entry is not None:
                entry.finished_at = time.monotonic()

    def _capture_body(
        self,
        entry: NetworkEntry,
        response: Any,
        headers: dict[str, str],
        max_bytes: int,
    ) -> None:
        content_length = _header_value(headers, "content-length")
        if content_length is not None:
            try:
                parsed_length = int(content_length)
            except ValueError:
                parsed_length = 0
            if parsed_length > max_bytes:
                entry.size = parsed_length
                return
        content_type = (_header_value(headers, "content-type") or "").lower()
        if "json" in content_type or entry.url.rstrip("?/#").endswith(".json"):
            try:
                entry.json_data = response.json()
            except Exception:
                body = response.body()
                entry.size = len(body)
                entry.body_text = body[:max_bytes].decode("utf-8", "replace")
        else:
            body = response.body()
            entry.size = len(body)
            entry.body_text = body[:max_bytes].decode("utf-8", "replace")

    def capture_page_data(
        self,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout: float = 30000,
        network_idle: bool = True,
        network_idle_timeout: float = 15000,
        capture_options: NetworkCaptureOptions | None = None,
        wait_for_challenge: bool = False,
        challenge_timeout: float = 60000,
    ) -> PageCapture:
        """Load a page, capture runtime API traffic, and deep-parse it."""
        started = time.monotonic()
        self.start_capture(capture_options)
        html = ""
        try:
            self.goto(url, wait_until=wait_until, timeout=timeout)
            if network_idle and self.page is not None:
                with suppress(Exception):
                    self.page.wait_for_load_state(
                        "networkidle",
                        timeout=network_idle_timeout,
                    )
            if wait_for_challenge and self.page is not None:
                self.wait_for_challenge(timeout=challenge_timeout)
            if self.page is not None:
                html = self.page.content()
        finally:
            network = self.stop_capture()
        return PageCapture(
            url=url,
            html=html,
            network=network,
            analysis=analyze_page(html, base_url=url),
            started_at=started,
            finished_at=time.monotonic(),
        )

    def solve_captchas_auto(
        self,
        solver: AutoCaptchaSolver,
        page_url: str | None = None,
        image_paths: list[str | Path] | None = None,
        max_challenges: int | None = None,
    ) -> list[tuple[CaptchaChallenge, str]]:
        """Detect page CAPTCHAs, solve them, and fill the answers."""
        if self.page is None:
            raise RuntimeError("browser session must be started before CAPTCHA solving")
        html = self.page.content()
        challenges = detect_captchas(html, page_url or self.page.url)
        normal_challenges = [
            challenge for challenge in challenges if challenge.kind not in {"slider", "audio"}
        ]
        solved = solver.solve_detected(
            normal_challenges,
            image_paths=image_paths,
            max_challenges=max_challenges,
        )
        for challenge, answer in solved:
            self._fill_captcha_answer(challenge, answer)
        for challenge in challenges:
            if challenge.kind == "slider":
                result = self.slider_solver.solve(
                    self.page,
                    SliderChallenge(selector=challenge.selector or ""),
                )
                if result.success:
                    solved.append((challenge, "slider-solved"))
            elif challenge.kind == "audio":
                audio_url = challenge.audio_url
                if audio_url and self.audio_solver is not None:
                    result = self.audio_solver.solve_audio(audio_url)
                    if result.success:
                        solved.append((challenge, result.answer or "audio-solved"))
        return solved

    def _fill_captcha_answer(
        self,
        challenge: CaptchaChallenge,
        answer: str,
    ) -> None:
        if challenge.kind in {"recaptcha_v2", "recaptcha_v3"}:
            selector = challenge.selector or "textarea#g-recaptcha-response"
        elif challenge.kind == "hcaptcha":
            selector = challenge.selector or "textarea#h-captcha-response"
        elif challenge.kind == "turnstile":
            selector = challenge.selector or "textarea#cf-turnstile-response"
        elif challenge.kind == "geetest":
            selector = (
                challenge.selector or "input[name=geetest_challenge], input[name=geetest_validate]"
            )
        else:
            selector = (
                challenge.selector
                or "input[name*=captcha], input[name*=verify_code], input[name*=code]"
            )
        if not selector:
            return
        script = """
        (selector, value) => {
          const el = document.querySelector(selector);
          if (!el) return false;
          el.value = value;
          el.dispatchEvent(new Event("input", {bubbles: true}));
          el.dispatchEvent(new Event("change", {bubbles: true}));
          return true;
        }
        """
        self.page.evaluate(script, selector, answer)

    def detect_login_selectors(self, page_url: str | None = None):
        """Detect username/password/submit selectors from the current page."""
        if self.page is None:
            raise RuntimeError("browser session must be started before login detection")
        html = self.page.content()
        form = detect_login_form(html, page_url or self.page.url)
        if form is None:
            raise LoginError("could not auto-detect a login form on the page")
        return form

    def is_logged_in(self, page_url: str | None = None) -> bool:
        """Return True when the current page looks authenticated."""
        if self.page is None:
            return False
        html = self.page.content()
        logged_in, confidence, _ = detect_login_state(html, page_url or self.page.url)
        return logged_in and confidence >= 0.6

    def find_login_url(self, url: str, timeout: float = 30000) -> str:
        """Follow login-looking links from a page and return the target."""
        self.goto(url, timeout=timeout)
        if self.page is None:
            raise RuntimeError("browser session must be started before login detection")
        html = self.page.content()
        urls = detect_login_urls(html, self.page.url)
        return urls[0] if urls else self.page.url

    def auto_login(
        self,
        url: str,
        username: str,
        password: str,
        *,
        auto_captcha_solver: AutoCaptchaSolver | None = None,
        captcha_image_paths: list[str | Path] | None = None,
        max_captcha_retries: int = 2,
        success_selector: str | None = None,
        success_markers: tuple[str, ...] | None = None,
        timeout: float = 30000,
        storage_state: str | Path | None = None,
        cookies_path: str | Path | None = None,
    ) -> bool:
        """Auto-detect a login form, submit credentials, and verify success."""
        self.goto(url, timeout=timeout)
        if self.is_logged_in(url):
            if storage_state:
                self.save_state(storage_state)
            if cookies_path:
                self.save_cookies(cookies_path)
            return True
        if success_selector and self.page is not None:
            with suppress(Exception):
                if self.page.locator(success_selector).count() > 0:
                    return True
        self.login(
            url,
            username,
            password,
            "",
            "",
            "",
            auto_captcha_solver=auto_captcha_solver,
            captcha_image_paths=captcha_image_paths,
            max_captcha_retries=max_captcha_retries,
            success_selector=success_selector,
            success_markers=success_markers,
            timeout=timeout,
        )
        if storage_state:
            self.save_state(storage_state)
        if cookies_path:
            self.save_cookies(cookies_path)
        return True

    def login(
        self,
        url: str,
        username: str,
        password: str,
        username_selector: str,
        password_selector: str,
        submit_selector: str,
        captcha_callback: Callable[[Any], str] | None = None,
        captcha_selector: str | None = None,
        auto_captcha_solver: AutoCaptchaSolver | None = None,
        captcha_image_paths: list[str | Path] | None = None,
        max_captcha_retries: int = 2,
        success_selector: str | None = None,
        success_markers: tuple[str, ...] | None = None,
        timeout: float = 30000,
    ) -> None:
        """Fill login fields, solve CAPTCHAs automatically, and submit."""
        self.goto(url, timeout=timeout)
        if not username_selector or not password_selector or not submit_selector:
            form = self.detect_login_selectors(url)
            username_selector = username_selector or form.username_selector or ""
            password_selector = password_selector or form.password_selector or ""
            submit_selector = submit_selector or form.submit_selector or ""
        if not (username_selector and password_selector and submit_selector):
            raise LoginError(
                "login form is incomplete; provide selectors or enable auto detection"
            )
        self.page.fill(username_selector, username)
        self.page.fill(password_selector, password)
        attempts = max(1, max_captcha_retries) if auto_captcha_solver else 1
        attempt_timeout = max(1000.0, timeout / attempts)
        for attempt in range(attempts):
            if auto_captcha_solver is not None:
                self.solve_captchas_auto(
                    auto_captcha_solver,
                    page_url=url,
                    image_paths=captcha_image_paths,
                )
            elif (
                captcha_callback
                and captcha_selector
                and self.page.locator(captcha_selector).count() > 0
            ):
                token = captcha_callback(self.page)
                if token:
                    try:
                        self.page.fill(captcha_selector, token)
                    except Exception:
                        self.page.evaluate(
                            f"arguments[0].value = {token!r}",
                            self.page.locator(captcha_selector).first,
                        )
            self.page.click(submit_selector)
            if success_selector:
                try:
                    self.page.wait_for_selector(
                        success_selector,
                        timeout=attempt_timeout,
                    )
                    return
                except Exception:
                    if attempt >= attempts - 1 or auto_captcha_solver is None:
                        raise
                    self.page.wait_for_timeout(1000)
                    continue
            elif success_markers:
                if self._wait_for_login_success(
                    attempt_timeout,
                    success_markers=success_markers,
                ):
                    return
                if attempt + 1 < attempts and auto_captcha_solver is not None:
                    self.page.wait_for_timeout(1000)
                    continue
                raise LoginError("login did not reach the expected success state")
            else:
                self.page.wait_for_timeout(2000)
                return

    def _wait_for_login_success(
        self,
        timeout: float,
        *,
        success_selector: str | None = None,
        success_markers: tuple[str, ...] | None = None,
    ) -> bool:
        if self.page is None:
            return False
        deadline = time.monotonic() + timeout / 1000.0
        while time.monotonic() < deadline:
            if success_selector:
                with suppress(Exception):
                    if self.page.locator(success_selector).count() > 0:
                        return True
            html = self.page.content().lower()
            page_url = self.page.url.lower()
            if success_markers and any(
                marker.lower() in html or marker.lower() in page_url
                for marker in success_markers
            ):
                return True
            logged_in, confidence, _ = detect_login_state(html, page_url)
            if logged_in and confidence >= 0.6:
                return True
            time.sleep(0.5)
        return False

    def save_cookies(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.context.cookies(), ensure_ascii=False),
            encoding="utf-8",
        )

    def load_cookies(self, path: str | Path) -> None:
        cookies = json.loads(Path(path).read_text(encoding="utf-8"))
        self.context.add_cookies(cookies)

    def save_state(self, path: str | Path) -> Path:
        """Persist cookies plus local/session storage as Playwright state."""
        if self.context is None:
            raise RuntimeError("browser session must be started before saving state")
        out = Path(path)
        self.context.storage_state(path=str(out))
        return out

    def load_state(self, path: str | Path) -> None:
        """Restore Playwright storage state into the current context."""
        state = json.loads(Path(path).read_text(encoding="utf-8"))
        if self.context is None:
            self._storage_state_path = Path(path)
            return
        cookies = state.get("cookies") or []
        if cookies:
            self.context.add_cookies(cookies)
        origins = state.get("origins") or []
        if origins:
            origin_state = {
                origin.get("origin"): {
                    "localStorage": {
                        item.get("name"): item.get("value")
                        for item in origin.get("localStorage", [])
                        if item.get("name")
                    },
                    "sessionStorage": {
                        item.get("name"): item.get("value")
                        for item in origin.get("sessionStorage", [])
                        if item.get("name")
                    },
                }
                for origin in origins
                if origin.get("origin")
            }
            payload = json.dumps(origin_state, ensure_ascii=False)
            self.context.add_init_script(
                f"""
                (() => {{
                  const state = {payload};
                  const entry = state[location.origin];
                  if (!entry) return;
                  for (const [key, value] of Object.entries(entry.localStorage || {{}})) {{
                    localStorage.setItem(key, value);
                  }}
                  for (const [key, value] of Object.entries(entry.sessionStorage || {{}})) {{
                    sessionStorage.setItem(key, value);
                  }}
                }})();
                """
            )

    def save_fingerprint(self, path: str | Path) -> Path:
        return self.fingerprint.save(path)

    def load_fingerprint(self, path: str | Path) -> None:
        self.fingerprint = FingerprintOptions.load(path)

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()


if __name__ == "__main__":
    print(
        "desktop-app-dev browser_session: import BrowserSession / FingerprintOptions for fingerprint browsing."
    )
