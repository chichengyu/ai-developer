"""High-intensity Cloudflare challenge handling for authorized automation.

Cloudflare serves several challenge intensities: the lightweight JS
challenge, managed non-interactive challenges, interactive Turnstile
widgets, and full block pages. This module classifies the current stage,
waits for the `cf_clearance` cookie, tries to interact with the Turnstile
widget, and can submit a third-party Turnstile token. It never claims to
bypass CAPTCHAs; when a challenge cannot be cleared it returns a result
that the pipeline can use to rotate proxy / retry in a fresh browser
session without asking the user.
"""

from __future__ import annotations

import re
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verify you are human",
    "managed challenge",
    "cf-chl",
    "cf_chl_opt",
    "challenge-platform",
    "challenges.cloudflare.com",
    "enable javascript and cookies",
    "attention required",
)
_TURNSTILE_SRC_RE = re.compile(r"https?://challenges\.cloudflare\.com[^\"'\s]*", re.IGNORECASE)
_SITEKEY_RE = re.compile(r"[?&](?:k|sitekey)=([A-Za-z0-9_\-]{8,})", re.IGNORECASE)
_RAY_RE = re.compile(r"cloudflare[\s-]*ray[^0-9]{0,24}([0-9a-f]{16,})", re.IGNORECASE)
_ERROR_CODE_RE = re.compile(r"error[^0-9]{0,20}code\s*[:=]?\s*(\d+)", re.IGNORECASE)
_CLEARANCE_NAME = "cf_clearance"


@dataclass
class CloudflareChallengeState:
    """Current Cloudflare challenge stage and available signals."""

    present: bool
    stage: str = "none"
    sitekey: str | None = None
    frame_url: str | None = None
    ray_id: str | None = None
    error_code: str | None = None
    clearance_cookie: str | None = None
    clearance_expires: float | None = None
    markers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "stage": self.stage,
            "sitekey": self.sitekey,
            "frame_url": self.frame_url,
            "ray_id": self.ray_id,
            "error_code": self.error_code,
            "clearance_cookie": self.clearance_cookie,
            "clearance_expires": self.clearance_expires,
            "markers": self.markers,
        }


@dataclass
class CloudflareChallengeConfig:
    """Non-interactive strategy configuration for challenge handling."""

    enabled: bool = True
    max_attempts: int = 3
    wait_timeout: float = 60000
    clearance_timeout: float = 30000
    poll_interval: float = 1.0
    auto_click: bool = True
    solve_turnstile: bool = True
    reload_before_retry: bool = True
    reload_delay: float = 2.0
    rotate_proxy_on_fail: bool = True
    user_agent: str | None = None
    proxy: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CloudflareChallengeConfig:
        values = dict(data or {})
        return cls(
            enabled=bool(values.get("enabled", True)),
            max_attempts=int(values.get("max_attempts", 3)),
            wait_timeout=float(values.get("wait_timeout", 60000)),
            clearance_timeout=float(values.get("clearance_timeout", 30000)),
            poll_interval=float(values.get("poll_interval", 1.0)),
            auto_click=bool(values.get("auto_click", True)),
            solve_turnstile=bool(values.get("solve_turnstile", True)),
            reload_before_retry=bool(values.get("reload_before_retry", True)),
            reload_delay=float(values.get("reload_delay", 2.0)),
            rotate_proxy_on_fail=bool(values.get("rotate_proxy_on_fail", True)),
            user_agent=values.get("user_agent"),
            proxy=values.get("proxy"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "max_attempts": self.max_attempts,
            "wait_timeout": self.wait_timeout,
            "clearance_timeout": self.clearance_timeout,
            "poll_interval": self.poll_interval,
            "auto_click": self.auto_click,
            "solve_turnstile": self.solve_turnstile,
            "reload_before_retry": self.reload_before_retry,
            "reload_delay": self.reload_delay,
            "rotate_proxy_on_fail": self.rotate_proxy_on_fail,
            "user_agent": self.user_agent,
            "proxy": self.proxy,
        }


@dataclass
class CloudflareChallengeResult:
    """Outcome of one challenge-handling run."""

    passed: bool
    attempts: int = 0
    strategy: str = "none"
    cf_clearance: str | None = None
    clearance_cookie: dict[str, Any] | None = None
    user_agent: str | None = None
    proxy: str | None = None
    error: str | None = None
    needs_new_session: bool = False
    state: CloudflareChallengeState | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "attempts": self.attempts,
            "strategy": self.strategy,
            "cf_clearance": self.cf_clearance,
            "clearance_cookie": self.clearance_cookie,
            "user_agent": self.user_agent,
            "proxy": self.proxy,
            "error": self.error,
            "needs_new_session": self.needs_new_session,
            "state": self.state.to_dict() if self.state else None,
        }


def _lower_headers(headers: dict[str, str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (headers or {}).items():
        result[str(key).lower()] = str(value)
    return result


def _find_clearance_cookie(cookies: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    for item in cookies or []:
        if str(item.get("name", "") or "").lower() == _CLEARANCE_NAME:
            return dict(item)
    return None


def extract_cloudflare_state(
    html: str,
    page_url: str | None = None,
    cookies: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
    title: str = "",
) -> CloudflareChallengeState:
    """Classify the Cloudflare challenge stage from page/cookie signals."""
    lower = _lower_headers(headers)
    text = f"{title}\n{html}".lower()
    markers = [marker for marker in _CHALLENGE_MARKERS if marker in text]
    frame_match = _TURNSTILE_SRC_RE.search(html)
    frame_url = frame_match.group(0) if frame_match else None
    sitekey_match = (
        _SITEKEY_RE.search(frame_url or "")
        or _SITEKEY_RE.search(html)
        or re.search(r'data-sitekey=["\']([A-Za-z0-9_\-]{8,})["\']', html, re.IGNORECASE)
    )
    sitekey = sitekey_match.group(1) if sitekey_match else None
    ray_match = _RAY_RE.search(text)
    ray_id = lower.get("cf-ray") or (ray_match.group(1) if ray_match else None)
    error_code = None
    error_match = _ERROR_CODE_RE.search(text)
    if error_match:
        error_code = error_match.group(1)

    clearance = _find_clearance_cookie(cookies)
    clearance_value = str(clearance.get("value") or "") if clearance else None
    clearance_expires = None
    if clearance is not None:
        expires = clearance.get("expires")
        if isinstance(expires, int | float) and expires > 0:
            clearance_expires = float(expires)

    blocked = (
        "attention required" in text
        or "error code 1020" in text
        or (ray_id is not None and "access denied" in text)
    )
    present = bool(markers) or lower.get("cf-mitigated") == "challenge"
    if blocked:
        stage = "blocked"
    elif present and ("managed challenge" in text or "cf-chl" in text):
        stage = "managed_non_interactive"
    elif present and ("turnstile" in text or sitekey is not None):
        stage = "turnstile_captcha"
    elif present and ("just a moment" in text or "checking your browser" in text):
        stage = "js_challenge"
    elif present:
        stage = "managed_non_interactive"
    elif clearance_value:
        stage = "passed"
    else:
        stage = "none"

    return CloudflareChallengeState(
        present=present,
        stage=stage,
        sitekey=sitekey,
        frame_url=frame_url,
        ray_id=ray_id,
        error_code=error_code,
        clearance_cookie=clearance_value,
        clearance_expires=clearance_expires,
        markers=markers,
    )


class CloudflareChallengeHandler:
    """Duck-typed browser handler: waits, clicks, solves, and reloads."""

    _CLICK_SELECTORS = (
        "input[type='checkbox']",
        "#challenge-stage input[type='checkbox']",
        ".ctp-checkbox-container",
        "button[id*='challenge']",
        "#turnstile-wrapper input[type='checkbox']",
    )
    _FRAME_CLICK_SELECTORS = (
        "input[type='checkbox']",
        "#challenge-stage input[type='checkbox']",
        "button",
    )

    def __init__(
        self,
        config: CloudflareChallengeConfig | None = None,
        captcha_solver: Any | None = None,
    ) -> None:
        self.config = config or CloudflareChallengeConfig()
        self.captcha_solver = captcha_solver

    def run(
        self,
        page: Any,
        context: Any,
        url: str,
        state: CloudflareChallengeState | None = None,
    ) -> CloudflareChallengeResult:
        result = CloudflareChallengeResult(
            passed=False,
            proxy=self.config.proxy,
            user_agent=self.config.user_agent,
        )
        attempts = max(1, self.config.max_attempts)
        for attempt in range(attempts):
            result.attempts = attempt + 1
            current = state or self._state(page, context, url)
            if current is None:
                continue
            result.state = current
            if current.stage == "blocked":
                result.error = "cloudflare block page"
                return result
            if not current.present and not current.clearance_cookie:
                result.passed = True
                result.strategy = "none"
                result.user_agent = self._user_agent(page) or result.user_agent
                return result

            cookie = self._wait_for_clearance(context)
            if cookie:
                result.passed = True
                result.strategy = "clearance"
                result.cf_clearance = str(cookie.get("value") or "")
                result.clearance_cookie = cookie
                result.user_agent = self._user_agent(page) or result.user_agent
                return result

            if self._wait_until_passed(page, context, url):
                result.passed = True
                result.strategy = "wait"
                result.user_agent = self._user_agent(page) or result.user_agent
                return result

            if self.config.auto_click and self._try_click(page):
                time.sleep(min(1.0, self.config.reload_delay))
                cookie = self._wait_for_clearance(context)
                if cookie:
                    result.passed = True
                    result.strategy = "click"
                    result.cf_clearance = str(cookie.get("value") or "")
                    result.clearance_cookie = cookie
                    result.user_agent = self._user_agent(page) or result.user_agent
                    return result
                if self._wait_until_passed(page, context, url):
                    result.passed = True
                    result.strategy = "click_wait"
                    result.user_agent = self._user_agent(page) or result.user_agent
                    return result

            sitekey = current.sitekey or self._extract_sitekey(page)
            if (
                self.config.solve_turnstile
                and self._can_solve_turnstile()
                and sitekey
                and self._solve_and_inject(page, url, sitekey)
                and self._wait_until_passed(page, context, url)
            ):
                result.passed = True
                result.strategy = "turnstile"
                result.user_agent = self._user_agent(page) or result.user_agent
                return result

            if self.config.reload_before_retry and attempt + 1 < attempts:
                time.sleep(self.config.reload_delay)
                with suppress(Exception):
                    page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=self.config.wait_timeout,
                    )

        result.error = "cloudflare challenge did not clear"
        if self.config.rotate_proxy_on_fail:
            result.needs_new_session = True
        return result

    def _state(
        self,
        page: Any,
        context: Any,
        url: str,
    ) -> CloudflareChallengeState | None:
        try:
            html = page.content()
            title = str(getattr(page, "title", lambda: "")() or "")
            page_url = str(getattr(page, "url", url) or url)
            cookies = context.cookies()
            return extract_cloudflare_state(
                html,
                page_url=page_url,
                cookies=cookies,
                title=title,
            )
        except Exception:
            return None

    def _wait_for_clearance(self, context: Any) -> dict[str, Any] | None:
        deadline = time.monotonic() + self.config.clearance_timeout / 1000.0
        while time.monotonic() < deadline:
            cookie = _find_clearance_cookie(context.cookies())
            if cookie:
                return cookie
            time.sleep(self.config.poll_interval)
        return None

    def _wait_until_passed(
        self,
        page: Any,
        context: Any,
        url: str,
    ) -> bool:
        deadline = time.monotonic() + self.config.wait_timeout / 1000.0
        while time.monotonic() < deadline:
            if _find_clearance_cookie(context.cookies()):
                return True
            state = self._state(page, context, url)
            if state is not None and not state.present:
                return True
            time.sleep(self.config.poll_interval)
        return False

    def _try_click(self, page: Any) -> bool:
        for selector in self._CLICK_SELECTORS:
            try:
                element = page.query_selector(selector)
                if element:
                    element.click()
                    return True
            except Exception:
                pass
        try:
            frames = list(getattr(page, "frames", []) or [])
        except Exception:
            frames = []
        for frame in frames:
            frame_url = str(getattr(frame, "url", "") or "")
            if "challenges.cloudflare.com" not in frame_url:
                continue
            for selector in self._FRAME_CLICK_SELECTORS:
                try:
                    element = frame.query_selector(selector)
                    if element:
                        element.click()
                        return True
                except Exception:
                    pass
        return False

    def _can_solve_turnstile(self) -> bool:
        return self.captcha_solver is not None and hasattr(
            self.captcha_solver,
            "solve_turnstile",
        )

    def _extract_sitekey(self, page: Any) -> str | None:
        try:
            html = page.content()
            frame_match = _TURNSTILE_SRC_RE.search(html)
            sitekey_match = _SITEKEY_RE.search(frame_match.group(0) if frame_match else html)
            if sitekey_match:
                return sitekey_match.group(1)
        except Exception:
            return None
        return None

    def _solve_and_inject(self, page: Any, url: str, sitekey: str) -> bool:
        try:
            if self.captcha_solver is None:
                return False
            answer = self.captcha_solver.solve_turnstile(sitekey, url)
            token = str(getattr(answer, "answer", "") or "")
            if not token:
                return False
            script = """
            (value) => {
              const el = document.querySelector(
                "textarea[name='cf-turnstile-response'], textarea#cf-turnstile-response"
              );
              if (!el) return false;
              el.value = value;
              el.dispatchEvent(new Event("input", {bubbles: true}));
              el.dispatchEvent(new Event("change", {bubbles: true}));
              return true;
            }
            """
            page.evaluate(script, token)
            return True
        except Exception:
            return False

    def _user_agent(self, page: Any) -> str | None:
        if self.config.user_agent:
            return self.config.user_agent
        try:
            value = page.evaluate("navigator.userAgent")
            return str(value) if value else None
        except Exception:
            return None


if __name__ == "__main__":
    print(
        "desktop-app-dev cloudflare_challenge: import CloudflareChallengeHandler for cf_clearance flows."
    )
