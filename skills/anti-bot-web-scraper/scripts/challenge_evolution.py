"""Dynamic anti-bot challenge variant fingerprinting.

Cloudflare, DataDome, Akamai and other vendors rotate challenge markup,
script paths, iframe URLs, cookie names and header signals over time. This
module turns one challenge response into a stable fingerprint so the rest
of the pipeline can detect a new variant, reuse strategy history for a
known variant, and report exactly what changed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

_IFRAME_SRC_RE = re.compile(r"<iframe[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)
_SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)

VENDOR_MARKERS: dict[str, tuple[str, ...]] = {
    "cloudflare": (
        "cf-chl",
        "cf_chl_opt",
        "cf_chl_rc_ni",
        "challenge-platform",
        "challenges.cloudflare.com",
        "__cf_bm",
        "cf_clearance",
    ),
    "datadome": (
        "datadome",
        "x-datadome",
        "captcha-delivery.com",
        "geo.captcha-delivery.com",
        "datadome-captcha",
    ),
    "akamai": (
        "_abck",
        "ak_bmsc",
        "bm_sz",
        "akamai",
        "akavpau_",
        "reference #",
        "sensor_data",
    ),
    "perimeterx": (
        "perimeterx",
        "px-captcha",
        "pxcdn",
        "_pxhd",
        "_px3",
    ),
    "shape": (
        "shape-security",
        "shape-api",
        "__shape",
        "shape.com",
    ),
    "kasada": (
        "kasada",
        "kpsdk",
        "x-kasada",
        "kasad",
    ),
    "imperva": (
        "imperva",
        "incapsula",
        "incap_ses",
        "visid_incap",
    ),
    "aws_waf": (
        "awswaf",
        "aws waf",
        "captcha.awswaf.com",
        "aws-waf-token",
    ),
    "f5": (
        "f5 networks",
        "big-ip",
        "x-wa-info",
    ),
    "alibaba": (
        "aliyun",
        "acw_tc",
        "aliyungf_tc",
        "waf_qcloud",
    ),
    "arkose": (
        "funcaptcha",
        "arkoselabs",
        "arkose",
    ),
    "fastly": (
        "fastly challenge",
        "fastly vcl error",
        "x-fastly-request-id",
    ),
    "sucuri": (
        "sucuri",
        "cloudproxy",
        "x-sucuri-id",
    ),
    "radware": (
        "radware captcha",
        "radware",
        "x-rdwr",
    ),
    "reblaze": (
        "reblaze",
        "rbzid",
        "x-reblaze",
    ),
    "stackpath": (
        "stackpath waf",
        "stackpath",
        "x-stackpath",
    ),
    "tencent": (
        "tencent security",
        "t-sec",
        "waf_qcloud",
        "x-waf-",
    ),
    "generic": (
        "access denied",
        "request blocked",
        "blocked by",
        "website firewall",
        "mod_security",
        "modsecurity",
        "your request has been blocked",
    ),
}

_URL_FILTER_WORDS = (
    "challenge",
    "captcha",
    "challenges.cloudflare.com",
    "captcha-delivery.com",
    "awswaf",
    "px-captcha",
    "akamai",
    "funcaptcha",
    "arkoselabs",
)


@dataclass
class ChallengeVariant:
    """Stable fingerprint of one challenge response variant."""

    vendor: str = "generic"
    stage: str = "unknown"
    markers: list[str] = field(default_factory=list)
    iframe_urls: list[str] = field(default_factory=list)
    script_urls: list[str] = field(default_factory=list)
    cookie_names: list[str] = field(default_factory=list)
    header_signals: list[str] = field(default_factory=list)
    signature: str = ""

    def __post_init__(self) -> None:
        if not self.signature:
            self.signature = self.compute_signature()

    def compute_signature(self) -> str:
        payload = {
            "vendor": self.vendor,
            "stage": self.stage,
            "markers": sorted(set(self.markers)),
            "iframes": sorted(set(self.iframe_urls)),
            "scripts": sorted(set(self.script_urls)),
            "cookies": sorted(set(self.cookie_names)),
            "headers": sorted(set(self.header_signals)),
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChallengeVariant:
        return cls(
            vendor=str(data.get("vendor") or "generic"),
            stage=str(data.get("stage") or "unknown"),
            markers=list(data.get("markers") or []),
            iframe_urls=list(data.get("iframe_urls") or []),
            script_urls=list(data.get("script_urls") or []),
            cookie_names=list(data.get("cookie_names") or []),
            header_signals=list(data.get("header_signals") or []),
            signature=str(data.get("signature") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "stage": self.stage,
            "markers": self.markers,
            "iframe_urls": self.iframe_urls,
            "script_urls": self.script_urls,
            "cookie_names": self.cookie_names,
            "header_signals": self.header_signals,
            "signature": self.signature,
        }


def _cookie_names(cookies: Iterable[Any] | None) -> list[str]:
    names: list[str] = []
    for item in cookies or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
        else:
            name = str(getattr(item, "name", "") or "")
        if name:
            names.append(name)
    return names


def fingerprint_challenge(
    *,
    vendor: str = "generic",
    stage: str = "unknown",
    html: str = "",
    headers: dict[str, str] | None = None,
    cookies: Iterable[Any] | None = None,
) -> ChallengeVariant:
    """Build a challenge variant from one blocked response."""
    text = (html or "").lower()
    markers = [
        marker
        for marker in VENDOR_MARKERS.get(str(vendor).lower(), VENDOR_MARKERS["generic"])
        if marker.lower() in text
    ]
    iframe_urls = [
        src
        for src in _IFRAME_SRC_RE.findall(html or "")
        if any(word in src.lower() for word in _URL_FILTER_WORDS)
    ]
    script_urls = [
        src
        for src in _SCRIPT_SRC_RE.findall(html or "")
        if any(word in src.lower() for word in _URL_FILTER_WORDS)
    ]
    cookie_names = _cookie_names(cookies)
    vendor_markers = VENDOR_MARKERS.get(str(vendor).lower(), VENDOR_MARKERS["generic"])
    header_signals: list[str] = []
    for key, value in (headers or {}).items():
        lower_key = str(key).lower()
        lower_value = str(value).lower()
        if any(marker.lower() in lower_key or marker.lower() in lower_value for marker in vendor_markers):
            header_signals.append(f"{key}:{value}")
    return ChallengeVariant(
        vendor=str(vendor).lower(),
        stage=stage,
        markers=markers,
        iframe_urls=iframe_urls,
        script_urls=script_urls,
        cookie_names=cookie_names,
        header_signals=header_signals,
    )


def marker_diff(previous: ChallengeVariant, current: ChallengeVariant) -> dict[str, list[str]]:
    """Return the marker/URL/cookie fields that changed between two variants."""
    fields = (
        "markers",
        "iframe_urls",
        "script_urls",
        "cookie_names",
        "header_signals",
    )
    return {
        field_name: [
            item
            for item in getattr(current, field_name)
            if item not in set(getattr(previous, field_name))
        ]
        for field_name in fields
    }


if __name__ == "__main__":
    sample = fingerprint_challenge(
        vendor="datadome",
        stage="datadome_captcha",
        html='<iframe src="https://geo.captcha-delivery.com/captcha"></iframe>',
    )
    print(json.dumps(sample.to_dict(), ensure_ascii=False, indent=2))
