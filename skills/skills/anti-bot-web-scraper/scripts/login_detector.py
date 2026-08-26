"""Automatic login-form, login-state, and auth-endpoint recognition.

The browser session can use these detectors when the caller does not know
the exact selectors of a site: it scans visible inputs, password fields,
submit buttons, login links, and common login/captcha markers.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_USERNAME_HINTS = (
    "user",
    "username",
    "login",
    "email",
    "mail",
    "account",
    "phone",
    "mobile",
    "member",
    "账号",
    "用户名",
    "邮箱",
    "手机",
    "手机号",
)
_SUBMIT_HINTS = (
    "login",
    "signin",
    "sign-in",
    "sign_in",
    "log in",
    "登录",
    "登入",
    "登陆",
    "立即登录",
)
_LOGIN_URL_HINTS = re.compile(
    r"(login|logon|signin|sign-in|sign_in|account/login|passport|sso)",
    re.IGNORECASE,
)
_LOGGED_IN_MARKERS = (
    "logout",
    "sign out",
    "signout",
    "log out",
    "退出登录",
    "退出",
    "注销",
    "欢迎",
    "welcome",
    "dashboard",
    "会员中心",
    "个人中心",
    "账户中心",
)
_LOGIN_PAGE_MARKERS = (
    "login",
    "sign in",
    "signin",
    "log in",
    "登录",
    "登入",
    "登陆",
)


@dataclass
class LoginFormSpec:
    """Detected selectors for one login form."""

    method: str = "POST"
    action: str | None = None
    form_selector: str | None = None
    username_selector: str | None = None
    password_selector: str | None = None
    submit_selector: str | None = None
    captcha_selectors: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return bool(
            self.username_selector
            and self.password_selector
            and self.submit_selector
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "action": self.action,
            "form_selector": self.form_selector,
            "username_selector": self.username_selector,
            "password_selector": self.password_selector,
            "submit_selector": self.submit_selector,
            "captcha_selectors": list(self.captcha_selectors),
            "confidence": self.confidence,
            "reasons": list(self.reasons),
        }


@dataclass
class LoginDetection:
    """Combined login-page recognition result."""

    form: LoginFormSpec | None = None
    login_urls: list[str] = field(default_factory=list)
    logged_in: bool = False
    login_confidence: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "form": self.form.to_dict() if self.form else None,
            "login_urls": list(self.login_urls),
            "logged_in": self.logged_in,
            "login_confidence": self.login_confidence,
            "reasons": list(self.reasons),
        }


def _contains_hint(value: str, hints: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in hints)


def _selector_for_input(attrs: dict[str, str]) -> str | None:
    name = attrs.get("name") or ""
    input_id = attrs.get("id") or ""
    if input_id:
        return f"#{input_id}"
    if name:
        return f"input[name={name!r}]"
    return None


class _LoginHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.forms: list[dict[str, Any]] = []
        self.current_form: int | None = None
        self.anchors: list[tuple[str, str]] = []
        self._link_text: list[str] = []
        self._in_anchor = False
        self._anchor_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "form":
            self.forms.append(
                {
                    "method": (attr_map.get("method") or "POST").upper(),
                    "action": attr_map.get("action") or None,
                    "username": None,
                    "password": None,
                    "submit": None,
                    "captchas": [],
                }
            )
            self.current_form = len(self.forms) - 1
            return
        if tag == "a":
            href = attr_map.get("href") or ""
            self._anchor_href = href
            self._link_text = []
            self._in_anchor = True
            return
        if self.current_form is None and tag not in {"input", "button"}:
            return
        if tag == "input":
            input_type = (attr_map.get("type") or "text").lower()
            combined = " ".join(
                [
                    attr_map.get("name") or "",
                    attr_map.get("id") or "",
                    attr_map.get("placeholder") or "",
                    attr_map.get("autocomplete") or "",
                    attr_map.get("aria-label") or "",
                ]
            ).lower()
            selector = _selector_for_input(attr_map)
            if selector is None:
                return
            form = self.forms[self.current_form] if self.current_form is not None else None
            if input_type == "password":
                if form is not None:
                    form["password"] = selector
                return
            if input_type in {"submit", "button", "image"}:
                if form is not None and form["submit"] is None:
                    form["submit"] = selector
                return
            if _contains_hint(combined, ("captcha", "verify", "验证码", "校验码")):
                if form is not None:
                    form["captchas"].append(selector)
                return
            if (
                input_type in {"text", "email", "tel", "number"}
                and _contains_hint(combined, _USERNAME_HINTS)
                and form is not None
                and form["username"] is None
            ):
                form["username"] = selector
            return
        if tag == "button":
            button_type = (attr_map.get("type") or "submit").lower()
            selector = _selector_for_input(attr_map)
            if selector is None:
                selector = "button[type='submit'], input[type='submit']"
            form = self.forms[self.current_form] if self.current_form is not None else None
            if form is not None and form["submit"] is None and button_type in {"submit", "button"}:
                form["submit"] = selector

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._link_text.append(data)
        if self.current_form is not None and self.forms:
            form = self.forms[self.current_form]
            if form["submit"] is None and _contains_hint(data, _SUBMIT_HINTS):
                # The submit button text is handled as a fallback by the caller.
                form["submit_text"] = data.strip()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "form":
            self.current_form = None
        elif tag == "a" and self._in_anchor:
            self.anchors.append((self._anchor_href or "", "".join(self._link_text)))
            self._in_anchor = False
            self._anchor_href = None


def detect_login_form(html: str, base_url: str | None = None) -> LoginFormSpec | None:
    """Return the best login form found in a page."""
    parser = _LoginHTMLParser()
    parser.feed(html)
    candidates: list[LoginFormSpec] = []
    for index, raw in enumerate(parser.forms):
        action = raw.get("action")
        if action and base_url:
            action = urllib.parse.urljoin(base_url, action)
        form = LoginFormSpec(
            method=str(raw.get("method") or "POST"),
            action=action,
            form_selector=f"form:nth-of-type({index + 1})" if index < len(parser.forms) else None,
            username_selector=raw.get("username"),
            password_selector=raw.get("password"),
            submit_selector=raw.get("submit"),
            captcha_selectors=list(raw.get("captchas") or []),
        )
        reasons: list[str] = []
        if form.username_selector:
            reasons.append("username input")
        if form.password_selector:
            reasons.append("password input")
        if form.submit_selector:
            reasons.append("submit button")
        elif raw.get("submit_text"):
            form.submit_selector = _submit_text_selector(str(raw["submit_text"]))
            if form.submit_selector:
                reasons.append("submit text")
        if form.username_selector and form.password_selector:
            form.confidence = 0.95
        elif form.password_selector:
            form.confidence = 0.75
        form.reasons = reasons
        candidates.append(form)
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.confidence, bool(item.submit_selector)))


def _submit_text_selector(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'button:has-text("{escaped}"), input[value="{escaped}"]'


def detect_login_urls(html: str, base_url: str | None = None) -> list[str]:
    """Return normalized links that look like login/sign-in destinations."""
    parser = _LoginHTMLParser()
    parser.feed(html)
    found: list[str] = []
    for href, text in parser.anchors:
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if _LOGIN_URL_HINTS.search(href) or _contains_hint(text, _SUBMIT_HINTS):
            normalized = urllib.parse.urljoin(base_url or "", href)
            if normalized not in found:
                found.append(normalized)
    return found


def detect_login_state(
    html: str,
    page_url: str | None = None,
) -> tuple[bool, float, list[str]]:
    """Return (logged_in, confidence, reasons)."""
    text = html.lower()
    success_hits = [marker for marker in _LOGGED_IN_MARKERS if marker in text]
    form = detect_login_form(html, page_url)
    reasons: list[str] = []
    if success_hits:
        reasons.extend(success_hits[:5])
        if not form or not form.complete:
            return True, 0.9, reasons
        return True, 0.75, reasons + ["login form still present"]
    if form is not None and form.complete:
        reasons.append("login form present")
        return False, 0.8, reasons
    url_lower = (page_url or "").lower()
    if any(marker in url_lower for marker in _LOGIN_PAGE_MARKERS) and not success_hits:
        reasons.append("login-looking URL")
        return False, 0.6, reasons
    return False, 0.3, reasons


def detect_login(html: str, base_url: str | None = None) -> LoginDetection:
    """Run all login detectors and return one combined result."""
    logged_in, confidence, reasons = detect_login_state(html, base_url)
    return LoginDetection(
        form=detect_login_form(html, base_url),
        login_urls=detect_login_urls(html, base_url),
        logged_in=logged_in,
        login_confidence=confidence,
        reasons=reasons,
    )


if __name__ == "__main__":
    sample = """
    <html><body>
      <a href="/login">登录</a>
      <form action="/api/login" method="post">
        <input name="email" placeholder="邮箱">
        <input type="password" name="password">
        <button type="submit">立即登录</button>
      </form>
    </body></html>
    """
    detection = detect_login(sample, "https://example.com/")
    print(detection.to_dict())
