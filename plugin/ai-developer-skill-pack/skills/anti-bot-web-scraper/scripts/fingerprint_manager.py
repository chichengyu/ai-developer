"""Unified fingerprint manager: browser profile + headers + stealth JS."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from browser_flags import BrowserLaunchProfile
from fingerprint_bank import BrowserFingerprint, HeaderFingerprint
from fingerprint_binding import FingerprintBinding, resolve_binding
from stealth_patch_bank import compose_patches

_TZ_COORDS: dict[str, tuple[float, float]] = {
    "asia/shanghai": (31.2304, 121.4737),
    "asia/tokyo": (35.6762, 139.6503),
    "america/new_york": (40.7128, -74.006),
    "america/los_angeles": (34.0522, -118.2437),
    "europe/london": (51.5074, -0.1278),
    "europe/berlin": (52.52, 13.405),
    "europe/paris": (48.8566, 2.3522),
    "australia/sydney": (-33.8688, 151.2093),
    "asia/singapore": (1.3521, 103.8198),
    "america/sao_paulo": (-23.5505, -46.6333),
}

_TZ_OFFSET_FALLBACK: dict[str, int] = {
    "asia/shanghai": -480,
    "asia/tokyo": -540,
    "america/new_york": 240,
    "america/los_angeles": 420,
    "europe/london": 60,
    "europe/berlin": 120,
    "europe/paris": 120,
    "australia/sydney": 600,
    "asia/singapore": -480,
    "america/sao_paulo": -180,
}


def timezone_coordinates(timezone_id: str) -> tuple[float, float]:
    return _TZ_COORDS.get(str(timezone_id).strip().lower(), (31.2304, 121.4737))


def timezone_offset_minutes(timezone_id: str) -> int:
    """Return current UTC offset for a timezone, preferring the real IANA value."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        offset = datetime.now(ZoneInfo(str(timezone_id))).utcoffset()
        if offset is not None:
            return -int(offset.total_seconds() // 60)
    except Exception:
        pass
    return _TZ_OFFSET_FALLBACK.get(str(timezone_id).strip().lower(), -480)


def _parse_user_agent(user_agent: str) -> dict[str, Any]:
    ua = str(user_agent or "")
    lower = ua.lower()
    result: dict[str, Any] = {
        "browser_kind": "chrome",
        "version": "126",
        "full_version": "126.0.0.0",
        "brands": [
            {"brand": "Chromium", "version": "126"},
            {"brand": "Google Chrome", "version": "126"},
            {"brand": "Not=A?Brand", "version": "99"},
        ],
    }
    if "edg/" in lower:
        result["browser_kind"] = "edge"
        match = re.search(r"Edg/(\d+)", ua, re.IGNORECASE)
        version = match.group(1) if match else "126"
        result.update(
            version=version,
            full_version=f"{version}.0.0.0",
            brands=[
                {"brand": "Chromium", "version": version},
                {"brand": "Microsoft Edge", "version": version},
                {"brand": "Not=A?Brand", "version": "99"},
            ],
        )
    elif "firefox/" in lower:
        result["browser_kind"] = "firefox"
        match = re.search(r"Firefox/(\d+(?:\.\d+)?)", ua, re.IGNORECASE)
        version = match.group(1) if match else "127.0"
        result.update(version=version.split(".")[0], full_version=version)
    elif "version/" in lower and "safari/" in lower:
        result["browser_kind"] = "safari"
        match = re.search(r"Version/(\d+(?:\.\d+)?)", ua, re.IGNORECASE)
        version = match.group(1) if match else "17.0"
        result.update(version=version, full_version=version)
    else:
        match = re.search(r"Chrome/(\d+)", ua, re.IGNORECASE)
        if match:
            version = match.group(1)
            result.update(
                version=version,
                full_version=f"{version}.0.0.0",
                brands=[
                    {"brand": "Chromium", "version": version},
                    {"brand": "Google Chrome", "version": version},
                    {"brand": "Not=A?Brand", "version": "99"},
                ],
            )
    return result


def fingerprint_patch_values(browser: BrowserFingerprint) -> dict[str, Any]:
    """Build one coherent stealth value map from a browser fingerprint."""
    ua_info = _parse_user_agent(browser.user_agent)
    kind = str(browser.browser_kind or ua_info["browser_kind"]).lower()
    if kind not in {"chrome", "edge", "firefox", "safari"}:
        kind = str(ua_info["browser_kind"]).lower()
    is_chromium = kind in {"chrome", "edge"}
    is_windows = str(browser.platform).lower().startswith("win")
    is_macos = "mac" in str(browser.platform).lower() or kind == "safari"
    viewport = tuple(browser.viewport or (1920, 1080))
    width = int(browser.screen_width or viewport[0])
    height = int(browser.screen_height or viewport[1])
    avail_width = int(browser.screen_avail_width or width)
    avail_height = int(browser.screen_avail_height or max(0, height - 40))
    outer_width = int(browser.outer_width or width)
    outer_height = int(browser.outer_height or height)
    full_version = str(ua_info["full_version"])
    if kind == "firefox" and "." not in full_version:
        full_version = f"{full_version}.0"
    brands = ua_info.get("brands") if is_chromium else []
    full_version_list: list[dict[str, str]] = []
    if is_chromium:
        full_version_list = [
            {"brand": item["brand"], "version": f"{item['version']}.0.0.0"}
            for item in brands
            if item["brand"] != "Not=A?Brand"
        ]
        full_version_list.append({"brand": "Not=A?Brand", "version": "99.0.0.0"})
    if is_windows:
        platform = "Win32"
        oscpu = "Windows NT 10.0; Win64; x64"
        ua_platform = "Windows"
        platform_version = str(browser.platform_version or "10.0.0")
    elif is_macos:
        platform = "MacIntel"
        oscpu = "Intel Mac OS X 10_15_7"
        ua_platform = "macOS"
        platform_version = str(browser.platform_version or "15.0.0")
    else:
        platform = "Linux x86_64"
        oscpu = ""
        ua_platform = "Linux"
        platform_version = str(browser.platform_version or "10.0.0")
    if kind in {"chrome", "edge"}:
        vendor = "Google Inc."
        product_sub = "20030107"
    elif kind == "safari":
        vendor = "Apple Computer, Inc."
        product_sub = "20030107"
    else:
        vendor = ""
        product_sub = "20100101"
    language = browser.languages[0] if browser.languages else "zh-CN"
    voices = [
        {"name": "Microsoft Huihui Desktop", "lang": "zh-CN", "localService": True},
        {"name": "Google US English", "lang": "en-US", "localService": True},
    ]
    if not str(language).lower().startswith("zh"):
        voices = [
            {"name": "Google US English", "lang": "en-US", "localService": True},
            {"name": "Microsoft Aria Online (Natural)", "lang": "en-US", "localService": False},
        ]
    return {
        "user_agent": browser.user_agent,
        "browser_kind": kind,
        "languages": list(browser.languages),
        "language": language,
        "locale": language,
        "timezone_id": browser.timezone_id,
        "timezone_offset": timezone_offset_minutes(browser.timezone_id),
        "screen_width": width,
        "screen_height": height,
        "screen_avail_width": avail_width,
        "screen_avail_height": avail_height,
        "screen_avail_top": int(browser.screen_avail_top or 0),
        "outer_width": outer_width,
        "outer_height": outer_height,
        "device_pixel_ratio": float(browser.device_pixel_ratio or 1.0),
        "color_depth": int(browser.color_depth or 24),
        "is_extended": False,
        "hardware_concurrency": browser.hardware_concurrency,
        "device_memory": browser.device_memory,
        "max_touch_points": browser.max_touch_points,
        "platform": platform,
        "platform_version": platform_version,
        "architecture": browser.architecture,
        "bitness": browser.bitness,
        "model": browser.model,
        "oscpu": oscpu,
        "vendor": vendor,
        "product_sub": product_sub,
        "app_version": browser.user_agent,
        "pdf_viewer_enabled": is_chromium,
        "canvas_seed": browser.canvas_seed,
        "webgl_vendor": browser.webgl_vendor,
        "webgl_renderer": browser.webgl_renderer,
        "ua_data_brands": brands,
        "ua_data_platform": ua_platform,
        "ua_data_mobile": False,
        "ua_full_version": full_version,
        "full_version_list": full_version_list,
        "latitude": timezone_coordinates(browser.timezone_id)[0],
        "longitude": timezone_coordinates(browser.timezone_id)[1],
        "speech_voices": voices,
    }


@dataclass
class FingerprintSession:
    browser: BrowserFingerprint
    headers: dict[str, str]
    stealth_js: str
    launch_profile: BrowserLaunchProfile
    binding_name: str | None = None
    tls_impersonate: str | None = None
    stealth_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "binding": self.binding_name,
            "tls_impersonate": self.tls_impersonate,
            "browser": self.browser.to_dict(),
            "headers": dict(self.headers),
            "launch_args": self.launch_profile.args(),
            "stealth_values": dict(self.stealth_values),
        }


class FingerprintManager:
    """Rotate coherent profiles across HTTP and browser layers."""

    def __init__(
        self,
        *,
        seed: int | None = None,
        browser: str = "chrome",
        header_browser: str = "chrome",
        headless: bool = True,
        profiles: list[BrowserFingerprint] | None = None,
        patch_names: list[str] | tuple[str, ...] | None = None,
        fingerprint_binding: str | dict[str, Any] | FingerprintBinding | None = None,
    ) -> None:
        self.browser_family = browser
        self.binding = resolve_binding(fingerprint_binding)
        self.header_browser = (
            self.binding.header_fingerprint if self.binding is not None else header_browser
        )
        self.headless = headless
        self.patch_names = patch_names
        if self.binding is not None:
            self.profiles = profiles or [self.binding.to_browser_fingerprint()]
        else:
            self.profiles = profiles or [
                BrowserFingerprint.generate(
                    seed=seed + index if seed is not None else None,
                    browser=browser,
                )
                for index in range(4)
            ]
        self._index = 0

    def next(self) -> FingerprintSession:
        browser = self.profiles[self._index % len(self.profiles)]
        self._index += 1
        if self.binding is not None:
            browser = self.binding.to_browser_fingerprint()
            header = HeaderFingerprint.for_browser(self.binding.header_fingerprint)
            tls = self.binding.tls_impersonate
        else:
            header = HeaderFingerprint.for_browser(self.header_browser)
            tls = None
        headers = header.apply({"User-Agent": browser.user_agent})
        headers["Accept-Language"] = ",".join(browser.languages)
        stealth_values = self._patch_values(browser)
        launch = BrowserLaunchProfile(
            headless=self.headless,
            user_agent=browser.user_agent,
            locale=browser.languages[0] if browser.languages else "zh-CN",
            timezone_id=browser.timezone_id,
        )
        return FingerprintSession(
            browser=browser,
            headers=headers,
            stealth_js=compose_patches(self.patch_names, values=stealth_values),
            launch_profile=launch,
            binding_name=self.binding.name if self.binding is not None else None,
            tls_impersonate=tls,
            stealth_values=stealth_values,
        )

    def validate_binding(self) -> list[str]:
        return self.binding.validate() if self.binding is not None else []

    @staticmethod
    def _patch_values(browser: BrowserFingerprint) -> dict[str, Any]:
        return fingerprint_patch_values(browser)


if __name__ == "__main__":
    session = FingerprintManager(seed=1).next()
    print(session.to_dict())
