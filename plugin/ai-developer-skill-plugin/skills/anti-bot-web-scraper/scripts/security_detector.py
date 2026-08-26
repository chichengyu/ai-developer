"""Automatic identification of anti-bot and content-security mechanisms.

This module classifies an HTTP response / HTML body into known obstacle
types: Cloudflare challenge or block, generic WAF block, rate limit,
CAPTCHA wall, login wall, cookie-consent wall, JS challenge, geo block,
empty SPA shell, and server error. It does not bypass anything; it tells
the pipeline which existing, compliant strategy applies (browser render,
proxy rotation, CAPTCHA service, login session, retry, or skip) so the
whole flow can run without a human.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from captcha_solver import detect_captchas
from cloudflare_challenge import extract_cloudflare_state
from waf_vendor import detect_vendor

CLOUDFLARE_CHALLENGE = "cloudflare_challenge"
CLOUDFLARE_BLOCKED = "cloudflare_blocked"
WAF_BLOCKED = "waf_blocked"
RATE_LIMITED = "rate_limited"
CAPTCHA_REQUIRED = "captcha_required"
LOGIN_REQUIRED = "login_required"
COOKIE_CONSENT_WALL = "cookie_consent_wall"
JS_REQUIRED = "js_required"
GEO_BLOCKED = "geo_blocked"
SERVER_ERROR = "server_error"
EMPTY_PAGE = "empty_page"
DYNAMIC_PAGE = "dynamic_page"
IP_REPUTATION_BLOCKED = "ip_reputation_blocked"
DATADOME_CHALLENGE = "datadome_challenge"
AKAMAI_CHALLENGE = "akamai_challenge"
PERIMETERX_CHALLENGE = "perimeterx_challenge"
SHAPE_CHALLENGE = "shape_challenge"
KASADA_CHALLENGE = "kasada_challenge"
IMPERVA_CHALLENGE = "imperva_challenge"
AWS_WAF_CHALLENGE = "aws_waf_challenge"
F5_CHALLENGE = "f5_challenge"
ALIBABA_WAF_CHALLENGE = "alibaba_waf_challenge"
ARKOSE_CAPTCHA = "arkose_captcha"
FASTLY_CHALLENGE = "fastly_challenge"
SUCURI_BLOCKED = "sucuri_blocked"
RADWARE_CHALLENGE = "radware_challenge"
REBLAZE_CHALLENGE = "reblaze_challenge"
STACKPATH_CHALLENGE = "stackpath_challenge"
TENCENT_WAF_CHALLENGE = "tencent_waf_challenge"
DYNAMIC_CHALLENGE_VARIANT = "dynamic_challenge_variant"

KNOWN_KINDS = (
    CLOUDFLARE_CHALLENGE,
    CLOUDFLARE_BLOCKED,
    WAF_BLOCKED,
    RATE_LIMITED,
    CAPTCHA_REQUIRED,
    LOGIN_REQUIRED,
    COOKIE_CONSENT_WALL,
    JS_REQUIRED,
    GEO_BLOCKED,
    SERVER_ERROR,
    EMPTY_PAGE,
    DYNAMIC_PAGE,
    IP_REPUTATION_BLOCKED,
    DATADOME_CHALLENGE,
    AKAMAI_CHALLENGE,
    PERIMETERX_CHALLENGE,
    SHAPE_CHALLENGE,
    KASADA_CHALLENGE,
    IMPERVA_CHALLENGE,
    AWS_WAF_CHALLENGE,
    F5_CHALLENGE,
    ALIBABA_WAF_CHALLENGE,
    ARKOSE_CAPTCHA,
    FASTLY_CHALLENGE,
    SUCURI_BLOCKED,
    RADWARE_CHALLENGE,
    REBLAZE_CHALLENGE,
    STACKPATH_CHALLENGE,
    TENCENT_WAF_CHALLENGE,
    DYNAMIC_CHALLENGE_VARIANT,
)

_BLOCKING_KINDS = frozenset(
    {
        CLOUDFLARE_CHALLENGE,
        CLOUDFLARE_BLOCKED,
        WAF_BLOCKED,
        RATE_LIMITED,
        CAPTCHA_REQUIRED,
        LOGIN_REQUIRED,
        JS_REQUIRED,
        GEO_BLOCKED,
        SERVER_ERROR,
        IP_REPUTATION_BLOCKED,
        DATADOME_CHALLENGE,
        AKAMAI_CHALLENGE,
        PERIMETERX_CHALLENGE,
        SHAPE_CHALLENGE,
        KASADA_CHALLENGE,
        IMPERVA_CHALLENGE,
        AWS_WAF_CHALLENGE,
        F5_CHALLENGE,
        ALIBABA_WAF_CHALLENGE,
        ARKOSE_CAPTCHA,
        FASTLY_CHALLENGE,
        SUCURI_BLOCKED,
        RADWARE_CHALLENGE,
        REBLAZE_CHALLENGE,
        STACKPATH_CHALLENGE,
        TENCENT_WAF_CHALLENGE,
        DYNAMIC_CHALLENGE_VARIANT,
    }
)

_VENDOR_KIND = {
    "datadome": DATADOME_CHALLENGE,
    "akamai": AKAMAI_CHALLENGE,
    "perimeterx": PERIMETERX_CHALLENGE,
    "shape": SHAPE_CHALLENGE,
    "kasada": KASADA_CHALLENGE,
    "imperva": IMPERVA_CHALLENGE,
    "aws_waf": AWS_WAF_CHALLENGE,
    "f5": F5_CHALLENGE,
    "alibaba": ALIBABA_WAF_CHALLENGE,
    "arkose": ARKOSE_CAPTCHA,
    "fastly": FASTLY_CHALLENGE,
    "sucuri": SUCURI_BLOCKED,
    "radware": RADWARE_CHALLENGE,
    "reblaze": REBLAZE_CHALLENGE,
    "stackpath": STACKPATH_CHALLENGE,
    "tencent": TENCENT_WAF_CHALLENGE,
}

_CLOUDFLARE_CHALLENGE_RE = re.compile(
    r"(just a moment|checking your browser|verifying your browser|"
    r"verify you are human|verify you are not a robot|"
    r"enable javascript and cookies to continue|cf_chl_opt|challenge passed)",
    re.IGNORECASE,
)
_CLOUDFLARE_PLATFORM_RE = re.compile(
    r"(challenge-platform|cf-chl|cf-challenge|managed challenge|"
    r"cloudflare.*challenge)",
    re.IGNORECASE,
)
_ACCESS_GATE_RE = re.compile(
    r"(just a moment|checking your browser|verifying your browser|"
    r"verify you are human|verify you are not a robot|"
    r"enable javascript and cookies to continue|"
    r"attention required|access denied|request blocked|"
    r"you are being rate limited|verify your identity|are you human|"
    r"complete the security check|please complete the captcha|"
    r"captcha required|your request has been blocked|reference #)",
    re.IGNORECASE,
)
_CLOUDFLARE_BLOCKED_RE = re.compile(
    r"(attention required|cloudflare ray id|error code 1020|" r"access denied|request blocked)",
    re.IGNORECASE,
)
_WAF_BLOCKED_RE = re.compile(
    r"(access denied|request blocked|blocked by|mod_security|modsecurity|"
    r"imperva|incapsula|akamai.*blocked|your request has been blocked|"
    r"sorry, you have been blocked|reference #|请求被拒绝|访问被拒绝|"
    r"被拦截|防火墙拦截)",
    re.IGNORECASE,
)
_RATE_LIMIT_RE = re.compile(
    r"(rate limit|rate limited|too many requests|访问过于频繁|"
    r"请求过于频繁|请稍后再试|try again later)",
    re.IGNORECASE,
)
_LOGIN_REQUIRED_RE = re.compile(
    r"(sign in to continue|log in to continue|login to continue|"
    r"please sign in|please log in|session has expired|session expired|"
    r"请登录|登录后|登录才能|登录已过期|需要登录)",
    re.IGNORECASE,
)
_COOKIE_CONSENT_RE = re.compile(
    r"(cookie consent|cookie policy|accept all cookies|accept cookies|"
    r"同意使用 Cookie|接受所有 Cookie|同意并继续|同意 Cookie)",
    re.IGNORECASE,
)
_JS_REQUIRED_RE = re.compile(
    r"(enable javascript|enable js|javascript is disabled|"
    r"please enable javascript|your browser must support javascript|"
    r"启用 JavaScript|需要启用 JavaScript|浏览器需要支持 JavaScript|"
    r"js challenge)",
    re.IGNORECASE,
)
_GEO_BLOCK_RE = re.compile(
    r"(not available in your country|not available in your region|"
    r"geographic restriction|地域限制|地区限制|所在地区不可用|"
    r"此内容在你所在的地区不可用)",
    re.IGNORECASE,
)
_DYNAMIC_SHELL_RE = re.compile(
    r'(id=["\'](root|app|__nuxt|app-mount|__next)["\']|'
    r'id=["\']__NEXT_DATA__["\']|id=["\']__NUXT__["\'])',
    re.IGNORECASE,
)


@dataclass
class SecurityFinding:
    """One classified obstacle with evidence and a compliant next action."""

    kind: str
    confidence: float
    evidence: str
    recommendation: str
    severity: str = "medium"
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "severity": self.severity,
            "details": self.details,
        }


@dataclass
class SecurityReport:
    """Aggregated classification for one request/response pair."""

    url: str
    status: int | None
    findings: list[SecurityFinding] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return any(item.kind in _BLOCKING_KINDS for item in self.findings)

    @property
    def needs_browser(self) -> bool:
        return any(
            item.kind
            in {
                CLOUDFLARE_CHALLENGE,
                JS_REQUIRED,
                COOKIE_CONSENT_WALL,
                EMPTY_PAGE,
                DYNAMIC_PAGE,
                IP_REPUTATION_BLOCKED,
                CAPTCHA_REQUIRED,
                LOGIN_REQUIRED,
                DATADOME_CHALLENGE,
                AKAMAI_CHALLENGE,
                PERIMETERX_CHALLENGE,
                SHAPE_CHALLENGE,
                KASADA_CHALLENGE,
                IMPERVA_CHALLENGE,
                AWS_WAF_CHALLENGE,
                F5_CHALLENGE,
                ALIBABA_WAF_CHALLENGE,
                ARKOSE_CAPTCHA,
                FASTLY_CHALLENGE,
                SUCURI_BLOCKED,
                RADWARE_CHALLENGE,
                REBLAZE_CHALLENGE,
                STACKPATH_CHALLENGE,
                TENCENT_WAF_CHALLENGE,
                DYNAMIC_CHALLENGE_VARIANT,
            }
            for item in self.findings
        )

    @property
    def needs_proxy(self) -> bool:
        return any(
            item.kind
            in {
                CLOUDFLARE_BLOCKED,
                WAF_BLOCKED,
                RATE_LIMITED,
                GEO_BLOCKED,
                SERVER_ERROR,
                IP_REPUTATION_BLOCKED,
                DATADOME_CHALLENGE,
                AKAMAI_CHALLENGE,
                PERIMETERX_CHALLENGE,
                SHAPE_CHALLENGE,
                KASADA_CHALLENGE,
                IMPERVA_CHALLENGE,
                AWS_WAF_CHALLENGE,
                F5_CHALLENGE,
                ALIBABA_WAF_CHALLENGE,
                FASTLY_CHALLENGE,
                SUCURI_BLOCKED,
                RADWARE_CHALLENGE,
                REBLAZE_CHALLENGE,
                STACKPATH_CHALLENGE,
                TENCENT_WAF_CHALLENGE,
            }
            for item in self.findings
        )

    @property
    def needs_captcha(self) -> bool:
        return any(
            item.kind
            in {
                CAPTCHA_REQUIRED,
                CLOUDFLARE_CHALLENGE,
                ARKOSE_CAPTCHA,
                AWS_WAF_CHALLENGE,
                DATADOME_CHALLENGE,
                PERIMETERX_CHALLENGE,
                AKAMAI_CHALLENGE,
                SHAPE_CHALLENGE,
                KASADA_CHALLENGE,
                IMPERVA_CHALLENGE,
                F5_CHALLENGE,
                ALIBABA_WAF_CHALLENGE,
                RADWARE_CHALLENGE,
                TENCENT_WAF_CHALLENGE,
            }
            for item in self.findings
        )

    @property
    def needs_login(self) -> bool:
        return any(item.kind == LOGIN_REQUIRED for item in self.findings)

    @property
    def primary_kind(self) -> str | None:
        if not self.findings:
            return None
        return max(self.findings, key=lambda item: item.confidence).kind

    @property
    def actions(self) -> list[str]:
        actions: list[str] = []
        if any(item.kind in {RATE_LIMITED, SERVER_ERROR, EMPTY_PAGE} for item in self.findings):
            actions.append("retry")
        if self.needs_proxy:
            actions.append("proxy")
        if self.needs_browser:
            actions.append("browser")
        if self.needs_captcha:
            actions.append("captcha")
        if self.needs_login:
            actions.append("login")
        if self.is_blocked:
            actions.append("skip")
        return actions

    @property
    def strategy(self) -> str:
        """Return one primary compliant strategy for this obstacle."""
        strategy_by_kind = {
            CLOUDFLARE_CHALLENGE: "browser",
            CLOUDFLARE_BLOCKED: "proxy",
            WAF_BLOCKED: "proxy",
            RATE_LIMITED: "retry",
            CAPTCHA_REQUIRED: "captcha",
            LOGIN_REQUIRED: "login",
            COOKIE_CONSENT_WALL: "browser",
            JS_REQUIRED: "browser",
            GEO_BLOCKED: "proxy",
            SERVER_ERROR: "retry",
            EMPTY_PAGE: "browser",
            DYNAMIC_PAGE: "browser",
            IP_REPUTATION_BLOCKED: "proxy",
            DATADOME_CHALLENGE: "browser",
            AKAMAI_CHALLENGE: "browser",
            PERIMETERX_CHALLENGE: "browser",
            SHAPE_CHALLENGE: "browser",
            KASADA_CHALLENGE: "browser",
            IMPERVA_CHALLENGE: "browser",
            AWS_WAF_CHALLENGE: "browser",
            F5_CHALLENGE: "browser",
            ALIBABA_WAF_CHALLENGE: "browser",
            ARKOSE_CAPTCHA: "captcha",
            FASTLY_CHALLENGE: "proxy",
            SUCURI_BLOCKED: "proxy",
            RADWARE_CHALLENGE: "browser",
            REBLAZE_CHALLENGE: "proxy",
            STACKPATH_CHALLENGE: "proxy",
            TENCENT_WAF_CHALLENGE: "browser",
            DYNAMIC_CHALLENGE_VARIANT: "browser",
        }
        if not self.findings:
            return "proceed"
        primary = max(self.findings, key=lambda item: item.confidence)
        return strategy_by_kind.get(primary.kind, "skip")

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "blocked": self.is_blocked,
            "primary_kind": self.primary_kind,
            "actions": self.actions,
            "needs_browser": self.needs_browser,
            "needs_proxy": self.needs_proxy,
            "needs_captcha": self.needs_captcha,
            "needs_login": self.needs_login,
            "strategy": self.strategy,
            "findings": [item.to_dict() for item in self.findings],
        }


def _lower_headers(headers: dict[str, str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in (headers or {}).items():
        result[str(key).lower()] = str(value)
    return result


def _add(
    findings: list[SecurityFinding],
    kind: str,
    confidence: float,
    evidence: str,
    recommendation: str,
    *,
    severity: str = "medium",
    details: dict[str, Any] | None = None,
) -> None:
    existing = next((item for item in findings if item.kind == kind), None)
    if existing is None:
        findings.append(
            SecurityFinding(
                kind=kind,
                confidence=confidence,
                evidence=evidence,
                recommendation=recommendation,
                severity=severity,
                details=details or {},
            )
        )
    elif confidence > existing.confidence:
        existing.confidence = confidence
        existing.evidence = evidence
        existing.recommendation = recommendation
        existing.severity = severity
        existing.details = details or {}


def detect_security_mechanisms(
    status: int | None,
    url: str,
    headers: dict[str, str] | None = None,
    body_text: str | None = None,
    *,
    html: str | None = None,
    page_url: str | None = None,
) -> SecurityReport:
    """Classify an HTTP response into actionable security findings."""
    lower = _lower_headers(headers)
    body = body_text or ""
    text = body.lower()
    stripped = body.strip()
    html_doc = html if html is not None else body
    findings: list[SecurityFinding] = []

    if status == 401:
        _add(
            findings,
            LOGIN_REQUIRED,
            0.95,
            "HTTP 401 requires authentication",
            "use an account session / login flow",
            severity="high",
        )
    elif status == 403:
        cloudflare_block_wording = _CLOUDFLARE_BLOCKED_RE.search(text) and (
            lower.get("cf-ray") or "cloudflare" in text or "cf-error" in text
        )
        if cloudflare_block_wording or lower.get("cf-mitigated") == "blocked":
            _add(
                findings,
                CLOUDFLARE_BLOCKED,
                0.95,
                "Cloudflare returned an access-denied page",
                "rotate proxy and retry, or respect the block",
                severity="high",
            )
        elif _WAF_BLOCKED_RE.search(text) or any(
            marker in lower
            for marker in (
                "x-sucuri-id",
                "x-dotdefender",
                "x-iinfo",
                "x-akamai-transformed",
                "x-waf-blocked",
                "x-cdn",
            )
        ):
            _add(
                findings,
                WAF_BLOCKED,
                0.85,
                "WAF markers present in headers or body",
                "rotate proxy, retry with browser fingerprint, or respect the block",
                severity="high",
            )
        elif _LOGIN_REQUIRED_RE.search(text):
            _add(
                findings,
                LOGIN_REQUIRED,
                0.75,
                "403 page asks for a login session",
                "use an account session / login flow",
                severity="high",
            )
        else:
            _add(
                findings,
                WAF_BLOCKED,
                0.5,
                "HTTP 403 without an explicit challenge",
                "rotate proxy, retry with browser fingerprint, or respect the block",
                severity="high",
            )
    elif status == 429:
        retry_after = lower.get("retry-after")
        _add(
            findings,
            RATE_LIMITED,
            0.97,
            "HTTP 429 rate limit",
            "honor Retry-After, reduce pacing, rotate proxy",
            severity="high",
            details={"retry_after": retry_after},
        )
    elif status == 451:
        _add(
            findings,
            GEO_BLOCKED,
            0.95,
            "HTTP 451 indicates a geographic block",
            "use a proxy in an allowed region or respect the block",
            severity="high",
        )
    elif status is not None and status >= 500:
        _add(
            findings,
            SERVER_ERROR,
            0.85,
            f"HTTP {status} server error",
            "retry with backoff, then rotate proxy",
            severity="high",
        )

    mitigated = lower.get("cf-mitigated", "")
    cf_header_challenge = (
        mitigated.lower() in {"challenge", "turnstile", "managed_challenge"}
        or any(key.startswith("cf-chl") for key in lower)
        or lower.get("cf-challenge") == "true"
        or lower.get("x-cf-chl") == "true"
    )
    cf_platform = _CLOUDFLARE_PLATFORM_RE.search(text)
    if (
        _CLOUDFLARE_CHALLENGE_RE.search(text)
        or cf_header_challenge
        or (cf_platform and (status in {None, 403, 503} or _ACCESS_GATE_RE.search(text)))
    ):
        cf_state = extract_cloudflare_state(body, url, [], lower)
        _add(
            findings,
            CLOUDFLARE_CHALLENGE,
            0.95,
            "Cloudflare challenge page detected",
            "render with the fingerprint browser and wait for the challenge",
            severity="high",
            details={
                "stage": cf_state.stage,
                "sitekey": cf_state.sitekey,
                "frame_url": cf_state.frame_url,
                "ray_id": cf_state.ray_id,
                "clearance_cookie": bool(cf_state.clearance_cookie),
            },
        )
    elif _CLOUDFLARE_BLOCKED_RE.search(text) and lower.get("cf-ray"):
        _add(
            findings,
            CLOUDFLARE_BLOCKED,
            0.9,
            "Cloudflare block page detected",
            "rotate proxy and retry, or respect the block",
            severity="high",
        )

    if (
        ("humans only" in text or "your ip address" in text)
        and ("cloudflare location" in text or lower.get("cf-ray"))
    ):
        _add(
            findings,
            IP_REPUTATION_BLOCKED,
            0.9,
            "site reports an IP-reputation block",
            "use a residential proxy in an allowed region",
            severity="high",
        )

    vendor = detect_vendor(status, headers, body)
    vendor_kind = _VENDOR_KIND.get(vendor.vendor)
    if vendor_kind and (
        status is None or status >= 400 or _ACCESS_GATE_RE.search(text)
    ):
        _add(
            findings,
            vendor_kind,
            min(0.98, vendor.confidence + 0.15),
            f"{vendor.evidence[0] if vendor.evidence else vendor.vendor} detected",
            "render in a fingerprint browser, keep challenge cookies, and reload",
            severity="high",
            details={
                "vendor": vendor.vendor,
                "confidence": vendor.confidence,
                "evidence": vendor.evidence,
                "challenge_cookies": vendor.challenge_cookies,
                "recommended_impersonate": vendor.recommended_impersonate,
                "recommended_engines": vendor.recommended_engines,
                "challenge_stage": vendor.challenge_stage,
                "signature": vendor.signature,
            },
        )
        findings = [item for item in findings if item.kind != WAF_BLOCKED]
        if vendor.challenge_stage == "unknown":
            _add(
                findings,
                DYNAMIC_CHALLENGE_VARIANT,
                0.6,
                f"unknown {vendor.vendor} challenge stage detected",
                "render with the full browser strategy and record the new signature",
                severity="medium",
                details={
                    "vendor": vendor.vendor,
                    "signature": vendor.signature,
                    "evidence": vendor.evidence,
                },
            )

    large_page = len(stripped) >= 20000
    if (
        _WAF_BLOCKED_RE.search(text)
        and not any(
            item.kind in {CLOUDFLARE_BLOCKED, CLOUDFLARE_CHALLENGE}
            for item in findings
        )
        and (
            status is None
            or status >= 400
            or (not large_page and _ACCESS_GATE_RE.search(text))
        )
    ):
        _add(
            findings,
            WAF_BLOCKED,
            0.8,
            "WAF block wording detected in body",
            "rotate proxy, retry with browser fingerprint, or respect the block",
            severity="high",
        )

    if _RATE_LIMIT_RE.search(text) and (
        status in {None, 403, 429, 500, 502, 503, 504}
        or _ACCESS_GATE_RE.search(text)
    ):
        _add(
            findings,
            RATE_LIMITED,
            0.85,
            "rate-limit wording detected",
            "honor Retry-After, reduce pacing, rotate proxy",
            severity="high",
        )

    captchas = detect_captchas(html_doc, page_url or url) if html_doc else []
    captcha_gate = (
        status is None
        or status >= 400
        or bool(_ACCESS_GATE_RE.search(text))
    )
    if captchas and captcha_gate:
        _add(
            findings,
            CAPTCHA_REQUIRED,
            min(0.99, max(item.confidence for item in captchas) + 0.15),
            "CAPTCHA elements detected in page",
            "use the automatic CAPTCHA solver (OCR / third-party service)",
            severity="high",
            details={"kinds": sorted({item.kind for item in captchas})},
        )
    elif captcha_gate and any(
        marker in text
        for marker in (
            "captcha",
            "recaptcha",
            "hcaptcha",
            "turnstile",
            "geetest",
            "人机验证",
            "安全验证",
        )
    ):
        _add(
            findings,
            CAPTCHA_REQUIRED,
            0.55,
            "CAPTCHA wording detected",
            "use the automatic CAPTCHA solver (OCR / third-party service)",
            severity="medium",
        )

    if (
        _LOGIN_REQUIRED_RE.search(text)
        and not any(item.kind == LOGIN_REQUIRED for item in findings)
        and (status is None or status >= 400 or not large_page)
    ):
        _add(
            findings,
            LOGIN_REQUIRED,
            0.65,
            "login-required wording detected",
            "use an account session / login flow",
            severity="medium",
        )

    if _COOKIE_CONSENT_RE.search(text):
        _add(
            findings,
            COOKIE_CONSENT_WALL,
            0.7,
            "cookie-consent wall detected",
            "render in browser and accept the consent dialog",
            severity="low",
        )

    if _JS_REQUIRED_RE.search(text) and not any(
        item.kind in {CLOUDFLARE_CHALLENGE, CLOUDFLARE_BLOCKED} for item in findings
    ):
        _add(
            findings,
            JS_REQUIRED,
            0.75,
            "page requires JavaScript",
            "render with the fingerprint browser",
            severity="medium",
        )

    if _GEO_BLOCK_RE.search(text):
        _add(
            findings,
            GEO_BLOCKED,
            0.8,
            "geographic restriction detected",
            "use a proxy in an allowed region or respect the block",
            severity="high",
        )

    content_type = lower.get("content-type", "").lower()
    if status in {None, 200} and (not content_type or "html" in content_type) and not findings:
        if _DYNAMIC_SHELL_RE.search(text) and len(stripped) < 2000:
            _add(
                findings,
                DYNAMIC_PAGE,
                0.65,
                "SPA shell detected without rendered data",
                "render in browser and capture after JavaScript runs",
                severity="low",
            )
        elif len(stripped) < 100 and not re.search(r"<html|<body", text):
            _add(
                findings,
                EMPTY_PAGE,
                0.6,
                "response body is effectively empty",
                "render in browser, wait for network idle, or retry",
                severity="low",
            )

    findings.sort(key=lambda item: (-item.confidence, item.kind))
    return SecurityReport(url=url, status=status, findings=findings)


if __name__ == "__main__":
    print(
        "desktop-app-dev security_detector: import detect_security_mechanisms() for block classification."
    )
