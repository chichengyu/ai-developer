"""Deep Cloudflare challenge solvers using stealth browser engines.

The adaptive HTTP stack in `smart_fetch.py` handles TLS/JA3/JA4 and simple
JS challenges. Some sites use Managed Challenges or Turnstile that need a
real browser. This module provides optional browser engines that are known
for stronger anti-bot resistance and can cycle through them automatically:

- `patchright` -- undetected Playwright (drop-in sync API)
- `camoufox` -- patched anti-fingerprint Firefox browser
- `scrapling` -- stealth fetcher with built-in Cloudflare solving
- `nodriver` -- CDP-only Chromium automation, no WebDriver
- `seleniumbase` -- SeleniumBase UC / CDP mode
- `undetected_chromedriver` -- patched ChromeDriver
- `drission_page` -- Chromium automation with a self-developed core
- `selenium` -- Selenium WebDriver with stealth injection

All engines are lazy imports. Install them with
`ensure_web_fetch_dependencies.py` or `media_dependencies.py --install`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from browser_flags import ANTI_DETECT_ARGS, BrowserLaunchProfile
from challenge_click import click_any_challenge
from fingerprint_binding import FingerprintBinding, resolve_binding
from fingerprint_manager import FingerprintManager
from proxy_pool import normalize_proxy
from stealth_patches import apply_playwright_stealth, apply_selenium_stealth
from vendor_solver import (
    extract_vendor_public_key,
    has_valid_vendor_cookie,
    inject_captcha_token,
    solve_vendor_slider,
    solve_vendor_with_provider,
)
from waf_vendor import BODY_MARKERS, anti_bot_cookie_present, detect_vendor

STEALTH_ENGINES = (
    "patchright",
    "camoufox",
    "scrapling",
    "nodriver",
    "seleniumbase",
    "undetected_chromedriver",
    "drission_page",
    "selenium",
)
STEALTH_MODULE_NAMES = {
    "patchright": "patchright",
    "camoufox": "camoufox",
    "scrapling": "scrapling",
    "nodriver": "nodriver",
    "seleniumbase": "seleniumbase",
    "undetected_chromedriver": "undetected_chromedriver",
    "drission_page": "DrissionPage",
    "selenium": "selenium",
}
_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "verifying your browser",
    "verify you are human",
    "verify you are not a robot",
    "managed challenge",
    "challenge-platform",
    "attention required",
    "enable javascript and cookies",
    "cf_chl_opt",
    "you are being rate limited",
    "your request has been blocked",
    "请稍候",
    "正在检查您的浏览器",
    "正在验证",
) + tuple(BODY_MARKERS)


def _challenge_pending(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


_BLOCK_WORDING_MARKERS = (
    "access denied",
    "request blocked",
    "your request has been blocked",
    "you are being rate limited",
    "attention required",
    "reference #",
)


def _detect_vendor_from_html(html: str, cookies: Any = None) -> str:
    try:
        return detect_vendor(None, {}, html, cookies).vendor
    except Exception:
        return "generic"


def _enrich_result_variant(result: StealthBrowserResult) -> None:
    if not result.html:
        return
    try:
        detection = detect_vendor(None, {}, result.html, result.cookies)
        result.vendor = detection.vendor
        result.challenge_stage = detection.challenge_stage
        result.challenge_signature = detection.signature
    except Exception:
        pass


def _extract_token_callback(html: str, vendor: str) -> str | None:
    import re

    match = re.search(
        r"data-(?:callback|verify|success-callback)=['\"]([^'\"]+)['\"]",
        html or "",
        re.IGNORECASE,
    )
    if match:
        return match.group(1)
    if vendor in {"aws_waf", "perimeterx"}:
        match = re.search(
            r"(?:onToken|onVerify|onSuccess)\s*[:=]\s*['\"]([^'\"]+)['\"]",
            html or "",
            re.IGNORECASE,
        )
        return match.group(1) if match else None
    return None


def _try_vendor_provider(
    page: Any,
    url: str,
    captcha_solver: Any,
    vendor: str,
) -> bool:
    if captcha_solver is None or vendor in {None, "none", "generic_waf", "cloudflare"}:
        return False
    try:
        html = str(page.content() or "")
        cookies = list(getattr(page.context, "cookies", lambda: [])() or [])
        if has_valid_vendor_cookie(cookies, vendor):
            return False
        public_key = extract_vendor_public_key(html, vendor)
        token = solve_vendor_with_provider(
            captcha_solver,
            vendor,
            url,
            public_key=public_key,
        )
        if not token:
            return False
        callback = _extract_token_callback(html, vendor)
        return inject_captcha_token(page, vendor, token, callback=callback)
    except Exception:
        return False


def _binding_init_script(binding: FingerprintBinding | None) -> str:
    if binding is None:
        return ""
    languages = json.dumps(list(binding.languages), ensure_ascii=False)
    is_chromium = binding.browser_family == "chrome" or binding.header_fingerprint in {
        "edge",
        "msedge",
    }
    device_memory_js = (
        f"""
    Object.defineProperty(navigator, "deviceMemory", {{
      get: () => {binding.device_memory}
    }});
    """
        if is_chromium
        else ""
    )
    return f"""
    Object.defineProperty(navigator, "languages", {{
      get: () => {languages}
    }});
    Object.defineProperty(navigator, "hardwareConcurrency", {{
      get: () => {binding.hardware_concurrency}
    }});
    {device_memory_js}
    """


def _binding_patch_values(
    binding: FingerprintBinding | None,
) -> dict[str, Any] | None:
    if binding is None:
        return None
    return FingerprintManager._patch_values(binding.to_browser_fingerprint())


class StealthBrowserError(RuntimeError):
    """Raised when a stealth browser engine is missing or fails."""


@dataclass
class StealthBrowserResult:
    """Solved HTML plus cookies and user agent from one browser engine."""

    url: str
    html: str = ""
    cookies: list[dict[str, Any]] = field(default_factory=list)
    user_agent: str | None = None
    engine: str = "patchright"
    status: int = 200
    final_url: str = ""
    error: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    proxy: str | None = None
    vendor: str | None = None
    challenge_stage: str | None = None
    challenge_signature: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "engine": self.engine,
            "user_agent": self.user_agent,
            "cookies": self.cookies,
            "proxy": self.proxy,
            "vendor": self.vendor,
            "challenge_stage": self.challenge_stage,
            "challenge_signature": self.challenge_signature,
            "error": self.error,
            "attempts": self.attempts,
        }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available_stealth_engines() -> list[str]:
    """Return installed stealth browser engines in preferred order."""
    return [
        engine
        for engine in STEALTH_ENGINES
        if _module_available(STEALTH_MODULE_NAMES[engine])
    ]


def default_browser_path() -> str | None:
    """Return the first installed Edge/Chrome executable found on Windows."""
    candidates = [
        os.environ.get("BROWSER_PATH"),
        os.environ.get("CHROME_PATH"),
        os.path.expandvars(
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
        ),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        r"D:\soft\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
        ),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def preflight_stealth_engines() -> list[dict[str, Any]]:
    """Return engine availability plus a usable browser binary path."""
    browser_path = default_browser_path()
    return [
        {
            "engine": engine,
            "installed": _module_available(STEALTH_MODULE_NAMES[engine]),
            "browser_path": browser_path,
        }
        for engine in STEALTH_ENGINES
    ]


def _normalize_engine(value: str | None) -> str:
    normalized = str(value or "auto").lower().replace("-", "_")
    if normalized == "playwright":
        return "patchright"
    return normalized


def _ensure_engine_dependencies(engines: list[str]) -> None:
    missing = [
        STEALTH_MODULE_NAMES[engine]
        for engine in engines
        if not _module_available(STEALTH_MODULE_NAMES[engine])
    ]
    if not missing:
        return
    try:
        from ensure_web_fetch_dependencies import ensure as ensure_fetch_deps

        ensure_fetch_deps(install=True, packages=missing)
    except Exception:
        pass


def _cf_clearance_present(result: StealthBrowserResult) -> bool:
    return any(
        str(item.get("name", "") or "").lower() == "cf_clearance"
        and str(item.get("value", "") or "")
        for item in result.cookies or []
    )


def _challenge_cookie_present(cookies: Any) -> bool:
    """Return True when any known vendor challenge cookie is present."""
    return anti_bot_cookie_present(cookies)


def _looks_solved(result: StealthBrowserResult) -> bool:
    if not result.html:
        return False
    vendor = result.vendor or _detect_vendor_from_html(result.html, result.cookies)
    pending = _challenge_pending(result.html)
    if not pending:
        return True
    lowered = result.html.lower()
    if any(marker in lowered for marker in _BLOCK_WORDING_MARKERS):
        return False
    if not _challenge_cookie_present(result.cookies):
        return False
    if vendor == "cloudflare":
        return False
    return not (
        pending
        and result.challenge_stage
        and (
            result.challenge_stage.endswith("_block")
            or result.challenge_stage.endswith("_captcha")
        )
    )


def _record_attempt(
    attempts: list[dict[str, Any]],
    engine: str,
    result: StealthBrowserResult | None,
    error: str | None = None,
    headless: bool | None = None,
) -> None:
    attempts.append(
        {
            "engine": engine,
            "error": error,
            "headless": headless,
            "solved": bool(result is not None and _looks_solved(result)),
            "html_length": len(result.html) if result is not None else 0,
            "cookies": len(result.cookies) if result is not None else 0,
        }
    )


def _store_result_cookies(
    result: StealthBrowserResult,
    url: str,
    cookie_store_path: str | None,
) -> None:
    if not cookie_store_path or not _looks_solved(result):
        return
    try:
        from challenge_cookie_bank import ChallengeCookieBank

        ChallengeCookieBank(cookie_store_path).save(url, result.cookies)
    except Exception:
        pass


def _solve_with_loop(
    url: str,
    engines: list[str],
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    headless_fallback: bool,
    storage_state: str | None,
    timeout_ms: float,
    auto_install: bool,
    max_attempts: int,
    retry_delay: float,
    rotate_proxy_on_fail: bool,
    proxy_pool: Any,
    progress: Callable[[str, float | None, str], None] | None,
    fingerprint_binding: str | dict[str, Any] | FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    if auto_install:
        _ensure_engine_dependencies(engines)
    proxy = normalize_proxy(proxy)
    binding = resolve_binding(fingerprint_binding)
    installed = set(available_stealth_engines())
    order = [engine for engine in engines if engine in installed]
    if not order:
        order = [engine for engine in engines if engine in STEALTH_MODULE_NAMES]
    browser_path = browser_path or default_browser_path()
    attempts: list[dict[str, Any]] = []
    last: StealthBrowserResult | None = None
    best_cookie_result: StealthBrowserResult | None = None
    rounds = max(1, int(max_attempts))
    for round_no in range(rounds):
        for engine in order:
            current_proxy = proxy
            if proxy_pool is not None:
                current_proxy = normalize_proxy(proxy_pool.get_proxy() or current_proxy)
            modes = [False] if not headless else ([True, False] if headless_fallback else [True])
            engine_failed = False
            for mode in modes:
                mode_name = "headless" if mode else "headed"
                if progress is not None:
                    progress(
                        "challenge",
                        (round_no + 1) / rounds,
                        f"browser engine {engine} {mode_name} attempt {round_no + 1}",
                    )
                try:
                    result = _solve_engine(
                        engine,
                        url,
                        proxy=current_proxy,
                        browser_path=browser_path,
                        headless=mode,
                        storage_state=storage_state,
                        timeout_ms=timeout_ms,
                        fingerprint=binding,
                        captcha_solver=captcha_solver,
                    )
                except Exception as exc:
                    _record_attempt(
                        attempts,
                        engine,
                        None,
                        error=str(exc),
                        headless=mode,
                    )
                    last = StealthBrowserResult(url=url, engine=engine, error=str(exc))
                    engine_failed = True
                    continue
                _enrich_result_variant(result)
                _record_attempt(attempts, engine, result, headless=mode)
                if _looks_solved(result):
                    result.proxy = current_proxy
                    result.attempts = attempts
                    return result
                if best_cookie_result is None and _challenge_cookie_present(result.cookies):
                    best_cookie_result = result
                    best_cookie_result.proxy = current_proxy
                last = result
                last.proxy = current_proxy
                engine_failed = True
            if best_cookie_result is not None:
                break
            if engine_failed and proxy_pool is not None and current_proxy and rotate_proxy_on_fail:
                proxy_pool.report_failure(current_proxy)
            time.sleep(max(0.0, retry_delay))
        if best_cookie_result is not None:
            break
    if best_cookie_result is not None:
        best_cookie_result.attempts = attempts
        best_cookie_result.error = best_cookie_result.error or (
            "challenge cookie obtained but page still pending"
        )
        _enrich_result_variant(best_cookie_result)
        return best_cookie_result
    if last is None:
        last = StealthBrowserResult(
            url=url,
            engine="auto",
            error="no stealth browser engine produced a page",
        )
    last.attempts = attempts
    last.error = last.error or "cloudflare challenge did not clear"
    last.proxy = proxy
    _enrich_result_variant(last)
    return last


def _solve_engine(
    engine: str,
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    storage_state: str | None = None,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    if engine == "patchright":
        return _solve_patchright(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            storage_state=storage_state,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "camoufox":
        return _solve_camoufox(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            storage_state=storage_state,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "scrapling":
        return _solve_scrapling(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "nodriver":
        return _solve_nodriver(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "seleniumbase":
        return _solve_seleniumbase(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "undetected_chromedriver":
        return _solve_undetected_chromedriver(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "drission_page":
        return _solve_drission(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    if engine == "selenium":
        return _solve_selenium(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
            fingerprint=fingerprint,
            captcha_solver=captcha_solver,
        )
    raise StealthBrowserError(f"unsupported stealth browser engine: {engine}")


def solve_cloudflare_with_stealth_browser(
    url: str,
    engine: str = "auto",
    *,
    engine_order: list[str] | tuple[str, ...] | None = None,
    proxy: str | None = None,
    browser_path: str | None = None,
    headless: bool = True,
    headless_fallback: bool = True,
    storage_state: str | None = None,
    cookie_store_path: str | None = None,
    timeout_ms: float = 60000,
    auto_install: bool = True,
    max_attempts: int = 1,
    retry_delay: float = 2.0,
    rotate_proxy_on_fail: bool = False,
    proxy_pool: Any = None,
    progress: Callable[[str, float | None, str], None] | None = None,
    fingerprint_binding: str | dict[str, Any] | FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    """Solve a Cloudflare challenge, cycling engines until one clears."""
    engine = _normalize_engine(engine)
    if engine in {"auto", "adaptive", "smart"}:
        engines = [
            _normalize_engine(item)
            for item in (engine_order or STEALTH_ENGINES)
            if _normalize_engine(item) in STEALTH_MODULE_NAMES
        ]
        result = _solve_with_loop(
            url,
            engines,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            headless_fallback=headless_fallback,
            storage_state=storage_state,
            timeout_ms=timeout_ms,
            auto_install=auto_install,
            max_attempts=max_attempts,
            retry_delay=retry_delay,
            rotate_proxy_on_fail=rotate_proxy_on_fail,
            proxy_pool=proxy_pool,
            progress=progress,
            fingerprint_binding=fingerprint_binding,
            captcha_solver=captcha_solver,
        )
        _store_result_cookies(result, url, cookie_store_path)
        return result
    if engine not in STEALTH_MODULE_NAMES:
        raise StealthBrowserError(f"unsupported stealth browser engine: {engine}")
    if auto_install:
        _ensure_engine_dependencies([engine])
    result = _solve_with_loop(
        url,
        [engine],
        proxy=proxy,
        browser_path=browser_path,
        headless=headless,
        headless_fallback=headless_fallback,
        storage_state=storage_state,
        timeout_ms=timeout_ms,
        auto_install=auto_install,
        max_attempts=max_attempts,
        retry_delay=retry_delay,
        rotate_proxy_on_fail=rotate_proxy_on_fail,
        proxy_pool=proxy_pool,
        progress=progress,
        fingerprint_binding=fingerprint_binding,
        captcha_solver=captcha_solver,
    )
    _store_result_cookies(result, url, cookie_store_path)
    return result


def _solve_patchright(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    storage_state: str | None = None,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as exc:
        raise StealthBrowserError(
            "patchright is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    with sync_playwright() as playwright:
        launch_kwargs: dict[str, Any] = {"headless": headless}
        launch_args = list(ANTI_DETECT_ARGS)
        if fingerprint is not None:
            launch_args.append(
                f"--lang={fingerprint.languages[0]}" if fingerprint.languages else "--lang=en-US"
            )
        launch_kwargs["args"] = launch_args
        if browser_path:
            launch_kwargs["executable_path"] = browser_path
        browser = playwright.chromium.launch(**launch_kwargs)
        context_kwargs: dict[str, Any] = {}
        if proxy:
            context_kwargs["proxy"] = {"server": proxy}
        if fingerprint is not None:
            context_kwargs["user_agent"] = fingerprint.user_agent
            context_kwargs["locale"] = (
                fingerprint.languages[0] if fingerprint.languages else "en-US"
            )
            context_kwargs["timezone_id"] = fingerprint.timezone_id
        if storage_state and os.path.isfile(storage_state):
            context_kwargs["storage_state"] = storage_state
        try:
            context = browser.new_context(**context_kwargs)
        except Exception:
            context_kwargs.pop("storage_state", None)
            context = browser.new_context(**context_kwargs)
        if fingerprint is not None:
            context.add_init_script(_binding_init_script(fingerprint))
        apply_playwright_stealth(
            context,
            None,
            values=_binding_patch_values(fingerprint),
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        from turnstile_solver import TurnstileSolver

        turnstile_result = TurnstileSolver(
            config={"wait_timeout": 5000, "poll_interval": 0.5, "max_attempts": 1},
            captcha_solver=captcha_solver,
        ).solve_page(page, url)
        if turnstile_result.passed:
            with suppress(Exception):
                page.reload(wait_until="domcontentloaded", timeout=15000)
        deadline = time.monotonic() + timeout_ms / 1000.0
        html = ""
        no_challenge_since: float | None = None
        clearance_reloads = 0
        clicked_generic_challenge = False
        while time.monotonic() < deadline:
            with suppress(Exception):
                html = page.content()
            cookies = context.cookies()
            has_challenge_cookie = _challenge_cookie_present(cookies)
            title = ""
            with suppress(Exception):
                title = page.title().lower() if hasattr(page, "title") else ""
            if not html:
                time.sleep(1.0)
                continue
            no_challenge = not _challenge_pending(f"{title}\n{html}")
            if no_challenge:
                if has_challenge_cookie:
                    break
                if no_challenge_since is None:
                    no_challenge_since = time.monotonic()
                elif time.monotonic() - no_challenge_since >= 10.0:
                    break
            else:
                no_challenge_since = None
                vendor = _detect_vendor_from_html(html)
                if _try_vendor_provider(page, url, captcha_solver, vendor):
                    time.sleep(1.0)
                    continue
                if solve_vendor_slider(page, vendor):
                    time.sleep(1.0)
                    continue
                if not clicked_generic_challenge:
                    with suppress(Exception):
                        clicked_generic_challenge = click_any_challenge(
                            page,
                            vendor=vendor,
                        )
            if (
                has_challenge_cookie
                and _challenge_pending(f"{title}\n{html}")
                and clearance_reloads < 4
            ):
                clearance_reloads += 1
                clicked_generic_challenge = False
                remaining = max(0.0, deadline - time.monotonic())
                with suppress(Exception):
                    page.reload(
                        wait_until="domcontentloaded",
                        timeout=min(15000, int(remaining * 1000)),
                    )
                time.sleep(1.0)
                continue
            time.sleep(1.0)
        with suppress(Exception):
            html = page.content()
        if _challenge_pending(html) and _challenge_cookie_present(context.cookies()):
            with suppress(Exception):
                page.reload(wait_until="domcontentloaded", timeout=min(15000, int(max(0.0, deadline - time.monotonic()) * 1000) or 15000))
            with suppress(Exception):
                click_any_challenge(page, vendor=_detect_vendor_from_html(html))
            time.sleep(2.0)
            with suppress(Exception):
                html = page.content()
        cookies = context.cookies()
        user_agent = ""
        final_url = ""
        with suppress(Exception):
            user_agent = page.evaluate("navigator.userAgent")
        with suppress(Exception):
            final_url = page.url
        if storage_state:
            with suppress(Exception):
                context.storage_state(path=storage_state)
        browser.close()
    return StealthBrowserResult(
        url=url,
        html=html,
        cookies=_normalize_cookies(cookies, url),
        user_agent=str(user_agent) if user_agent else None,
        engine="patchright",
        final_url=final_url,
    )


def _solve_nodriver(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        import nodriver as uc
    except ImportError as exc:
        raise StealthBrowserError(
            "nodriver is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc

    async def run() -> StealthBrowserResult:
        browser_args: list[str] = list(ANTI_DETECT_ARGS)
        if proxy:
            browser_args.append(f"--proxy-server={proxy}")
        if fingerprint is not None:
            browser_args.append(f"--user-agent={fingerprint.user_agent}")
            browser_args.append(
                f"--lang={fingerprint.languages[0]}" if fingerprint.languages else "--lang=en-US"
            )
            browser_args.append(f"--timezone={fingerprint.timezone_id}")
        start_kwargs: dict[str, Any] = {
            "headless": headless,
            "browser_args": browser_args,
        }
        if browser_path:
            start_kwargs["browser_executable_path"] = browser_path
        browser = await uc.start(**start_kwargs)
        tab = await browser.get(url)
        if hasattr(tab, "cf_verify"):
            with suppress(Exception):
                await tab.cf_verify()
        deadline = time.monotonic() + timeout_ms / 1000.0
        html = ""
        cookies: list[Any] = []
        user_agent: str | None = None
        no_challenge_since: float | None = None
        clearance_reloads = 0
        while time.monotonic() < deadline:
            html = await tab.get_content()
            cookies = await _nodriver_cookies(browser, cookies)
            with suppress(Exception):
                user_agent = await tab.evaluate("navigator.userAgent")
            lowered = html.lower()
            has_challenge_cookie = _challenge_cookie_present(cookies)
            no_challenge = not _challenge_pending(lowered)
            if no_challenge:
                if has_challenge_cookie:
                    break
                if no_challenge_since is None:
                    no_challenge_since = time.monotonic()
                elif time.monotonic() - no_challenge_since >= 10.0:
                    break
            else:
                no_challenge_since = None
            if has_challenge_cookie and not no_challenge and clearance_reloads < 2:
                clearance_reloads += 1
                with suppress(Exception):
                    await tab.reload()
                await tab.sleep(1)
                continue
            await tab.sleep(1)
        with suppress(Exception):
            browser.stop()
        final_url = tab.url
        return StealthBrowserResult(
            url=url,
            html=html,
            cookies=_normalize_cookies(cookies, url),
            user_agent=user_agent,
            engine="nodriver",
            final_url=final_url,
        )

    loop = uc.loop()
    return loop.run_until_complete(run())


async def _nodriver_cookies(browser: Any, fallback: list[Any]) -> list[Any]:
    jar = getattr(browser, "cookies", None)
    get_all = getattr(jar, "get_all", None)
    if get_all is not None:
        try:
            value = await get_all()
            if value:
                return list(value)
        except Exception:
            pass
    return list(fallback)


def _solve_drission(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
    except ImportError as exc:
        raise StealthBrowserError(
            "DrissionPage is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    options = ChromiumOptions()
    options.headless(headless)
    for arg in ANTI_DETECT_ARGS:
        with suppress(Exception):
            options.set_argument(arg)
    if browser_path:
        options.set_browser_path(browser_path)
    if proxy:
        try:
            options.set_proxy(proxy)
        except Exception:
            options.set_argument("--proxy-server", proxy)
    if fingerprint is not None:
        with suppress(Exception):
            options.set_user_agent(fingerprint.user_agent)
        if fingerprint.languages:
            with suppress(Exception):
                options.set_argument(f"--lang={fingerprint.languages[0]}")
    page = ChromiumPage(options)
    page.get(url)
    deadline = time.monotonic() + timeout_ms / 1000.0
    html = ""
    challenge_reloads = 0
    while time.monotonic() < deadline:
        html = page.html
        lowered = html.lower()
        if not _challenge_pending(lowered):
            break
        try:
            has_challenge_cookie = _challenge_cookie_present(page.cookies())
        except Exception:
            has_challenge_cookie = False
        if has_challenge_cookie and challenge_reloads < 2:
            challenge_reloads += 1
            with suppress(Exception):
                page.refresh()
            continue
        page.wait(1)
    try:
        cookies = page.cookies()
    except Exception:
        cookies = []
    try:
        user_agent = page.run_js("return navigator.userAgent")
    except Exception:
        user_agent = None
    try:
        final_url = page.url
    except Exception:
        final_url = url
    page.quit()
    return StealthBrowserResult(
        url=url,
        html=html,
        cookies=_normalize_cookies(cookies, url),
        user_agent=str(user_agent) if user_agent else None,
        engine="drission_page",
        final_url=final_url,
    )


def _wait_for_browser_ready(
    html_getter: Callable[[], str],
    cookie_getter: Callable[[], list[Any]],
    timeout_ms: float,
    click_callback: Callable[[], None] | None = None,
    reload_callback: Callable[[], None] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000.0
    no_challenge_since: float | None = None
    clearance_reloads = 0
    clicked_challenge = False
    while time.monotonic() < deadline:
        html = html_getter()
        cookies = cookie_getter()
        lowered = html.lower()
        has_challenge_cookie = _challenge_cookie_present(cookies)
        no_challenge = not _challenge_pending(lowered)
        if no_challenge:
            if has_challenge_cookie:
                return True
            if no_challenge_since is None:
                no_challenge_since = time.monotonic()
            elif time.monotonic() - no_challenge_since >= 10.0:
                return True
        else:
            no_challenge_since = None
            if click_callback is not None and not clicked_challenge:
                try:
                    click_callback()
                    clicked_challenge = True
                except Exception:
                    pass
        if has_challenge_cookie and not no_challenge and clearance_reloads < 2:
            clearance_reloads += 1
            clicked_challenge = False
            if reload_callback is not None:
                with suppress(Exception):
                    reload_callback()
            time.sleep(1.0)
            continue
        if has_challenge_cookie and not no_challenge and clearance_reloads >= 2:
            return True
        time.sleep(1.0)
    return False


def _solve_seleniumbase(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        from seleniumbase import Driver
    except ImportError as exc:
        raise StealthBrowserError(
            "seleniumbase is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    kwargs = BrowserLaunchProfile(
        headless=headless,
        user_agent=fingerprint.user_agent if fingerprint is not None else None,
        locale=fingerprint.languages[0] if fingerprint is not None and fingerprint.languages else "zh-CN",
    ).seleniumbase_kwargs()
    if proxy:
        kwargs["proxy"] = proxy
    if browser_path:
        kwargs["binary_location"] = browser_path
    driver = Driver(**kwargs)
    try:
        apply_selenium_stealth(driver, values=_binding_patch_values(fingerprint))
        try:
            driver.uc_open_with_reconnect(url, 4)
        except Exception:
            driver.get(url)

        def click_captcha() -> None:
            if hasattr(driver, "uc_gui_click_captcha"):
                driver.uc_gui_click_captcha()

        _wait_for_browser_ready(
            lambda: str(driver.page_source or ""),
            lambda: list(driver.get_cookies()),
            timeout_ms,
            click_callback=click_captcha,
            reload_callback=lambda: driver.refresh(),
        )
        html = str(driver.page_source or "")
        cookies = list(driver.get_cookies())
        user_agent = driver.execute_script("return navigator.userAgent")
        final_url = str(driver.current_url or url)
    finally:
        with suppress(Exception):
            driver.quit()
    return StealthBrowserResult(
        url=url,
        html=html,
        cookies=_normalize_cookies(cookies, final_url),
        user_agent=str(user_agent) if user_agent else None,
        engine="seleniumbase",
        final_url=final_url,
    )


def _solve_undetected_chromedriver(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        import undetected_chromedriver as uc
    except ImportError as exc:
        raise StealthBrowserError(
            "undetected_chromedriver is not installed; "
            "run ensure_web_fetch_dependencies.py"
        ) from exc
    options = uc.ChromeOptions()
    BrowserLaunchProfile(
        headless=headless,
        user_agent=fingerprint.user_agent if fingerprint is not None else None,
        locale=fingerprint.languages[0] if fingerprint is not None and fingerprint.languages else "zh-CN",
    ).apply_undetected_options(options, proxy=proxy)
    if browser_path:
        options.binary_location = browser_path
    driver = uc.Chrome(options=options, headless=headless)
    try:
        driver.get(url)
        _wait_for_browser_ready(
            lambda: str(driver.page_source or ""),
            lambda: list(driver.get_cookies()),
            timeout_ms,
            reload_callback=lambda: driver.refresh(),
        )
        html = str(driver.page_source or "")
        cookies = list(driver.get_cookies())
        user_agent = driver.execute_script("return navigator.userAgent")
        final_url = str(driver.current_url or url)
    finally:
        with suppress(Exception):
            driver.quit()
    return StealthBrowserResult(
        url=url,
        html=html,
        cookies=_normalize_cookies(cookies, final_url),
        user_agent=str(user_agent) if user_agent else None,
        engine="undetected_chromedriver",
        final_url=final_url,
    )


def _solve_selenium(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        from selenium import webdriver
    except ImportError as exc:
        raise StealthBrowserError(
            "selenium is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    options = webdriver.ChromeOptions()
    BrowserLaunchProfile(
        headless=headless,
        user_agent=fingerprint.user_agent if fingerprint is not None else None,
        locale=fingerprint.languages[0] if fingerprint is not None and fingerprint.languages else "zh-CN",
    ).apply_chrome_options(options, proxy=proxy)
    if browser_path:
        options.binary_location = browser_path
    service = None
    try:
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        service = Service(ChromeDriverManager().install())
    except Exception:
        service = None
    driver = webdriver.Chrome(options=options, service=service)
    try:
        apply_selenium_stealth(driver, values=_binding_patch_values(fingerprint))
        driver.get(url)
        _wait_for_browser_ready(
            lambda: str(driver.page_source or ""),
            lambda: list(driver.get_cookies()),
            timeout_ms,
            reload_callback=lambda: driver.refresh(),
        )
        html = str(driver.page_source or "")
        cookies = list(driver.get_cookies())
        user_agent = driver.execute_script("return navigator.userAgent")
        final_url = str(driver.current_url or url)
    finally:
        with suppress(Exception):
            driver.quit()
    return StealthBrowserResult(
        url=url,
        html=html,
        cookies=_normalize_cookies(cookies, final_url),
        user_agent=str(user_agent) if user_agent else None,
        engine="selenium",
        final_url=final_url,
    )


def _solve_camoufox(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    storage_state: str | None = None,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        from camoufox.sync_api import Camoufox
    except ImportError as exc:
        raise StealthBrowserError(
            "camoufox is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    html = ""
    cookies: list[Any] = []
    user_agent: str | None = None
    final_url = url
    with Camoufox(headless=headless) as browser:
        page_kwargs: dict[str, Any] = {}
        if proxy:
            page_kwargs["proxy"] = {"server": proxy}
        if storage_state and os.path.isfile(storage_state):
            page_kwargs["storage_state"] = storage_state
        try:
            page = browser.new_page(**page_kwargs)
        except Exception:
            page_kwargs.pop("storage_state", None)
            page = browser.new_page(**page_kwargs)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        from turnstile_solver import TurnstileSolver

        TurnstileSolver(
            config={"wait_timeout": 5000, "poll_interval": 0.5, "max_attempts": 1},
            captcha_solver=captcha_solver,
        ).solve_page(page, url)

        def click_turnstile() -> None:
            vendor = _detect_vendor_from_html(str(page.content()))
            if _try_vendor_provider(page, url, captcha_solver, vendor):
                return
            if solve_vendor_slider(page, vendor):
                return
            if click_any_challenge(page, vendor=vendor):
                return
            for frame in page.frames:
                if "challenges.cloudflare.com" not in frame.url:
                    continue
                with suppress(Exception):
                    frame.click("input[type='checkbox']", timeout=1200)

        _wait_for_browser_ready(
            lambda: str(page.content()),
            lambda: list(page.context.cookies()),
            timeout_ms,
            click_callback=click_turnstile,
            reload_callback=lambda: page.reload(
                wait_until="domcontentloaded",
                timeout=min(15000, int(timeout_ms)),
            ),
        )
        html = str(page.content())
        cookies = list(page.context.cookies())
        with suppress(Exception):
            user_agent = str(page.evaluate("navigator.userAgent"))
        final_url = str(page.url or url)
        if storage_state:
            with suppress(Exception):
                page.context.storage_state(path=storage_state)
    return StealthBrowserResult(
        url=url,
        html=html,
        cookies=_normalize_cookies(cookies, final_url),
        user_agent=user_agent,
        engine="camoufox",
        final_url=final_url,
    )


def _solve_scrapling(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
    fingerprint: FingerprintBinding | None = None,
    captcha_solver: Any = None,
) -> StealthBrowserResult:
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError as exc:
        raise StealthBrowserError(
            "scrapling is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    kwargs: dict[str, Any] = {
        "headless": headless,
        "solve_cloudflare": True,
        "timeout": max(60000, int(timeout_ms)),
    }
    if proxy:
        kwargs["proxy"] = proxy
    if browser_path:
        kwargs["executable_path"] = browser_path
    if fingerprint is not None:
        kwargs["useragent"] = fingerprint.user_agent
    response = StealthyFetcher.fetch(url, **kwargs)
    html = getattr(response, "text", None)
    if not html:
        body = getattr(response, "body", b"")
        html = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body or "")
    raw_cookies = getattr(response, "cookies", []) or []
    if hasattr(raw_cookies, "get_dict"):
        raw_cookies = [
            {"name": key, "value": value}
            for key, value in raw_cookies.get_dict().items()
        ]
    user_agent = getattr(response, "user_agent", None)
    final_url = str(getattr(response, "url", url) or url)
    status = int(getattr(response, "status", 200) or 200)
    return StealthBrowserResult(
        url=url,
        html=str(html),
        cookies=_normalize_cookies(raw_cookies, final_url),
        user_agent=str(user_agent) if user_agent else None,
        engine="scrapling",
        status=status,
        final_url=final_url,
    )


def _normalize_cookies(
    cookies: list[Any] | tuple[Any, ...],
    url: str,
) -> list[dict[str, Any]]:
    default_domain = ""
    with suppress(Exception):
        from urllib.parse import urlsplit

        default_domain = urlsplit(url).hostname or ""
    normalized: list[dict[str, Any]] = []
    for item in cookies or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            value = str(item.get("value") or "")
            if not name or not value:
                continue
            domain = str(item.get("domain") or default_domain)
            normalized.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": str(item.get("path") or "/"),
                    "secure": bool(item.get("secure", False)),
                    "httpOnly": bool(item.get("httpOnly", False)),
                    "sameSite": item.get("sameSite"),
                    "expires": item.get("expires"),
                    "session": bool(item.get("session", False)),
                }
            )
        elif hasattr(item, "name") and hasattr(item, "value"):
            domain = str(getattr(item, "domain", "") or default_domain)
            normalized.append(
                {
                    "name": str(item.name),
                    "value": str(item.value),
                    "domain": domain,
                    "path": str(getattr(item, "path", "/") or "/"),
                    "secure": bool(getattr(item, "secure", False)),
                    "httpOnly": bool(
                        getattr(item, "httpOnly", None) or getattr(item, "http_only", None)
                    ),
                    "sameSite": _enum_value(
                        getattr(item, "sameSite", None) or getattr(item, "same_site", None)
                    ),
                    "expires": getattr(item, "expires", None),
                    "session": bool(getattr(item, "session", False)),
                }
            )
    return normalized


def _enum_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Solve a Cloudflare-protected URL with a stealth browser engine."
    )
    parser.add_argument("--url", default=None)
    parser.add_argument(
        "--engine",
        default="auto",
        choices=["auto", *STEALTH_ENGINES],
    )
    parser.add_argument(
        "--engine-order",
        default=None,
        help="comma-separated engine order, e.g. patchright,camoufox,scrapling",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--headless-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="retry the same engine in headed mode when a headless attempt stays challenged",
    )
    parser.add_argument("--storage-state", default=None, help="Playwright storage state JSON path")
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--browser-path", default=None)
    parser.add_argument("--timeout-ms", type=float, default=60000)
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument(
        "--rotate-proxy-on-fail",
        action="store_true",
        help="mark the current proxy as failed before the next browser attempt",
    )
    parser.add_argument("--check", action="store_true", help="list installed engines")
    parser.add_argument(
        "--auto-install",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="auto-install a missing engine before solving (default: enabled)",
    )
    parser.add_argument(
        "--fingerprint-binding",
        "--profile",
        default=None,
        help="full-chain fingerprint profile, e.g. chrome126, firefox127",
    )
    args = parser.parse_args(argv)
    if args.check:
        print(
            json.dumps(
                {
                    "installed": available_stealth_engines(),
                    "preflight": preflight_stealth_engines(),
                    "browser_path": default_browser_path(),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not args.url:
        parser.error("--url is required unless --check is used")
    engine_order = None
    if args.engine_order:
        engine_order = [
            item.strip()
            for item in args.engine_order.split(",")
            if item.strip()
        ]
    result = solve_cloudflare_with_stealth_browser(
        args.url,
        engine=args.engine,
        engine_order=engine_order,
        proxy=args.proxy,
        browser_path=args.browser_path,
        headless=args.headless,
        headless_fallback=args.headless_fallback,
        storage_state=args.storage_state,
        timeout_ms=args.timeout_ms,
        auto_install=args.auto_install,
        max_attempts=args.max_attempts,
        retry_delay=args.retry_delay,
        rotate_proxy_on_fail=args.rotate_proxy_on_fail,
        fingerprint_binding=args.fingerprint_binding,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
