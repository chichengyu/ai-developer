"""Vendor-specific challenge solving helpers.

Different bot-management vendors expose different cookies, iframes, and
token fields. This module validates the cookie that actually matters for a
vendor (`_abck`, `datadome`, `aws-waf-token`, ...), waits for it inside the
browser, and injects provider tokens into the vendor's response fields.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterable
from contextlib import suppress
from typing import Any

VENDOR_COOKIE_NAMES: dict[str, tuple[str, ...]] = {
    "cloudflare": ("cf_clearance",),
    "datadome": ("datadome",),
    "akamai": ("_abck", "ak_bmsc", "bm_sz"),
    "perimeterx": ("_px3", "_pxhd", "_px"),
    "shape": ("__shape", "__sl"),
    "kasada": ("kasad", "kpsdk_ct"),
    "imperva": ("incap_ses_", "visid_incap_", "nlbi_"),
    "aws_waf": ("aws-waf-token",),
    "f5": ("TS", "F5"),
    "alibaba": ("acw_tc", "aliyungf_tc"),
    "radware": ("radware", "rdwr"),
    "reblaze": ("rbzid",),
    "stackpath": ("stackpath",),
    "tencent": ("t_security", "t_cookie"),
}

_TOKEN_SELECTORS: dict[str, tuple[str, ...]] = {
    "aws_waf": (
        "textarea#aws-waf-token",
        "textarea[name='aws-waf-token']",
        "input[name='aws-waf-token']",
    ),
    "perimeterx": (
        "textarea[name='px-captcha-response']",
        "input[name='px-captcha-response']",
    ),
    "datadome": (
        "input[name='datadome']",
        "textarea[name='datadome']",
        "textarea[name='dd-token']",
    ),
    "arkose": (
        "input[name='fc-token']",
        "textarea[name='fc-token']",
        "textarea[name='arkose-token']",
    ),
    "shape": (
        "input[name='shape-token']",
        "textarea[name='shape-token']",
    ),
    "kasada": (
        "input[name='kpsdk-token']",
        "textarea[name='kpsdk-token']",
    ),
}

_SLIDER_IFRAME_MARKERS = {
    "datadome": ("geo.captcha-delivery.com", "captcha-delivery.com"),
    "geetest": ("geetest.com",),
    "yidun": ("cstaticdun.126.net",),
}

_PUBLIC_KEY_ATTR_RE = re.compile(
    r"data-(?:sitekey|pkey|public-key|data-sitekey)=['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_PUBLIC_KEY_SCRIPT_RE = re.compile(
    r"(?:sitekey|public_key|pkey)\s*[:=]\s*['\"]([^'\"]{8,})['\"]",
    re.IGNORECASE,
)

_PROVIDER_METHODS: dict[str, str] = {
    "arkose": "solve_funcaptcha",
    "datadome": "solve_datadome",
    "aws_waf": "solve_awswaf",
    "perimeterx": "solve_perimeterx",
}


def _cookie_name(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("name") or "")
    return str(getattr(item, "name", "") or "")


def _cookie_value(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("value") or "")
    return str(getattr(item, "value", "") or "")


def _cookie_expires(item: Any) -> float | None:
    raw = item.get("expires") if isinstance(item, dict) else getattr(item, "expires", None)
    return float(raw) if isinstance(raw, int | float) and raw > 0 else None


def vendor_cookie_matches(item: Any, vendor: str) -> bool:
    name = _cookie_name(item).lower()
    names = VENDOR_COOKIE_NAMES.get(str(vendor).lower(), ())
    return any(name == str(candidate).lower() or name.startswith(str(candidate).lower()) for candidate in names)


def vendor_cookie_valid(item: Any, vendor: str) -> bool:
    """Return True only when the vendor cookie is present and not expired."""
    value = _cookie_value(item)
    if not value:
        return False
    expires = _cookie_expires(item)
    if expires is not None and expires <= time.time():
        return False
    vendor = str(vendor).lower()
    name = _cookie_name(item).lower()
    if vendor == "akamai":
        if name == "_abck":
            return len(value) >= 20 and not value.startswith("-1~")
        if name == "ak_bmsc":
            return len(value) >= 10
    if vendor == "datadome":
        return len(value) >= 5 and value.lower() not in {"x", "false", "true"}
    if vendor == "aws_waf":
        return len(value) >= 10
    return True


def has_valid_vendor_cookie(cookies: Iterable[Any] | None, vendor: str) -> bool:
    return any(
        vendor_cookie_matches(item, vendor) and vendor_cookie_valid(item, vendor)
        for item in cookies or []
    )


def wait_for_vendor_cookie(
    context: Any,
    vendor: str,
    *,
    timeout: float = 30000,
    poll_interval: float = 0.5,
) -> list[dict[str, Any]] | None:
    deadline = time.monotonic() + timeout / 1000.0
    while time.monotonic() < deadline:
        try:
            cookies = list(context.cookies() or [])
        except Exception:
            cookies = []
        if has_valid_vendor_cookie(cookies, vendor):
            return cookies
        time.sleep(poll_interval)
    return None


def inject_captcha_token(
    page: Any,
    vendor: str,
    token: str,
    *,
    callback: str | None = None,
) -> bool:
    """Inject a provider token into vendor-specific response fields."""
    selectors = _TOKEN_SELECTORS.get(str(vendor).lower(), ())
    if not selectors:
        return False
    script = """
    (args) => {
      let found = false;
      const seen = new WeakSet();
      function visit(root) {
        if (!root || seen.has(root)) return;
        seen.add(root);
        for (const selector of args.selectors) {
          try {
            const nodes = root.querySelectorAll ? root.querySelectorAll(selector) : [];
            for (const el of nodes) {
              el.value = args.token;
              el.dispatchEvent(new Event("input", {bubbles: true}));
              el.dispatchEvent(new Event("change", {bubbles: true}));
              found = true;
            }
          } catch (e) {}
        }
        if (root.shadowRoot) visit(root.shadowRoot);
        if (root.children) {
          for (const child of root.children) visit(child);
        }
      }
      visit(document);
      window.__vendorToken = args.token;
      return found || true;
    }
    """
    try:
        if not page.evaluate(script, {"selectors": list(selectors), "token": token}):
            return False
    except Exception:
        return False
    if callback:
        expression = "window"
        for part in str(callback).split("."):
            expression += f"[{json.dumps(part)}]"
        with suppress(Exception):
            page.evaluate(
                f"({expression}) && typeof ({expression}) === 'function' "
                f"&& ({expression})({json.dumps(token)})"
            )
    return True


def extract_vendor_public_key(html: str, vendor: str) -> str | None:
    match = _PUBLIC_KEY_ATTR_RE.search(html or "")
    if match:
        return match.group(1)
    match = _PUBLIC_KEY_SCRIPT_RE.search(html or "")
    return match.group(1) if match else None


def solve_vendor_with_provider(
    solver: Any,
    vendor: str,
    page_url: str,
    *,
    public_key: str | None = None,
) -> str | None:
    """Best-effort provider solve for vendors with a supported adapter method."""
    method_name = _PROVIDER_METHODS.get(str(vendor).lower())
    method = getattr(solver, method_name, None) if method_name else None
    if method is None:
        return None
    try:
        if method_name == "solve_funcaptcha" and public_key:
            result = method(public_key, page_url)
        else:
            result = method(page_url)
    except Exception:
        return None
    token = str(getattr(result, "answer", "") or "")
    return token or None


def solve_vendor_slider(page: Any, vendor: str = "datadome") -> bool:
    """Solve a slider inside a vendor challenge iframe when present."""
    markers = _SLIDER_IFRAME_MARKERS.get(str(vendor).lower(), ())
    try:
        frames = list(getattr(page, "frames", []) or [])
    except Exception:
        frames = []
    for frame in frames:
        frame_url = str(getattr(frame, "url", "") or "").lower()
        if markers and not any(marker in frame_url for marker in markers):
            continue
        try:
            html = str(frame.content() or "")
        except Exception:
            continue
        from slider_solver import SliderCaptchaSolver, detect_slider_challenges

        challenges = detect_slider_challenges(html)
        if challenges:
            result = SliderCaptchaSolver().solve(frame, challenges[0])
            if result.success:
                return True
        from challenge_click import click_shadow_dom

        if click_shadow_dom(frame):
            return True
    return False


if __name__ == "__main__":
    print("vendor_solver: import vendor cookie validation and token injection helpers.")
