"""Full-chain fingerprint binding across HTTP, TLS, and browser layers.

A real visitor identity is one coherent browser, not three independent
profiles. This module maps a named profile to a single user agent, header
set, TLS impersonation target, and compatible stealth-browser engine so the
HTTP stack does not advertise Chrome while the browser layer looks like
Firefox.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from fingerprint_bank import BrowserFingerprint, HeaderFingerprint


def _ua_version(user_agent: str, browser_family: str) -> str | None:
    ua = user_agent.lower()
    if browser_family == "safari":
        pattern = r"version/(\d+)"
    elif browser_family == "firefox":
        pattern = r"firefox/(\d+)"
    else:
        pattern = r"chrome/(\d+)"
    match = re.search(pattern, ua)
    return match.group(1) if match else None


def _tls_version(tls_impersonate: str) -> str | None:
    match = re.search(r"(\d+)", tls_impersonate)
    return match.group(1) if match else None


@dataclass(frozen=True)
class FingerprintBinding:
    """One coherent identity used by every transport layer."""

    name: str
    browser_family: str
    header_fingerprint: str
    tls_impersonate: str
    user_agent: str
    platform: str = "Windows"
    languages: tuple[str, ...] = ("zh-CN", "zh", "en-US", "en")
    timezone_id: str = "Asia/Shanghai"
    viewport: tuple[int, int] = (1920, 1080)
    hardware_concurrency: int = 8
    device_memory: int = 8
    compatible_engines: tuple[str, ...] = field(
        default_factory=lambda: (
            "patchright",
            "nodriver",
            "drission_page",
            "seleniumbase",
            "undetected_chromedriver",
            "selenium",
        )
    )
    header_order: tuple[str, ...] = ()

    def to_header_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        profile = HeaderFingerprint.for_browser(self.header_fingerprint)
        merged = profile.apply(extra or {})
        merged["User-Agent"] = self.user_agent
        merged["Accept-Language"] = ",".join(self.languages)
        if self.header_order:
            return merged
        return merged

    def to_browser_fingerprint(self) -> BrowserFingerprint:
        if self.header_fingerprint in {"edge", "msedge"}:
            kind = "edge"
        elif self.browser_family == "firefox":
            kind = "firefox"
        elif self.browser_family == "safari":
            kind = "safari"
        else:
            kind = "chrome"
        is_mac = "mac" in self.platform.lower() or kind == "safari"
        return BrowserFingerprint(
            user_agent=self.user_agent,
            browser_kind=kind,
            platform=self.platform,
            languages=self.languages,
            timezone_id=self.timezone_id,
            viewport=self.viewport,
            screen_width=self.viewport[0],
            screen_height=self.viewport[1],
            screen_avail_width=self.viewport[0],
            screen_avail_height=max(0, self.viewport[1] - 40),
            outer_width=self.viewport[0],
            outer_height=self.viewport[1],
            hardware_concurrency=self.hardware_concurrency,
            device_memory=self.device_memory,
            platform_version="15.0.0" if is_mac else "10.0.0",
            architecture="x86",
            bitness="64",
            webgl_vendor="Apple Inc." if is_mac else "Intel Inc.",
            webgl_renderer=(
                "Apple GPU"
                if is_mac
                else "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 "
                "vs_5_0 ps_5_0, D3D11)"
            ),
        )

    def to_launch_profile_dict(self, headless: bool = True) -> dict[str, Any]:
        return {
            "headless": headless,
            "user_agent": self.user_agent,
            "locale": self.languages[0] if self.languages else "en-US",
            "extra_args": [
                f"--lang={self.languages[0]}" if self.languages else "--lang=en-US",
                f"--timezone={self.timezone_id}",
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "browser_family": self.browser_family,
            "header_fingerprint": self.header_fingerprint,
            "tls_impersonate": self.tls_impersonate,
            "user_agent": self.user_agent,
            "platform": self.platform,
            "languages": list(self.languages),
            "timezone_id": self.timezone_id,
            "viewport": list(self.viewport),
            "hardware_concurrency": self.hardware_concurrency,
            "device_memory": self.device_memory,
            "compatible_engines": list(self.compatible_engines),
            "header_order": list(self.header_order),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FingerprintBinding:
        profile_name = str(data.get("name") or "custom")
        known = BINDINGS.get(profile_name)
        base = known.to_dict() if known is not None else {}
        merged = dict(base)
        merged.update(data)
        header_order = tuple(merged.get("header_order") or ())
        return cls(
            name=profile_name,
            browser_family=str(merged.get("browser_family") or "chrome"),
            header_fingerprint=str(
                merged.get("header_fingerprint")
                or merged.get("header_profile")
                or "chrome"
            ),
            tls_impersonate=str(
                merged.get("tls_impersonate") or merged.get("tls") or "chrome_124"
            ),
            user_agent=str(merged.get("user_agent") or ""),
            platform=str(merged.get("platform") or "Windows"),
            languages=tuple(merged.get("languages") or ("zh-CN", "zh", "en-US", "en")),
            timezone_id=str(merged.get("timezone_id") or "Asia/Shanghai"),
            viewport=tuple(merged.get("viewport") or (1920, 1080)),
            hardware_concurrency=int(merged.get("hardware_concurrency") or 8),
            device_memory=int(merged.get("device_memory") or 8),
            compatible_engines=tuple(
                merged.get("compatible_engines") or known.compatible_engines
            )
            if known is not None
            else tuple(merged.get("compatible_engines") or ()),
            header_order=header_order,
        )

    def validate(self) -> list[str]:
        """Return human-readable consistency problems for this profile."""
        issues: list[str] = []
        ua = self.user_agent.lower()
        if self.browser_family == "chrome" and "chrome/" not in ua:
            issues.append("Chrome binding has a non-Chrome user agent")
        if self.browser_family == "firefox" and "firefox/" not in ua:
            issues.append("Firefox binding has a non-Firefox user agent")
        if self.browser_family == "safari" and "safari/" not in ua:
            issues.append("Safari binding has a non-Safari user agent")
        if self.header_fingerprint in {"edge", "msedge"} and "edg/" not in ua:
            issues.append("Edge headers do not match a Chromium Edge user agent")
        if self.browser_family == "safari" and "mac" not in self.platform.lower():
            issues.append("Safari binding must use a macOS platform")
        if "chrome" in self.header_fingerprint and "chrome/" not in ua:
            issues.append("Chrome HTTP headers do not match the user agent")
        if self.browser_family == "firefox" and "firefox" not in self.tls_impersonate.lower():
            issues.append("Firefox binding uses a non-Firefox TLS impersonation target")
        if self.browser_family == "chrome" and "chrome" not in self.tls_impersonate.lower():
            issues.append("Chrome binding uses a non-Chrome TLS impersonation target")
        ua_version = _ua_version(self.user_agent, self.browser_family)
        tls_version = _tls_version(self.tls_impersonate)
        if ua_version is not None and tls_version is not None and ua_version != tls_version:
            issues.append(
                f"TLS impersonation version {tls_version} does not match "
                f"user agent version {ua_version}"
            )
        if not self.user_agent:
            issues.append("user agent is empty")
        return issues


def _binding(
    name: str,
    family: str,
    header: str,
    tls: str,
    ua: str,
    engines: tuple[str, ...],
    platform: str = "Windows",
) -> FingerprintBinding:
    return FingerprintBinding(
        name=name,
        browser_family=family,
        header_fingerprint=header,
        tls_impersonate=tls,
        user_agent=ua,
        platform=platform,
        compatible_engines=engines,
    )


BINDINGS: dict[str, FingerprintBinding] = {
    "chrome126": _binding(
        "chrome126",
        "chrome",
        "chrome",
        "chrome_124",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        (
            "patchright",
            "nodriver",
            "drission_page",
            "seleniumbase",
            "undetected_chromedriver",
            "selenium",
        ),
    ),
    "chrome124": _binding(
        "chrome124",
        "chrome",
        "chrome",
        "chrome_124",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        (
            "patchright",
            "nodriver",
            "drission_page",
            "seleniumbase",
            "undetected_chromedriver",
            "selenium",
        ),
    ),
    "chrome120": _binding(
        "chrome120",
        "chrome",
        "chrome",
        "chrome_120",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        (
            "patchright",
            "nodriver",
            "drission_page",
            "seleniumbase",
            "undetected_chromedriver",
            "selenium",
        ),
    ),
    "edge124": _binding(
        "edge124",
        "chrome",
        "edge",
        "chrome_124",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        ),
        (
            "patchright",
            "nodriver",
            "drission_page",
            "seleniumbase",
            "undetected_chromedriver",
            "selenium",
        ),
    ),
    "edge126": _binding(
        "edge126",
        "chrome",
        "edge",
        "chrome_124",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0"
        ),
        (
            "patchright",
            "nodriver",
            "drission_page",
            "seleniumbase",
            "undetected_chromedriver",
            "selenium",
        ),
    ),
    "firefox127": _binding(
        "firefox127",
        "firefox",
        "firefox",
        "firefox_124",
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) "
            "Gecko/20100101 Firefox/127.0"
        ),
        ("camoufox", "scrapling"),
    ),
    "safari17": _binding(
        "safari17",
        "safari",
        "safari",
        "safari_15_6_1",
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        ),
        (),
        "macOS",
    ),
}


def resolve_binding(value: str | dict[str, Any] | FingerprintBinding | None) -> FingerprintBinding | None:
    """Resolve a profile name, dict, or binding object to a stable profile."""
    if value is None:
        return None
    if isinstance(value, FingerprintBinding):
        return value
    if isinstance(value, dict):
        if not value:
            return None
        return FingerprintBinding.from_dict(value)
    key = str(value).strip().lower()
    if not key:
        return None
    if key in BINDINGS:
        return BINDINGS[key]
    family_aliases = {
        "chrome": "chrome124",
        "chromium": "chrome124",
        "edge": "edge124",
        "firefox": "firefox127",
        "ff": "firefox127",
        "safari": "safari17",
        "webkit": "safari17",
    }
    if key in family_aliases:
        return BINDINGS[family_aliases[key]]
    raise ValueError(f"unknown fingerprint binding: {value}")


def binding_from_fetch_config(config: dict[str, Any] | None) -> FingerprintBinding | None:
    """Read a binding from a fetch config while staying backward compatible."""
    cfg = dict(config or {})
    direct = cfg.get("fingerprint_binding") or cfg.get("binding")
    if direct is not None:
        return resolve_binding(direct)
    browser = cfg.get("browser") or {}
    nested = browser.get("fingerprint_binding") or browser.get("binding")
    if nested is not None:
        return resolve_binding(nested)
    return None


def apply_binding_to_fetch_config(
    config: dict[str, Any] | None,
    binding: FingerprintBinding | None,
) -> dict[str, Any]:
    """Return a fetch config whose TLS and HTTP layers use one binding."""
    cfg = dict(config or {})
    if binding is None:
        return cfg
    cfg["impersonate"] = binding.tls_impersonate
    cfg["header_fingerprint"] = binding.header_fingerprint
    browser = dict(cfg.get("browser") or {})
    browser["fingerprint_binding"] = binding.name
    browser.setdefault("user_agent", binding.user_agent)
    if binding.compatible_engines:
        configured_engine = str(browser.get("engine") or "auto").lower()
        if configured_engine in {"auto", "adaptive", "smart"}:
            browser["engine"] = "auto"
            browser["stealth_engine_order"] = list(binding.compatible_engines)
    cfg["browser"] = browser
    return cfg


def available_bindings() -> list[str]:
    return list(BINDINGS)


def binding_report(binding: FingerprintBinding) -> dict[str, Any]:
    return {
        "name": binding.name,
        "browser_family": binding.browser_family,
        "user_agent": binding.user_agent,
        "tls_impersonate": binding.tls_impersonate,
        "header_fingerprint": binding.header_fingerprint,
        "compatible_engines": list(binding.compatible_engines),
        "issues": binding.validate(),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(binding_report(BINDINGS["chrome126"]), ensure_ascii=False, indent=2))
