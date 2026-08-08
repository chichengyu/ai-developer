"""Playwright browser session for login, cookies, and consistent fingerprint.

This template is for automating flows the user is authorized to automate.
It keeps one session and one fingerprint per account, persists cookies, and
lets the UI provide a manual CAPTCHA answer when automation cannot solve it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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

    def to_context_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user_agent": self.user_agent,
            "locale": self.locale,
            "timezone_id": self.timezone_id,
        }
        if self.viewport:
            kwargs["viewport"] = self.viewport
        return kwargs


class BrowserSession:
    """One persistent Chromium session per account."""

    def __init__(
        self,
        headless: bool = True,
        proxy: str | None = None,
        user_data_dir: str | Path | None = None,
        fingerprint: FingerprintOptions | None = None,
    ) -> None:
        self.headless = headless
        self.proxy = proxy
        self.user_data_dir = Path(user_data_dir) if user_data_dir else None
        self.fingerprint = fingerprint or FingerprintOptions()
        self._playwright: Any = None
        self._browser: Any = None
        self.context: Any = None
        self.page: Any = None

    def start(self) -> None:
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
        self.context = self._browser.new_context(**kwargs)
        self.page = self.context.new_page()

    def goto(
        self,
        url: str,
        wait_until: str = "domcontentloaded",
        timeout: float = 30000,
    ) -> None:
        self.page.goto(url, wait_until=wait_until, timeout=timeout)

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
        success_selector: str | None = None,
        timeout: float = 30000,
    ) -> None:
        """Fill login fields and wait for a success signal."""
        self.goto(url, timeout=timeout)
        self.page.fill(username_selector, username)
        self.page.fill(password_selector, password)
        if (
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
            self.page.wait_for_selector(success_selector, timeout=timeout)
        else:
            self.page.wait_for_timeout(2000)

    def save_cookies(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.context.cookies(), ensure_ascii=False),
            encoding="utf-8",
        )

    def load_cookies(self, path: str | Path) -> None:
        cookies = json.loads(Path(path).read_text(encoding="utf-8"))
        self.context.add_cookies(cookies)

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
