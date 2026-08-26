"""Automatic block diagnosis for pages, APIs, and media requests.

Combines HTTP status, response headers, body markers, Cloudflare challenge
state, robots.txt, and sitemap discovery into one actionable report. The
crawler and pipeline use the report to decide between retry, proxy rotation,
browser escalation, CAPTCHA solving, and skip.
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from cloudflare_challenge import (
    CloudflareChallengeState,
    extract_cloudflare_state,
)
from scrape_guard import RobotsPolicy, parse_retry_after
from security_detector import (
    SecurityReport,
    detect_security_mechanisms,
)

_CDN_HEADERS = (
    "cf-ray",
    "cf-cache-status",
    "cf-mitigated",
    "x-amz-cf-id",
    "x-amz-cf-pop",
    "x-sucuri-id",
    "x-dotdefender",
    "x-iinfo",
    "x-akamai-transformed",
    "server",
    "via",
    "x-cdn",
)
_AUTH_HEADERS = ("www-authenticate", "x-login-required", "x-auth-required")


@dataclass
class BlockDiagnosis:
    """Full diagnosis for one blocked or suspicious response."""

    url: str
    status: int | None
    security: SecurityReport
    cloudflare: CloudflareChallengeState
    headers: dict[str, str] = field(default_factory=dict)
    retry_after: float | None = None
    robots_allowed: bool | None = None
    robots_url: str | None = None
    sitemap_urls: list[str] = field(default_factory=list)
    challenge_retry: bool = False
    proxy_recommended: bool = False
    browser_recommended: bool = False
    captcha_recommended: bool = False
    cdn: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_response(
        cls,
        url: str,
        status: int | None,
        headers: dict[str, str] | None,
        body: str,
        *,
        page_url: str | None = None,
    ) -> BlockDiagnosis:
        headers = {str(key): str(value) for key, value in (headers or {}).items()}
        security = detect_security_mechanisms(
            status,
            url,
            headers,
            body,
            html=body,
            page_url=page_url or url,
        )
        cloudflare = extract_cloudflare_state(
            body,
            page_url=page_url or url,
            headers=headers,
        )
        retry_after = parse_retry_after(
            next(
                (
                    value
                    for key, value in headers.items()
                    if key.lower() == "retry-after"
                ),
                None,
            )
        )
        cdn = {
            key: headers[key]
            for key in _CDN_HEADERS
            if headers.get(key)
        }
        auth = {
            key: headers[key]
            for key in _AUTH_HEADERS
            if headers.get(key)
        }
        cdn.update(auth)
        diagnosis = cls(
            url=url,
            status=status,
            security=security,
            cloudflare=cloudflare,
            headers=headers,
            retry_after=retry_after,
            cdn=cdn,
        )
        diagnosis.challenge_retry = bool(
            cloudflare.present
            or status in {403, 429, 503}
            or security.primary_kind == "cloudflare_challenge"
        )
        diagnosis.proxy_recommended = bool(security.needs_proxy or status in {403, 429, 451})
        diagnosis.browser_recommended = bool(
            security.needs_browser or cloudflare.present or cloudflare.stage == "managed_non_interactive"
        )
        diagnosis.captcha_recommended = bool(security.needs_captcha or cloudflare.sitekey)
        return diagnosis

    def probe_robots_sitemap(self, session: Any) -> None:
        """Fetch robots.txt and extract Sitemap entries using the given session."""
        parts = urllib.parse.urlsplit(self.url)
        robots_url = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/robots.txt", "", "")
        )
        self.robots_url = robots_url
        raw = ""
        try:
            body, status, _ = session.get_bytes_with_meta(robots_url)
            if status == 200:
                raw = body.decode("utf-8", "replace")
                policy = RobotsPolicy()
                policy.load_text(raw)
                self.robots_allowed = policy.can_fetch(self.url)
        except Exception:
            self.robots_allowed = None
        for match in re.finditer(r"(?im)^\s*Sitemap\s*:\s*(\S+)", raw):
            candidate = match.group(1).strip()
            if candidate not in self.sitemap_urls:
                self.sitemap_urls.append(candidate)
        default_sitemap = urllib.parse.urlunsplit(
            (parts.scheme, parts.netloc, "/sitemap.xml", "", "")
        )
        if default_sitemap not in self.sitemap_urls:
            self.sitemap_urls.append(default_sitemap)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "retry_after": self.retry_after,
            "robots_allowed": self.robots_allowed,
            "robots_url": self.robots_url,
            "sitemap_urls": list(self.sitemap_urls),
            "challenge_retry": self.challenge_retry,
            "proxy_recommended": self.proxy_recommended,
            "browser_recommended": self.browser_recommended,
            "captcha_recommended": self.captcha_recommended,
            "cdn": dict(self.cdn),
            "security": self.security.to_dict(),
            "cloudflare": self.cloudflare.to_dict(),
        }


def diagnose_response(
    url: str,
    status: int | None,
    headers: dict[str, str] | None = None,
    body: str = "",
    *,
    page_url: str | None = None,
) -> BlockDiagnosis:
    """Diagnose a response without performing additional network probes."""
    return BlockDiagnosis.from_response(
        url,
        status,
        headers,
        body,
        page_url=page_url,
    )


if __name__ == "__main__":
    report = diagnose_response(
        "https://example.com/",
        403,
        {"cf-ray": "abc", "server": "cloudflare"},
        "<html>Just a moment...</html>",
    )
    print(report.to_dict())
