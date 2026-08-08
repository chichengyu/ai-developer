#!/usr/bin/env python3
"""Capture an authenticated browser session for scraper tools.

Opens a real browser window. When the user provides --username and --password,
the script fills an ordinary login form and submits it. Any CAPTCHA, SMS, or
two-factor step must still be completed by the user in the opened browser.
After login, the session is saved as JSON that scraper tools can load with
--cookies-file. This script never solves CAPTCHAs or bypasses access controls.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import List, Optional

USERNAME_SELECTORS = (
    'input[name="username"]',
    'input[name="email"]',
    'input[name="account"]',
    'input[name="login"]',
    'input[name="user"]',
    'input[name="phone"]',
    'input[type="email"]',
    'input[autocomplete="username"]',
    '#username',
    '#email',
)

PASSWORD_SELECTORS = (
    'input[type="password"]',
    'input[name="password"]',
    'input[name="passwd"]',
    'input[autocomplete="current-password"]',
)

SUBMIT_SELECTORS = (
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Login")',
    'button:has-text("Sign in")',
    'button:has-text("Sign In")',
    'button:has-text("登录")',
    'button:has-text("登 录")',
)


def _first_visible(page, selectors, timeout_ms: int = 3000):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception:
            continue
    return None


def _try_autofill(page, args) -> None:
    if not args.username or not args.password:
        return
    username_selectors = (args.username_selector,) if args.username_selector else USERNAME_SELECTORS
    password_selectors = (args.password_selector,) if args.password_selector else PASSWORD_SELECTORS
    username_locator = _first_visible(page, username_selectors)
    password_locator = _first_visible(page, password_selectors)
    if username_locator is None or password_locator is None:
        print("Could not locate the login form; complete login manually.")
        return
    username_locator.fill(args.username)
    password_locator.fill(args.password)
    submit_clicked = False
    if args.submit_selector:
        submit_locator = _first_visible(page, (args.submit_selector,))
        if submit_locator is not None:
            submit_locator.click()
            submit_clicked = True
    else:
        submit_locator = _first_visible(page, SUBMIT_SELECTORS)
        if submit_locator is not None:
            submit_locator.click()
            submit_clicked = True
    if not submit_clicked:
        page.keyboard.press("Enter")
    print("Login form filled with the provided account and submitted.")
    print("If a CAPTCHA, SMS, or two-factor step appears, complete it in the browser.")


def _wait_for_url(page, expected: str, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if expected in page.url:
            return
        time.sleep(0.5)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Save a logged-in browser session for scraper tools."
    )
    parser.add_argument("--login-url", required=True, help="Login page to open.")
    parser.add_argument("--output", default="session_cookies.json")
    parser.add_argument(
        "--browser",
        choices=("chromium", "firefox", "webkit"),
        default="chromium",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=0.0,
        help="Extra seconds to wait after Enter before saving.",
    )
    parser.add_argument(
        "--username",
        default="",
        help="Account username or email to fill into the login form.",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Account password to fill into the login form.",
    )
    parser.add_argument(
        "--username-selector",
        default="",
        help="CSS selector for the username/email input; auto-detected when omitted.",
    )
    parser.add_argument(
        "--password-selector",
        default="",
        help="CSS selector for the password input; auto-detected when omitted.",
    )
    parser.add_argument(
        "--submit-selector",
        default="",
        help="CSS selector for the submit button or form; auto-detected when omitted.",
    )
    parser.add_argument(
        "--success-url",
        default="",
        help="URL substring that confirms login; the script waits for it after submit.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="Maximum seconds to wait for --success-url before prompting to save.",
    )
    args = parser.parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Install it with: "
            "pip install playwright && playwright install chromium"
        )
        return 2

    with sync_playwright() as playwright:
        browser = getattr(playwright, args.browser).launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(args.login_url, wait_until="domcontentloaded")
        _try_autofill(page, args)
        if args.success_url:
            _wait_for_url(page, args.success_url, args.timeout_seconds)
            print("Success URL detected:", page.url)
        if not args.username or not args.password:
            print("Complete login in the browser window (solve any CAPTCHA yourself).")
        print("Press Enter after login is complete to save the session.")
        input()
        if args.wait_seconds > 0:
            time.sleep(args.wait_seconds)
        state = context.storage_state()
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2)
        browser.close()

    print("Session saved to", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
