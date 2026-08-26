"""Slider CAPTCHA detection and human-like browser solving.

Slider challenges are solved in the real browser by dragging the handle
across the track with easing and jitter, then checking for a success state
or hidden answer field. It is a local browser action; no third-party
service is required.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_SLIDER_HINTS = (
    "geetest_slider",
    "geetest_slide",
    "nc_iconfont",
    "btn_slide",
    "yidun_slider",
    "captcha-slider",
    "verify-slider",
    "slide-verify",
    "secsdk-captcha-drag-icon",
    "滑块",
)
_HANDLE_HINTS = (
    "geetest_slider_button",
    "yidun_slider",
    "nc_iconfont",
    "btn_slide",
    "secsdk-captcha-drag-icon",
)
_TRACK_HINTS = (
    "geetest_slider_bg",
    "yidun_bgimg",
    "captcha-slider-track",
    "slide-verify-track",
)


class _SliderParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        self.elements.append((tag.lower(), attr_map))


@dataclass
class SliderChallenge:
    selector: str = "div[id*=slide], div[class*=slider]"
    handle_selector: str | None = None
    track_selector: str | None = None
    success_selector: str | None = None
    max_attempts: int = 3
    distance: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selector": self.selector,
            "handle_selector": self.handle_selector,
            "track_selector": self.track_selector,
            "success_selector": self.success_selector,
            "max_attempts": self.max_attempts,
            "distance": self.distance,
        }


@dataclass
class SliderSolveResult:
    success: bool = False
    attempts: int = 0
    strategy: str = "none"
    error: str | None = None
    distance: int | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "attempts": self.attempts,
            "strategy": self.strategy,
            "error": self.error,
            "distance": self.distance,
            "details": self.details,
        }


def detect_slider_challenges(html: str) -> list[SliderChallenge]:
    """Detect slider CAPTCHA containers from raw HTML."""
    parser = _SliderParser()
    parser.feed(html)
    found: list[SliderChallenge] = []
    seen: set[str] = set()
    for _tag, attrs in parser.elements:
        classes = attrs.get("class", "").lower()
        element_id = attrs.get("id", "").lower()
        combined = f"{classes} {element_id}"
        if not any(hint in combined for hint in _SLIDER_HINTS):
            continue
        selector = (
            f"#{attrs['id']}"
            if attrs.get("id")
            else f".{classes.split()[0]}"
            if classes
            else "div[id*=slide], div[class*=slider]"
        )
        if selector in seen:
            continue
        seen.add(selector)
        found.append(
            SliderChallenge(
                selector=selector,
                handle_selector=_first_matching_selector(attrs, _HANDLE_HINTS),
                track_selector=_first_matching_selector(attrs, _TRACK_HINTS),
            )
        )
    return found


def _first_matching_selector(attrs: dict[str, str], hints: tuple[str, ...]) -> str | None:
    combined = f"{attrs.get('class', '')} {attrs.get('id', '')}".lower()
    for hint in hints:
        if hint in combined:
            if attrs.get("id"):
                return f"#{attrs['id']}"
            if attrs.get("class"):
                return f".{attrs['class'].split()[0]}"
    return None


class SliderCaptchaSolver:
    """Drag slider handles with human-like mouse movement."""

    def __init__(
        self,
        *,
        duration: float = 0.9,
        jitter: float = 0.2,
        max_attempts: int = 3,
        seed: int | None = None,
    ) -> None:
        self.duration = max(0.1, float(duration))
        self.jitter = max(0.0, float(jitter))
        self.max_attempts = max(1, int(max_attempts))
        self._rng = random.Random(seed)

    def solve(
        self,
        page: Any,
        challenge: SliderChallenge | None = None,
    ) -> SliderSolveResult:
        challenge = challenge or SliderChallenge()
        distance = challenge.distance
        last_error: str | None = None
        for attempt in range(challenge.max_attempts):
            handle = self._locate_handle(page, challenge)
            if handle is None:
                last_error = "slider handle not found"
                continue
            if distance is None:
                distance = self._estimate_distance(page, challenge, handle)
            if distance is None:
                distance = 260
            box = self._box(page, handle)
            if box is None:
                last_error = "slider handle has no bounding box"
                continue
            start_x = box["x"] + box["width"] / 2
            start_y = box["y"] + box["height"] / 2
            self._drag(page, start_x, start_y, start_x + distance, start_y)
            if self._is_solved(page, challenge):
                return SliderSolveResult(
                    success=True,
                    attempts=attempt + 1,
                    strategy="human_drag",
                    distance=int(distance),
                )
            last_error = "slider did not reach success state"
            time.sleep(0.6)
        return SliderSolveResult(
            success=False,
            attempts=challenge.max_attempts,
            strategy="human_drag",
            error=last_error,
            distance=int(distance) if distance is not None else None,
        )

    def _locate_handle(self, page: Any, challenge: SliderChallenge) -> Any | None:
        selectors = [
            challenge.handle_selector,
            f"{challenge.selector} button",
            f"{challenge.selector} [class*=button]",
            "div.geetest_slider_button",
            "div.yidun_slider",
            "span.btn_slide",
            "div.secsdk-captcha-drag-icon",
        ]
        for selector in selectors:
            if not selector:
                continue
            try:
                element = page.query_selector(selector)
                if element is not None:
                    return element
            except Exception:
                pass
        return None

    def _estimate_distance(
        self,
        page: Any,
        challenge: SliderChallenge,
        handle: Any,
    ) -> int | None:
        script = """
        (selector) => {
          const el = document.querySelector(selector);
          if (!el) return null;
          const rect = el.getBoundingClientRect();
          return Math.round(rect.width);
        }
        """
        try:
            track_selector = (
                challenge.track_selector
                or f"{challenge.selector} [class*=bg]"
                or f"{challenge.selector} [class*=track]"
            )
            track_width = int(page.evaluate(script, track_selector) or 0)
            handle_box = self._box(page, handle)
            if handle_box and track_width:
                return max(10, int(track_width - handle_box["width"]))
        except Exception:
            pass
        return None

    def _box(self, page: Any, element: Any) -> dict[str, float] | None:
        box = getattr(element, "bounding_box", None)
        if box is None:
            return None
        try:
            value = box()
            return value if isinstance(value, dict) else None
        except Exception:
            return None

    def _drag(
        self,
        page: Any,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
    ) -> None:
        try:
            page.mouse.move(start_x, start_y)
            page.mouse.down()
            steps = max(8, min(28, int(abs(end_x - start_x) / 12)))
            for step in range(1, steps + 1):
                progress = step / steps
                eased = 1 - pow(1 - progress, 3)
                x = start_x + (end_x - start_x) * eased
                y = start_y + (end_y - start_y) * eased
                x += self._rng.uniform(-self.jitter, self.jitter)
                y += self._rng.uniform(-self.jitter, self.jitter)
                page.mouse.move(x, y)
                time.sleep(self.duration / steps)
            page.mouse.move(end_x, end_y)
            page.mouse.up()
        except Exception as exc:
            raise RuntimeError(f"slider drag failed: {exc}") from exc

    def _is_solved(self, page: Any, challenge: SliderChallenge) -> bool:
        selectors = [
            challenge.success_selector,
            "div.geetest_success",
            ".geetest_success_radar_tip",
            ".yidun--success",
            ".captcha-slider-success",
            "input[name*=geetest_validate][value]",
            "textarea[name*=geetest_validate]",
        ]
        for selector in selectors:
            if not selector:
                continue
            try:
                if page.query_selector(selector) is not None:
                    return True
            except Exception:
                pass
        try:
            value = page.evaluate(
                """
                () => {
                  const el = document.querySelector(
                    "input[name*=geetest_validate], textarea[name*=geetest_validate]"
                  );
                  return el && el.value ? el.value : "";
                }
                """
            )
            return bool(value)
        except Exception:
            return False


if __name__ == "__main__":
    print("slider_solver: import SliderCaptchaSolver for human-like slider drags.")
