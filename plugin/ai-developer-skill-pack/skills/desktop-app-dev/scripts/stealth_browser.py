"""Deep Cloudflare challenge solvers using stealth browser engines.

The adaptive HTTP stack in `smart_fetch.py` handles TLS/JA3/JA4 and simple
JS challenges. Some sites use Managed Challenges or Turnstile that need a
real browser. This module provides optional browser engines that are known
for stronger anti-bot resistance:

- `patchright` -- undetected Playwright (drop-in sync API)
- `nodriver` -- CDP-only Chromium automation, no WebDriver
- `drission_page` -- Chromium automation with a self-developed core

All engines are lazy imports. Install them with
`ensure_web_fetch_dependencies.py` or `media_dependencies.py --install`.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

STEALTH_ENGINES = ("patchright", "nodriver", "drission_page")
STEALTH_MODULE_NAMES = {
    "patchright": "patchright",
    "nodriver": "nodriver",
    "drission_page": "DrissionPage",
}


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status": self.status,
            "engine": self.engine,
            "user_agent": self.user_agent,
            "cookies": self.cookies,
        }


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available_stealth_engines() -> list[str]:
    """Return installed stealth browser engines in preferred order."""
    return [engine for engine in STEALTH_ENGINES if _module_available(STEALTH_MODULE_NAMES[engine])]


def solve_cloudflare_with_stealth_browser(
    url: str,
    engine: str = "patchright",
    *,
    proxy: str | None = None,
    browser_path: str | None = None,
    headless: bool = True,
    timeout_ms: float = 60000,
    auto_install: bool = True,
) -> StealthBrowserResult:
    """Solve a Cloudflare challenge with one configured browser engine."""
    engine = str(engine or "patchright").lower().replace("-", "_")
    if engine not in STEALTH_MODULE_NAMES:
        raise StealthBrowserError(f"unsupported stealth browser engine: {engine}")
    if auto_install and not _module_available(STEALTH_MODULE_NAMES[engine]):
        try:
            from ensure_web_fetch_dependencies import ensure as ensure_fetch_deps

            ensure_fetch_deps(
                install=True,
                packages=[STEALTH_MODULE_NAMES[engine]],
            )
        except Exception:
            pass
    if engine == "patchright":
        return _solve_patchright(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
        )
    if engine == "nodriver":
        return _solve_nodriver(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
        )
    if engine == "drission_page":
        return _solve_drission(
            url,
            proxy=proxy,
            browser_path=browser_path,
            headless=headless,
            timeout_ms=timeout_ms,
        )
    raise StealthBrowserError(f"unsupported stealth browser engine: {engine}")


def _solve_patchright(
    url: str,
    *,
    proxy: str | None,
    browser_path: str | None,
    headless: bool,
    timeout_ms: float,
) -> StealthBrowserResult:
    try:
        from patchright.sync_api import sync_playwright
    except ImportError as exc:
        raise StealthBrowserError(
            "patchright is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    with sync_playwright() as playwright:
        launch_kwargs: dict[str, Any] = {"headless": headless}
        if browser_path:
            launch_kwargs["executable_path"] = browser_path
        browser = playwright.chromium.launch(**launch_kwargs)
        context_kwargs: dict[str, Any] = {}
        if proxy:
            context_kwargs["proxy"] = {"server": proxy}
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        deadline = time.monotonic() + timeout_ms / 1000.0
        no_challenge_since: float | None = None
        while time.monotonic() < deadline:
            cookies = context.cookies()
            has_clearance = any(
                str(item.get("name", "")).lower() == "cf_clearance" for item in cookies
            )
            title = page.title().lower() if hasattr(page, "title") else ""
            no_challenge = "just a moment" not in title and "checking your browser" not in title
            if no_challenge:
                if has_clearance:
                    break
                if no_challenge_since is None:
                    no_challenge_since = time.monotonic()
                elif time.monotonic() - no_challenge_since >= 10.0:
                    break
            else:
                no_challenge_since = None
            time.sleep(1.0)
        html = page.content()
        cookies = context.cookies()
        user_agent = page.evaluate("navigator.userAgent")
        final_url = page.url
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
) -> StealthBrowserResult:
    try:
        import nodriver as uc
    except ImportError as exc:
        raise StealthBrowserError(
            "nodriver is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc

    async def run() -> StealthBrowserResult:
        browser_args: list[str] = []
        if proxy:
            browser_args.append(f"--proxy-server={proxy}")
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
        while time.monotonic() < deadline:
            html = await tab.get_content()
            cookies = await _nodriver_cookies(browser, cookies)
            with suppress(Exception):
                user_agent = await tab.evaluate("navigator.userAgent")
            lowered = html.lower()
            has_clearance = any(
                str(item.get("name") or "").lower() == "cf_clearance"
                for item in _normalize_cookies(cookies, url)
            )
            no_challenge = "just a moment" not in lowered and "checking your browser" not in lowered
            if no_challenge:
                if has_clearance:
                    break
                if no_challenge_since is None:
                    no_challenge_since = time.monotonic()
                elif time.monotonic() - no_challenge_since >= 10.0:
                    break
            else:
                no_challenge_since = None
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
) -> StealthBrowserResult:
    try:
        from DrissionPage import ChromiumOptions, ChromiumPage
    except ImportError as exc:
        raise StealthBrowserError(
            "DrissionPage is not installed; run ensure_web_fetch_dependencies.py"
        ) from exc
    options = ChromiumOptions()
    options.headless(headless)
    if browser_path:
        options.set_browser_path(browser_path)
    if proxy:
        try:
            options.set_proxy(proxy)
        except Exception:
            options.set_argument("--proxy-server", proxy)
    page = ChromiumPage(options)
    page.get(url)
    deadline = time.monotonic() + timeout_ms / 1000.0
    html = ""
    while time.monotonic() < deadline:
        html = page.html
        lowered = html.lower()
        if "just a moment" not in lowered and "checking your browser" not in lowered:
            break
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


def _normalize_cookies(
    cookies: list[Any] | tuple[Any, ...],
    url: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in cookies or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            value = str(item.get("value") or "")
            if not name or not value:
                continue
            normalized.append(
                {
                    "name": name,
                    "value": value,
                    "domain": str(item.get("domain") or ""),
                    "path": str(item.get("path") or "/"),
                    "secure": bool(item.get("secure", False)),
                    "httpOnly": bool(item.get("httpOnly", False)),
                    "sameSite": item.get("sameSite"),
                    "expires": item.get("expires"),
                    "session": bool(item.get("session", False)),
                }
            )
        elif hasattr(item, "name") and hasattr(item, "value"):
            normalized.append(
                {
                    "name": str(item.name),
                    "value": str(item.value),
                    "domain": str(getattr(item, "domain", "") or ""),
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
        default="patchright",
        choices=STEALTH_ENGINES,
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--browser-path", default=None)
    parser.add_argument("--timeout-ms", type=float, default=60000)
    parser.add_argument("--check", action="store_true", help="list installed engines")
    parser.add_argument(
        "--auto-install",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="auto-install a missing engine before solving (default: enabled)",
    )
    args = parser.parse_args(argv)
    if args.check:
        print(json.dumps({"installed": available_stealth_engines()}, ensure_ascii=False))
        return 0
    if not args.url:
        parser.error("--url is required unless --check is used")
    result = solve_cloudflare_with_stealth_browser(
        args.url,
        engine=args.engine,
        proxy=args.proxy,
        browser_path=args.browser_path,
        headless=args.headless,
        timeout_ms=args.timeout_ms,
        auto_install=args.auto_install,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
