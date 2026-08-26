"""Shared, humanized challenge-click helpers for Cloudflare/Turnstile pages."""

from __future__ import annotations

import random
import time
from contextlib import suppress
from typing import Any

FRAME_MARKER = "challenges.cloudflare.com"
CHALLENGE_FRAME_MARKERS = (
    "challenges.cloudflare.com",
    "captcha-delivery.com",
    "datadome",
    "perimeterx",
    "px-captcha",
    "akamai",
    "awswaf",
    "funcaptcha",
    "arkoselabs",
    "hcaptcha",
    "recaptcha",
    "turnstile",
)

CHALLENGE_SELECTORS = (
    "input[type='checkbox']",
    "button[id*='challenge']",
    "button[class*='challenge']",
    "button[aria-label*='challenge']",
    "button[aria-label*='captcha']",
    "button[class*='captcha']",
    "[data-sitekey] button",
    "[class*='challenge'] button",
    "[class*='captcha'] button",
)

VENDOR_IFRAME_MARKERS: dict[str, tuple[str, ...]] = {
    "datadome": ("geo.captcha-delivery.com", "captcha-delivery.com"),
    "akamai": ("akamai", "px-captcha", "sensor"),
    "aws_waf": ("captcha.awswaf.com",),
    "perimeterx": ("px-captcha", "perimeterx"),
    "arkose": ("arkoselabs", "funcaptcha"),
    "cloudflare": ("challenges.cloudflare.com",),
}

_SHADOW_CLICK_JS = r"""
() => {
  const roots = [
    document,
    document.querySelector("#challenge-stage"),
    document.querySelector("#turnstile-wrapper"),
    document.querySelector("challenge-frame")
  ].filter(Boolean);
  const selectors = [
    "input[type='checkbox']",
    ".ctp-checkbox-label",
    ".ctp-checkbox-container",
    "button[id*='challenge']",
    "#challenge-stage button",
    "#cf-chl-stage button"
  ];
  function visible(el) {
    if (!el || el.disabled) return false;
    const rect = el.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
    const style = window.getComputedStyle ? window.getComputedStyle(el) : null;
    return !style || (style.visibility !== "hidden" && style.display !== "none");
  }
  function visit(root) {
    if (!root) return false;
    if (root.querySelectorAll) {
      for (const selector of selectors) {
        const nodes = root.querySelectorAll(selector);
        for (const el of nodes) {
          if (visible(el)) {
            el.click();
            return true;
          }
        }
      }
    }
    if (root.shadowRoot && visit(root.shadowRoot)) return true;
    if (root.children) {
      for (const child of root.children) {
        if (visit(child)) return true;
      }
    }
    return false;
  }
  return roots.some(visit);
}
"""


def shadow_click_script() -> str:
    return _SHADOW_CLICK_JS


def click_shadow_dom(page_or_frame: Any) -> bool:
    try:
        return bool(page_or_frame.evaluate(_SHADOW_CLICK_JS))
    except Exception:
        return False


def human_click(element: Any, page_or_frame: Any | None = None) -> bool:
    """Click an element with human-like mouse movement when possible."""
    if element is None:
        return False
    with suppress(Exception):
        element.scroll_into_view_if_needed(timeout=1200)
    box = None
    with suppress(Exception):
        box = element.bounding_box()
    mouse = getattr(page_or_frame, "mouse", None)
    if mouse is None and page_or_frame is not None:
        with suppress(Exception):
            mouse = getattr(page_or_frame, "page", None).mouse
    if mouse is not None and isinstance(box, dict):
        try:
            x0 = float(box.get("x") or 0)
            y0 = float(box.get("y") or 0)
            width = float(box.get("width") or 0)
            height = float(box.get("height") or 0)
            cx = x0 + width * random.uniform(0.35, 0.65)
            cy = y0 + height * random.uniform(0.35, 0.65)
            for step in range(1, 4):
                tx = x0 + (cx - x0) * (step / 3.0) + random.uniform(-1.0, 1.0)
                ty = y0 + (cy - y0) * (step / 3.0) + random.uniform(-1.0, 1.0)
                mouse.move(tx, ty)
                time.sleep(random.uniform(0.01, 0.04))
            time.sleep(random.uniform(0.05, 0.15))
            mouse.click(cx, cy)
            return True
        except Exception:
            pass
    with suppress(Exception):
        element.click(timeout=1500)
        return True
    return False


def click_managed_challenge(page: Any) -> bool:
    """Try main-document selectors, Cloudflare iframes, then shadow DOM."""
    selectors = (
        "input[type='checkbox']",
        "#challenge-stage input[type='checkbox']",
        "#turnstile-wrapper input[type='checkbox']",
        "#challenge-stage button",
        ".ctp-checkbox-container",
        ".ctp-checkbox-label",
        "button[id*='challenge']",
        "#cf-chl-stage button",
    )
    for selector in selectors:
        try:
            element = page.query_selector(selector)
        except Exception:
            element = None
        if element is not None and human_click(element, page):
            return True
    try:
        frames = list(getattr(page, "frames", []) or [])
    except Exception:
        frames = []
    for frame in frames:
        if FRAME_MARKER not in str(getattr(frame, "url", "") or ""):
            continue
        for selector in ("input[type='checkbox']", "#challenge-stage button", "button"):
            try:
                element = frame.query_selector(selector)
            except Exception:
                element = None
            if element is not None and human_click(element, frame):
                return True
        if click_shadow_dom(frame):
            return True
    return click_shadow_dom(page)


def click_any_challenge(page: Any, vendor: str | None = None) -> bool:
    """Click a visible challenge widget, optionally narrowed to one vendor."""
    if vendor and click_vendor_challenge(page, vendor):
        return True
    for selector in CHALLENGE_SELECTORS:
        try:
            element = page.query_selector(selector)
        except Exception:
            element = None
        if element is not None and human_click(element, page):
            return True
    try:
        frames = list(getattr(page, "frames", []) or [])
    except Exception:
        frames = []
    for frame in frames:
        frame_url = str(getattr(frame, "url", "") or "").lower()
        if not any(marker in frame_url for marker in CHALLENGE_FRAME_MARKERS):
            continue
        for selector in CHALLENGE_SELECTORS:
            try:
                element = frame.query_selector(selector)
            except Exception:
                element = None
            if element is not None and human_click(element, frame):
                return True
        if click_shadow_dom(frame):
            return True
    return click_shadow_dom(page)


def click_vendor_challenge(page: Any, vendor: str) -> bool:
    """Click page-level and vendor-iframe challenge controls for one vendor."""
    for selector in CHALLENGE_SELECTORS:
        try:
            element = page.query_selector(selector)
        except Exception:
            element = None
        if element is not None and human_click(element, page):
            return True
    markers = VENDOR_IFRAME_MARKERS.get(str(vendor).lower(), ())
    try:
        frames = list(getattr(page, "frames", []) or [])
    except Exception:
        frames = []
    for frame in frames:
        frame_url = str(getattr(frame, "url", "") or "").lower()
        if markers and not any(marker in frame_url for marker in markers):
            continue
        for selector in ("input[type='checkbox']", "#challenge-stage button", "button"):
            try:
                element = frame.query_selector(selector)
            except Exception:
                element = None
            if element is not None and human_click(element, frame):
                return True
        if click_shadow_dom(frame):
            return True
    return click_shadow_dom(page)
