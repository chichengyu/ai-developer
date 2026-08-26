"""Vendor-level anti-bot detection and strategy hints.

Cloudflare has its own dedicated module. This module classifies the other
common bot-management / WAF vendors so the pipeline can choose a compatible
TLS profile, browser-engine order, and challenge-cookie reload behavior.
It only reports observations and strategy hints; it does not bypass anything
itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

VENDOR_NONE = "none"
VENDOR_GENERIC = "generic_waf"
VENDOR_CLOUDFLARE = "cloudflare"
VENDOR_DATADOME = "datadome"
VENDOR_AKAMAI = "akamai"
VENDOR_PERIMETERX = "perimeterx"
VENDOR_SHAPE = "shape"
VENDOR_KASADA = "kasada"
VENDOR_IMPERVA = "imperva"
VENDOR_AWS_WAF = "aws_waf"
VENDOR_F5 = "f5"
VENDOR_ALIBABA = "alibaba"
VENDOR_ARKOSE = "arkose"
VENDOR_FASTLY = "fastly"
VENDOR_SUCURI = "sucuri"
VENDOR_RADWARE = "radware"
VENDOR_REBLAZE = "reblaze"
VENDOR_STACKPATH = "stackpath"
VENDOR_TENCENT = "tencent"

BODY_MARKERS = (
    "datadome",
    "x-datadome",
    "_abck",
    "ak_bmsc",
    "bm_sz",
    "perimeterx",
    "px-captcha",
    "pxcdn",
    "shape-security",
    "shape-api",
    "kasada",
    "kpsdk",
    "incapsula",
    "incap_ses",
    "visid_incap",
    "awswaf",
    "captcha.awswaf.com",
    "f5 networks",
    "big-ip",
    "aliyungf_tc",
    "acw_tc",
    "funcaptcha",
    "arkoselabs",
    "arkose",
    "captcha-delivery.com",
    "fastly challenge",
    "sucuri cloudproxy",
    "radware captcha",
    "reblaze access denied",
    "stackpath waf",
    "tencent security",
)


def _compile(*patterns: str) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


_VENDOR_SPECS: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        VENDOR_CLOUDFLARE,
        {
            "name": "Cloudflare",
            "headers": ("cf-ray", "cf-mitigated", "cf-challenge", "server: cloudflare"),
            "body_regex": _compile(
                r"challenge-platform",
                r"cf-chl",
                r"cloudflare.*(challenge|block)",
            ),
            "cookie_names": ("cf_clearance", "__cf_bm"),
            "cookie_prefixes": (),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "scrapling"),
            "actions": ("browser", "captcha"),
        },
    ),
    (
        VENDOR_DATADOME,
        {
            "name": "DataDome",
            "headers": ("x-datadome", "server: datadome", "x-dd-"),
            "body_regex": _compile(r"datadome", r"captcha-delivery\.com", r"x-datadome"),
            "cookie_names": ("datadome",),
            "cookie_prefixes": ("datadome",),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "seleniumbase"),
            "actions": ("browser", "proxy", "captcha"),
        },
    ),
    (
        VENDOR_AKAMAI,
        {
            "name": "Akamai",
            "headers": ("x-akamai-transformed", "server: akamaighost", "x-akamai-"),
            "body_regex": _compile(r"akamai", r"_abck", r"ak_bmsc", r"bm_sz", r"reference #"),
            "cookie_names": ("_abck", "ak_bmsc", "bm_sz"),
            "cookie_prefixes": ("akavpau_", "pmc_"),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_PERIMETERX,
        {
            "name": "PerimeterX / HUMAN",
            "headers": ("x-px-", "px-captcha", "x-perimeterx"),
            "body_regex": _compile(r"perimeterx", r"px-captcha", r"pxcdn", r"_pxhd"),
            "cookie_names": ("_px", "_px3", "_pxhd", "_pxde", "_pxvid"),
            "cookie_prefixes": ("_px",),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "seleniumbase"),
            "actions": ("browser", "captcha", "proxy"),
        },
    ),
    (
        VENDOR_SHAPE,
        {
            "name": "Shape Security / F5 Shape",
            "headers": ("x-shape-", "server: shape"),
            "body_regex": _compile(r"shape-security", r"shape-api", r"__shape", r"shape\.com"),
            "cookie_names": ("__shape", "__sl", "shape"),
            "cookie_prefixes": ("__shape",),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "camoufox", "seleniumbase"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_KASADA,
        {
            "name": "Kasada",
            "headers": ("x-kasada", "server: kasada"),
            "body_regex": _compile(r"kasada", r"kpsdk", r"x-kasada"),
            "cookie_names": ("kasad", "kpsdk_ct", "kpsdk_ct_"),
            "cookie_prefixes": ("kasad", "kpsdk"),
            "impersonate": "chrome",
            "engines": ("camoufox", "patchright", "nodriver"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_IMPERVA,
        {
            "name": "Imperva / Incapsula",
            "headers": ("x-iinfo", "server: imperva", "x-cdn: imperva", "x-incap-"),
            "body_regex": _compile(r"imperva", r"incapsula", r"incap_ses", r"visid_incap"),
            "cookie_names": ("incap_ses_", "visid_incap_", "nlbi_"),
            "cookie_prefixes": ("incap_ses_", "visid_incap_", "nlbi_"),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_AWS_WAF,
        {
            "name": "AWS WAF",
            "headers": ("x-amzn-waf-action", "x-amzn-requestid", "x-amz-cf-id"),
            "body_regex": _compile(r"awswaf", r"aws waf", r"captcha\.awswaf\.com"),
            "cookie_names": ("aws-waf-token",),
            "cookie_prefixes": ("awswaf_", "aws-waf-"),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("browser", "captcha", "proxy"),
        },
    ),
    (
        VENDOR_F5,
        {
            "name": "F5 BIG-IP ASM",
            "headers": ("x-wa-info", "server: bigip", "x-f5-"),
            "body_regex": _compile(r"f5 networks", r"big-ip", r"x-wa-info"),
            "cookie_names": ("TS", "F5"),
            "cookie_prefixes": ("TS", "F5"),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_ALIBABA,
        {
            "name": "Alibaba Cloud WAF",
            "headers": ("x-ca-", "aliyun"),
            "body_regex": _compile(r"aliyun", r"acw_tc", r"aliyungf_tc"),
            "cookie_names": ("acw_tc", "aliyungf_tc", "tfstk"),
            "cookie_prefixes": ("acw_",),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "seleniumbase"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_ARKOSE,
        {
            "name": "Arkose / FunCaptcha",
            "headers": (),
            "body_regex": _compile(r"funcaptcha", r"arkoselabs", r"arkose"),
            "cookie_names": (),
            "cookie_prefixes": (),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "seleniumbase"),
            "actions": ("captcha", "browser"),
        },
    ),
    (
        VENDOR_FASTLY,
        {
            "name": "Fastly",
            "headers": ("server: fastly", "x-fastly-request-id", "x-served-by"),
            "body_regex": _compile(
                r"fastly challenge",
                r"fastly vcl error",
                r"fastly.*access denied",
            ),
            "cookie_names": (),
            "cookie_prefixes": ("fastly_",),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("proxy", "browser"),
        },
    ),
    (
        VENDOR_SUCURI,
        {
            "name": "Sucuri",
            "headers": ("x-sucuri-id", "x-sucuri-cache", "x-sucuri-block"),
            "body_regex": _compile(r"sucuri", r"cloudproxy", r"sucuri.*firewall"),
            "cookie_names": (),
            "cookie_prefixes": ("sucuri_cloudproxy_",),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("proxy", "browser"),
        },
    ),
    (
        VENDOR_RADWARE,
        {
            "name": "Radware",
            "headers": ("x-rdwr", "x-radware", "server: radware"),
            "body_regex": _compile(
                r"radware captcha",
                r"radware.*access denied",
                r"radware.*challenge",
            ),
            "cookie_names": ("radware", "rdwr"),
            "cookie_prefixes": ("rdwr_", "radware_"),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "seleniumbase"),
            "actions": ("browser", "proxy"),
        },
    ),
    (
        VENDOR_REBLAZE,
        {
            "name": "Reblaze",
            "headers": ("x-reblaze", "server: reblaze"),
            "body_regex": _compile(
                r"reblaze security",
                r"reblaze.*access denied",
                r"reblaze",
            ),
            "cookie_names": ("rbzid",),
            "cookie_prefixes": ("reblaze_", "rbz_"),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("proxy", "browser"),
        },
    ),
    (
        VENDOR_STACKPATH,
        {
            "name": "StackPath",
            "headers": ("x-stackpath", "server: stackpath"),
            "body_regex": _compile(
                r"stackpath waf",
                r"stackpath.*access denied",
                r"stackpath.*challenge",
            ),
            "cookie_names": ("stackpath",),
            "cookie_prefixes": ("sp_",),
            "impersonate": "chrome",
            "engines": ("patchright", "nodriver", "seleniumbase", "camoufox"),
            "actions": ("proxy", "browser"),
        },
    ),
    (
        VENDOR_TENCENT,
        {
            "name": "Tencent Cloud WAF",
            "headers": ("server: tencent", "x-tx-", "x-waf-"),
            "body_regex": _compile(
                r"tencent.*waf",
                r"qcloud.*waf",
                r"t-sec",
                r"waf_qcloud",
            ),
            "cookie_names": ("t_security", "t_cookie"),
            "cookie_prefixes": ("qcloud_",),
            "impersonate": "chrome",
            "engines": ("patchright", "camoufox", "nodriver", "seleniumbase"),
            "actions": ("browser", "proxy"),
        },
    ),
)

_GENERIC_WAF_RE = _compile(
    r"access denied",
    r"request blocked",
    r"blocked by",
    r"website firewall",
    r"mod_security",
    r"modsecurity",
    r"your request has been blocked",
)

_CHALLENGE_STAGES: dict[str, tuple[tuple[str, str], ...]] = {
    "cloudflare": (
        (r"turnstile|sitekey", "cloudflare_turnstile"),
        (r"challenge-platform|cf-chl|cf_chl_opt", "cloudflare_managed"),
        (r"managed challenge", "cloudflare_managed"),
    ),
    "datadome": (
        (r"captcha-delivery\.com|datadome-captcha|datadome.*captcha", "datadome_captcha"),
        (r"datadome|challenge", "datadome_challenge"),
    ),
    "akamai": (
        (r"reference #|access denied|blocked", "akamai_block"),
        (r"captcha|verify your identity|are you human", "akamai_captcha"),
        (r"_abck|ak_bmsc|bm_sz|sensor_data", "akamai_sensor"),
    ),
    "perimeterx": (
        (r"px-captcha|px-captcha-container", "perimeterx_captcha"),
        (r"perimeterx|_px3|_pxhd", "perimeterx_challenge"),
    ),
    "shape": (
        (r"shape-security|shape-api|__shape", "shape_challenge"),
    ),
    "kasada": (
        (r"kasada|kpsdk|kasad", "kasada_challenge"),
    ),
    "imperva": (
        (r"incapsula|incap_ses|visid_incap", "imperva_challenge"),
    ),
    "aws_waf": (
        (r"captcha\.awswaf\.com|awswaf.*captcha", "aws_waf_captcha"),
        (r"awswaf|aws-waf-token", "aws_waf_challenge"),
    ),
    "f5": (
        (r"f5 networks|big-ip|x-wa-info", "f5_challenge"),
    ),
    "alibaba": (
        (r"acw_tc|aliyungf_tc|waf_qcloud", "alibaba_waf_challenge"),
    ),
    "arkose": (
        (r"funcaptcha|arkoselabs|arkose", "arkose_captcha"),
    ),
    "fastly": (
        (r"fastly challenge|fastly vcl error|access denied", "fastly_block"),
    ),
    "sucuri": (
        (r"sucuri|cloudproxy", "sucuri_block"),
    ),
    "radware": (
        (r"radware captcha", "radware_captcha"),
        (r"radware|rdwr", "radware_challenge"),
    ),
    "reblaze": (
        (r"reblaze|rbzid", "reblaze_block"),
    ),
    "stackpath": (
        (r"stackpath waf|stackpath", "stackpath_block"),
    ),
    "tencent": (
        (r"t-sec|waf_qcloud|tencent security", "tencent_waf_challenge"),
    ),
}

ANTI_BOT_COOKIE_NAMES = frozenset(
    name
    for _, spec in _VENDOR_SPECS
    for name in spec["cookie_names"]
)
ANTI_BOT_COOKIE_PREFIXES = frozenset(
    prefix
    for _, spec in _VENDOR_SPECS
    for prefix in spec["cookie_prefixes"]
)


@dataclass
class VendorDetection:
    """One classified anti-bot vendor with strategy hints."""

    vendor: str = VENDOR_NONE
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    challenge_cookies: list[str] = field(default_factory=list)
    recommended_impersonate: str | None = None
    recommended_engines: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    challenge_stage: str = "unknown"
    signature: str = ""

    @property
    def detected(self) -> bool:
        return self.vendor not in {VENDOR_NONE, VENDOR_GENERIC}

    def to_dict(self) -> dict[str, Any]:
        return {
            "vendor": self.vendor,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
            "challenge_cookies": self.challenge_cookies,
            "recommended_impersonate": self.recommended_impersonate,
            "recommended_engines": self.recommended_engines,
            "actions": self.actions,
            "challenge_stage": self.challenge_stage,
            "signature": self.signature,
        }


def _lower_headers(headers: dict[str, str] | None) -> dict[str, str]:
    return {
        str(key).lower(): str(value).lower()
        for key, value in (headers or {}).items()
    }


def _header_hit(lower: dict[str, str], marker: str) -> bool:
    marker = marker.lower()
    for key, value in lower.items():
        if marker in key or marker in value:
            return True
        if ":" in marker:
            header_key, _, header_value = marker.partition(":")
            header_key = header_key.strip()
            header_value = header_value.strip()
            if header_key in key and header_value in value:
                return True
    return False


def _cookie_hit(name: str, spec: dict[str, Any]) -> bool:
    lowered = name.lower()
    if lowered in {str(item).lower() for item in spec["cookie_names"]}:
        return True
    return any(lowered.startswith(str(prefix).lower()) for prefix in spec["cookie_prefixes"])


def _normalize_cookies(cookies: Iterable[Any] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in cookies or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            if name:
                result.append({"name": name, "value": str(item.get("value") or "")})
        elif hasattr(item, "name") and hasattr(item, "value"):
            result.append({"name": str(item.name), "value": str(item.value)})
    return result


def _detect_challenge_stage(vendor: str, text: str) -> str:
    for pattern, stage in _CHALLENGE_STAGES.get(vendor, ()):
        if re.search(pattern, text, re.IGNORECASE):
            return stage
    return "unknown"


def detect_vendor(
    status: int | None = None,
    headers: dict[str, str] | None = None,
    body: str | None = None,
    cookies: Iterable[Any] | None = None,
) -> VendorDetection:
    """Classify the vendor behind a blocked or challenge response."""
    lower = _lower_headers(headers)
    text = (body or "").lower()
    cookie_items = _normalize_cookies(cookies)
    best: VendorDetection | None = None
    for vendor, spec in _VENDOR_SPECS:
        score = 0.0
        evidence: list[str] = []
        challenge_cookies: list[str] = list(spec["cookie_names"]) + [
            f"{prefix}*" for prefix in spec["cookie_prefixes"]
        ]
        if status in {403, 429, 503}:
            score += 0.08
        for marker in spec["headers"]:
            if _header_hit(lower, marker):
                score += 0.42
                evidence.append(f"header:{marker}")
        if spec["body_regex"].search(text):
            score += 0.34
            evidence.append("body markers")
        for item in cookie_items:
            if _cookie_hit(item["name"], spec):
                score += 0.28
                challenge_cookies.append(item["name"])
                evidence.append(f"cookie:{item['name']}")
        if score < 0.5:
            continue
        confidence = min(0.98, 0.4 + score)
        challenge_stage = _detect_challenge_stage(vendor, text)
        if challenge_stage != "unknown":
            evidence.append(f"stage:{challenge_stage}")
        signature = ""
        if body or cookie_items or lower:
            try:
                from challenge_evolution import fingerprint_challenge

                signature = fingerprint_challenge(
                    vendor=vendor,
                    stage=challenge_stage,
                    html=body or "",
                    headers=headers,
                    cookies=cookie_items,
                ).signature
            except Exception:
                pass
        detection = VendorDetection(
            vendor=vendor,
            confidence=confidence,
            evidence=evidence[:8],
            challenge_cookies=challenge_cookies[:8],
            recommended_impersonate=str(spec["impersonate"] or ""),
            recommended_engines=list(spec["engines"]),
            actions=list(spec["actions"]),
            challenge_stage=challenge_stage,
            signature=signature,
        )
        if best is None or confidence > best.confidence:
            best = detection
    if best is not None:
        return best
    if _GENERIC_WAF_RE.search(text) or status in {403, 429}:
        return VendorDetection(
            vendor=VENDOR_GENERIC,
            confidence=0.5,
            evidence=["generic WAF markers"],
            actions=["proxy", "browser"],
        )
    return VendorDetection()


def anti_bot_cookie_present(cookies: Iterable[Any] | None) -> bool:
    """Return True when any known challenge cookie is present."""
    for item in _normalize_cookies(cookies):
        name = item["name"].lower()
        if name in ANTI_BOT_COOKIE_NAMES:
            return True
        if any(name.startswith(prefix) for prefix in ANTI_BOT_COOKIE_PREFIXES):
            return True
    return False


def vendor_for_cookie(name: str) -> str | None:
    """Return the vendor that owns a challenge cookie name, if known."""
    for vendor, spec in _VENDOR_SPECS:
        if _cookie_hit(name, spec):
            return vendor
    return None


def recommended_engine_order(
    vendor: str,
    available: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Return the recommended engine order for a vendor, honoring installed."""
    for detected_vendor, spec in _VENDOR_SPECS:
        if detected_vendor != vendor:
            continue
        engines = list(spec["engines"])
        if available is not None:
            installed = set(available)
            return [engine for engine in engines if engine in installed] or engines
        return engines
    return []


if __name__ == "__main__":
    print(detect_vendor(403, {"x-datadome": "1"}, "<html>datadome challenge</html>").to_dict())
