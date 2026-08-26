"""Alternate endpoint fallback for bot-walled pages.

Many sites protect only the canonical HTML route but still serve the same
data through feeds, sitemaps, JSON endpoints, mobile hosts, or alternate
user agents. This module probes a bounded set of legitimate variants and
reuses the existing security classifier so a variant only counts as passed
when it is not blocked.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from media_session import MediaSession
from security_detector import detect_security_mechanisms

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 "
    "Mobile/15E148 Safari/604.1"
)
GOOGLEBOT_UA = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)
FEED_UA = "Feedbin feed-id:1 - 128 bytes"


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": DEFAULT_UA,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def _netloc_for_host(url: str, host: str) -> str:
    parts = urlsplit(url)
    netloc = host
    if parts.port is not None:
        netloc = f"{host}:{parts.port}"
    if parts.username:
        auth = parts.username
        if parts.password is not None:
            auth = f"{auth}:{parts.password}"
        netloc = f"{auth}@{netloc}"
    return netloc


def _variant_url(
    url: str,
    *,
    host: str | None = None,
    path: str | None = None,
    query: str | None = None,
) -> str:
    parts = urlsplit(url)
    if host is not None:
        parts = parts._replace(netloc=_netloc_for_host(url, host))
    if path is not None:
        parts = parts._replace(path=path)
    if query is not None:
        parts = parts._replace(query=query)
    return urlunsplit(parts._replace(fragment=""))


@dataclass
class AlternateVariant:
    """One bounded, legitimate request variant."""

    url: str
    reason: str
    headers: dict[str, str] = field(default_factory=_browser_headers)


@dataclass
class AlternateAccessResult:
    """Outcome of the alternate endpoint probe."""

    passed: bool = False
    url: str = ""
    status: int | None = None
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    strategy: str = "none"
    reason: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0
    security: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "url": self.url,
            "status": self.status,
            "strategy": self.strategy,
            "reason": self.reason,
            "attempts": self.attempts,
            "duration_ms": round(self.duration_ms, 3),
            "security": self.security,
        }


def build_alternate_variants(
    url: str,
    config: dict[str, Any] | None = None,
    *,
    max_variants: int = 16,
) -> list[AlternateVariant]:
    """Build a bounded list of alternate URLs/headers for one page."""
    cfg = dict(config or {})
    include = set(
        cfg.get("include")
        or ("www", "mobile", "amp", "feed", "rss", "sitemap", "api", "json", "query", "headers")
    )
    max_variants = max(1, int(cfg.get("max_variants", max_variants)))
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    base_path = parsed.path or "/"
    variants: list[AlternateVariant] = []
    seen: set[tuple[str, frozenset[tuple[str, str]]]] = set()

    def add(
        variant_url: str,
        reason: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        merged = _browser_headers()
        merged.update(headers or {})
        key = (variant_url, frozenset(merged.items()))
        if key in seen or len(variants) >= max_variants:
            return
        seen.add(key)
        variants.append(AlternateVariant(url=variant_url, reason=reason, headers=merged))

    if "feed" in include:
        for feed_path in ("/feed", "/rss", "/rss.xml", "/atom.xml"):
            add(_variant_url(url, path=feed_path), "feed")
    if "sitemap" in include:
        for sitemap_path in ("/sitemap.xml", "/sitemap_index.xml"):
            add(_variant_url(url, path=sitemap_path), "sitemap")
    if "api" in include:
        for api_path in ("/api/", "/api", "/wp-json/", "/graphql"):
            add(_variant_url(url, path=api_path), "api")
    if "json" in include and base_path:
        lowered = base_path.lower()
        if lowered.endswith((".html", ".htm", ".php", ".asp", ".aspx")):
            json_path = base_path.rsplit(".", 1)[0] + ".json"
            add(_variant_url(url, path=json_path), "json_suffix")
    if "query" in include:
        for query in ("format=json", "output=1", "_escaped_fragment_=", "amp=1"):
            add(_variant_url(url, query=query), "query")
    if "headers" in include:
        add(url, "json_accept", {"Accept": "application/json, text/plain, */*"})
        add(url, "mobile_ua", {"User-Agent": MOBILE_UA})
        add(url, "googlebot_ua", {"User-Agent": GOOGLEBOT_UA})
        add(url, "feed_ua", {"User-Agent": FEED_UA})
        add(
            url,
            "xhr",
            {"X-Requested-With": "XMLHttpRequest"},
        )
    if "www" in include:
        if host.startswith("www."):
            add(_variant_url(url, host=host[4:]), "bare_host")
        else:
            add(_variant_url(url, host=f"www.{host}"), "www_host")
    if "mobile" in include and host and not host.startswith("m."):
        add(_variant_url(url, host=f"m.{host}"), "mobile_host")
    if "amp" in include and host and not host.startswith("amp."):
        add(_variant_url(url, host=f"amp.{host}"), "amp_host")
    return variants[:max_variants]


def try_alternate_access(
    url: str,
    config: dict[str, Any] | None = None,
    *,
    proxy: str | None = None,
    timeout: float = 5.0,
    max_variants: int = 12,
) -> AlternateAccessResult:
    """Probe alternate endpoints and return the first non-blocked result."""
    started = time.monotonic()
    cfg = dict(config or {})
    alt_cfg = dict(cfg.get("alternate") or {})
    timeout = float(alt_cfg.get("timeout", timeout))
    max_variants = int(alt_cfg.get("max_variants", max_variants))
    variants = build_alternate_variants(url, alt_cfg, max_variants=max_variants)
    attempts: list[dict[str, Any]] = []
    session = MediaSession(proxy=proxy, min_interval=0.0, max_retries=0, timeout=timeout)
    try:
        for variant in variants:
            try:
                body, status, headers = session.get_bytes_with_meta(
                    variant.url,
                    headers=variant.headers,
                    timeout=timeout,
                )
            except Exception as exc:
                attempts.append(
                    {
                        "url": variant.url,
                        "reason": variant.reason,
                        "status": None,
                        "error": str(exc)[:300],
                    }
                )
                continue
            text = body.decode("utf-8", "replace")
            report = detect_security_mechanisms(
                status,
                variant.url,
                headers,
                text,
                html=text,
                page_url=variant.url,
            )
            attempts.append(
                {
                    "url": variant.url,
                    "reason": variant.reason,
                    "status": status,
                    "security": report.primary_kind,
                    "size": len(body),
                }
            )
            if 200 <= status < 400 and not report.is_blocked:
                return AlternateAccessResult(
                    passed=True,
                    url=variant.url,
                    status=status,
                    body=text,
                    headers=headers,
                    strategy=f"alternate:{variant.reason}",
                    reason=variant.reason,
                    attempts=attempts,
                    duration_ms=(time.monotonic() - started) * 1000,
                    security=report.to_dict(),
                )
    finally:
        session.close()
    return AlternateAccessResult(
        passed=False,
        url=url,
        attempts=attempts,
        duration_ms=(time.monotonic() - started) * 1000,
    )


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Probe alternate access routes")
    parser.add_argument("--url", required=True)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--max-variants", type=int, default=12)
    args = parser.parse_args()
    result = try_alternate_access(
        args.url,
        timeout=args.timeout,
        max_variants=args.max_variants,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
