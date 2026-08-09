"""Browser and HTTP header fingerprint profiles for anti-bot rotation."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BrowserFingerprint:
    """One consistent browser profile."""

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    browser_kind: str = "chrome"
    platform: str = "Windows"
    languages: tuple[str, ...] = ("zh-CN", "zh", "en-US", "en")
    timezone_id: str = "Asia/Shanghai"
    viewport: tuple[int, int] = (1920, 1080)
    screen_width: int = 1920
    screen_height: int = 1080
    screen_avail_width: int = 1920
    screen_avail_height: int = 1040
    screen_avail_top: int = 0
    outer_width: int = 1920
    outer_height: int = 1080
    device_pixel_ratio: float = 1.0
    color_depth: int = 24
    max_touch_points: int = 0
    hardware_concurrency: int = 8
    device_memory: int = 8
    platform_version: str = "10.0.0"
    architecture: str = "x86"
    bitness: str = "64"
    model: str = ""
    webgl_vendor: str = "Intel Inc."
    webgl_renderer: str = (
        "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"
    )
    canvas_seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "browser_kind": self.browser_kind,
            "platform": self.platform,
            "languages": list(self.languages),
            "timezone_id": self.timezone_id,
            "viewport": list(self.viewport),
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "screen_avail_width": self.screen_avail_width,
            "screen_avail_height": self.screen_avail_height,
            "screen_avail_top": self.screen_avail_top,
            "outer_width": self.outer_width,
            "outer_height": self.outer_height,
            "device_pixel_ratio": self.device_pixel_ratio,
            "color_depth": self.color_depth,
            "max_touch_points": self.max_touch_points,
            "hardware_concurrency": self.hardware_concurrency,
            "device_memory": self.device_memory,
            "platform_version": self.platform_version,
            "architecture": self.architecture,
            "bitness": self.bitness,
            "model": self.model,
            "webgl_vendor": self.webgl_vendor,
            "webgl_renderer": self.webgl_renderer,
            "canvas_seed": self.canvas_seed,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrowserFingerprint:
        viewport = tuple(data.get("viewport") or cls().viewport)
        width = int(data.get("screen_width") or (viewport[0] if viewport else 1920))
        height = int(data.get("screen_height") or (viewport[1] if viewport else 1080))
        return cls(
            user_agent=str(data.get("user_agent") or cls().user_agent),
            browser_kind=str(data.get("browser_kind") or "chrome"),
            platform=str(data.get("platform") or cls().platform),
            languages=tuple(data.get("languages") or cls().languages),
            timezone_id=str(data.get("timezone_id") or cls().timezone_id),
            viewport=viewport,
            screen_width=width,
            screen_height=height,
            screen_avail_width=int(data.get("screen_avail_width") or width),
            screen_avail_height=int(data.get("screen_avail_height") or max(0, height - 40)),
            screen_avail_top=int(data.get("screen_avail_top") or 0),
            outer_width=int(data.get("outer_width") or width),
            outer_height=int(data.get("outer_height") or height),
            device_pixel_ratio=float(data.get("device_pixel_ratio") or 1.0),
            color_depth=int(data.get("color_depth") or 24),
            max_touch_points=int(data.get("max_touch_points") or 0),
            hardware_concurrency=int(data.get("hardware_concurrency") or 8),
            device_memory=int(data.get("device_memory") or 8),
            platform_version=str(data.get("platform_version") or "10.0.0"),
            architecture=str(data.get("architecture") or "x86"),
            bitness=str(data.get("bitness") or "64"),
            model=str(data.get("model") or ""),
            webgl_vendor=str(data.get("webgl_vendor") or cls().webgl_vendor),
            webgl_renderer=str(data.get("webgl_renderer") or cls().webgl_renderer),
            canvas_seed=int(data.get("canvas_seed") or 0),
        )

    @classmethod
    def generate(
        cls,
        seed: int | None = None,
        browser: str = "chrome",
    ) -> BrowserFingerprint:
        rng = random.Random(seed)
        width = rng.choice((1366, 1440, 1536, 1920))
        height = rng.choice((768, 900, 1024, 1080))
        family = str(browser or "chrome").lower()
        if family in {"firefox", "ff"}:
            version = rng.choice((124, 127, 133, 136))
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:"
                f"{version}.0) Gecko/20100101 Firefox/{version}.0"
            )
            webgl_renderer = (
                "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 "
                "vs_5_0 ps_5_0, D3D11)"
            )
            return cls(
                user_agent=user_agent,
                browser_kind="firefox",
                platform="Windows",
                languages=("zh-CN", "zh", "en-US", "en"),
                timezone_id="Asia/Shanghai",
                viewport=(width, height),
                screen_width=width,
                screen_height=height,
                screen_avail_width=width,
                screen_avail_height=max(0, height - 40),
                outer_width=width,
                outer_height=height,
                hardware_concurrency=rng.choice((4, 8, 12, 16)),
                device_memory=rng.choice((4, 8)),
                webgl_renderer=webgl_renderer,
                canvas_seed=rng.randrange(1 << 30),
            )
        if family in {"safari", "webkit"}:
            version = rng.choice(("16.5", "17.0", "17.4", "18.0"))
            user_agent = (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/{version} Safari/605.1.15"
            )
            return cls(
                user_agent=user_agent,
                browser_kind="safari",
                platform="macOS",
                languages=("zh-CN", "zh", "en-US", "en"),
                timezone_id="Asia/Shanghai",
                viewport=(width, height),
                screen_width=width,
                screen_height=height,
                screen_avail_width=width,
                screen_avail_height=max(0, height - 40),
                outer_width=width,
                outer_height=height,
                hardware_concurrency=rng.choice((4, 8, 12, 16)),
                device_memory=rng.choice((4, 8)),
                platform_version="15.0.0",
                architecture="x86",
                bitness="64",
                webgl_vendor="Apple Inc.",
                webgl_renderer="Apple GPU",
                canvas_seed=rng.randrange(1 << 30),
            )
        if family in {"edge", "msedge"}:
            version = rng.choice((122, 124, 126, 131))
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36 "
                f"Edg/{version}.0.0.0"
            )
            return cls(
                user_agent=user_agent,
                browser_kind="edge",
                platform="Windows",
                languages=("zh-CN", "zh", "en-US", "en"),
                timezone_id="Asia/Shanghai",
                viewport=(width, height),
                screen_width=width,
                screen_height=height,
                screen_avail_width=width,
                screen_avail_height=max(0, height - 40),
                outer_width=width,
                outer_height=height,
                hardware_concurrency=rng.choice((4, 8, 12, 16)),
                device_memory=rng.choice((4, 8)),
                webgl_renderer=(
                    "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 "
                    "vs_5_0 ps_5_0, D3D11)"
                ),
                canvas_seed=rng.randrange(1 << 30),
            )
        version = rng.choice((122, 124, 126, 131))
        return cls(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"
            ),
            browser_kind="chrome",
            platform="Windows",
            languages=("zh-CN", "zh", "en-US", "en"),
            timezone_id="Asia/Shanghai",
            viewport=(width, height),
            screen_width=width,
            screen_height=height,
            screen_avail_width=width,
            screen_avail_height=max(0, height - 40),
            outer_width=width,
            outer_height=height,
            hardware_concurrency=rng.choice((4, 8, 12, 16)),
            device_memory=rng.choice((4, 8)),
            webgl_renderer=(
                "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 "
                "vs_5_0 ps_5_0, D3D11)"
            ),
            canvas_seed=rng.randrange(1 << 30),
        )


@dataclass
class HeaderFingerprint:
    """HTTP header profile that matches a real browser class."""

    name: str
    headers: dict[str, str] = field(default_factory=dict)
    order: tuple[str, ...] = ()

    @classmethod
    def chrome(cls, version: int = 126) -> HeaderFingerprint:
        sec_ch_ua = (
            f'"Chromium";v="{version}", "Google Chrome";v="{version}", '
            f'"Not=A?Brand";v="99"'
        )
        return cls(
            name="chrome",
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8,"
                    "application/signed-exchange;v=b3;q=0.7"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Sec-CH-UA": sec_ch_ua,
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            order=(
                "sec-ch-ua",
                "sec-ch-ua-mobile",
                "sec-ch-ua-platform",
                "upgrade-insecure-requests",
                "user-agent",
                "accept",
                "sec-fetch-site",
                "sec-fetch-mode",
                "sec-fetch-user",
                "sec-fetch-dest",
                "accept-encoding",
                "accept-language",
            ),
        )

    @classmethod
    def firefox(cls, version: int = 127) -> HeaderFingerprint:
        return cls(
            name="firefox",
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            },
            order=(
                "user-agent",
                "accept",
                "accept-language",
                "accept-encoding",
                "upgrade-insecure-requests",
                "sec-fetch-dest",
                "sec-fetch-mode",
                "sec-fetch-site",
                "sec-fetch-user",
            ),
        )

    @classmethod
    def safari(cls) -> HeaderFingerprint:
        return cls(
            name="safari",
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
            },
            order=(
                "user-agent",
                "accept",
                "accept-language",
                "accept-encoding",
                "sec-fetch-dest",
                "sec-fetch-mode",
                "sec-fetch-site",
            ),
        )

    @classmethod
    def edge(cls, version: int = 126) -> HeaderFingerprint:
        chrome = cls.chrome(version=version)
        sec_ch_ua = (
            f'"Chromium";v="{version}", "Microsoft Edge";v="{version}", '
            f'"Not=A?Brand";v="99"'
        )
        return cls(
            name="edge",
            headers={
                **chrome.headers,
                "Sec-CH-UA": sec_ch_ua,
                "Sec-CH-UA-Platform": '"Windows"',
            },
            order=chrome.order,
        )

    @classmethod
    def for_browser(cls, name: str) -> HeaderFingerprint:
        key = str(name or "chrome").lower()
        if key in {"firefox", "ff"}:
            return cls.firefox()
        if key in {"safari", "webkit"}:
            return cls.safari()
        if key in {"edge", "msedge"}:
            return cls.edge()
        return cls.chrome()

    def apply(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        merged = dict(headers or {})
        for key, value in self.headers.items():
            merged.setdefault(key, value)
        return merged


class FingerprintBank:
    """Rotate stable browser profiles for one task or session."""

    def __init__(
        self,
        profiles: list[BrowserFingerprint] | None = None,
        *,
        count: int = 4,
        seed: int | None = None,
        browser: str = "chrome",
    ) -> None:
        self.profiles = profiles or [
            BrowserFingerprint.generate(
                seed=seed + index if seed is not None else None,
                browser=browser,
            )
            for index in range(count)
        ]
        self._index = 0

    def next(self) -> BrowserFingerprint:
        profile = self.profiles[self._index % len(self.profiles)]
        self._index += 1
        return profile


if __name__ == "__main__":
    print(HeaderFingerprint.chrome().headers)
