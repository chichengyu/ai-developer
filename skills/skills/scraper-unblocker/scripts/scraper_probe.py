#!/usr/bin/env python3
"""Probe a web target and diagnose common blocking signals.

Stdlib-only diagnostic tool. It checks robots.txt and sitemap.xml, fetches the
target, and maps status codes, headers, and body markers to compliant next
steps. It never solves challenges or bypasses access controls.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_USER_AGENT = "scraper-unblocker-probe/1.0 (contact: replace-me@example.com)"

BLOCK_PATTERNS = {
    "challenge": [
        "just a moment",
        "checking your browser",
        "cf-chl",
        "cf-challenge",
        "attention required",
        "verify you are human",
        "captcha",
        "turnstile",
        "hcaptcha",
        "recaptcha",
        "perimeterx",
        "px-captcha",
        "kasada",
        "arkose",
        "intelligent tracking prevention",
    ],
    "waf": [
        "access denied",
        "request blocked",
        "sorry, you have been blocked",
        "incapsula",
        "akamai",
        "distil",
        "datadome",
        "sucuri",
        "imperva",
        "akamaighost",
        "shape security",
        "request rejected",
        "web application firewall",
    ],
    "js_required": [
        "please enable javascript",
        "javascript is required",
        "enable javascript and cookies",
        "javascript is disabled",
    ],
    "cookie_wall": [
        "accept cookies",
        "cookie settings",
        "your privacy",
        "consent",
    ],
}


def build_opener(proxy: Optional[str]) -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def parse_headers(items: List[str]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for item in items:
        if ":" not in item:
            continue
        key, _, value = item.partition(":")
        headers[key.strip()] = value.strip()
    return headers


def load_cookie_header(cookies_file: Optional[str]) -> Optional[str]:
    if not cookies_file:
        return None
    try:
        with open(cookies_file, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return None
    cookies = data.get("cookies", []) if isinstance(data, dict) else data
    parts = []
    for cookie in cookies:
        if isinstance(cookie, dict) and cookie.get("name") and cookie.get("value"):
            parts.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(parts) if parts else None


def decode_body(body: bytes, content_type: str = "") -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charset = match.group(1) if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 15.0,
    proxy: Optional[str] = None,
    max_bytes: int = 200_000,
    extra_headers: Optional[Dict[str, str]] = None,
    cookie: Optional[str] = None,
) -> Dict[str, Any]:
    opener = build_opener(proxy)
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if cookie:
        headers["Cookie"] = cookie
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    result = {
        "requested_url": url,
        "status": None,
        "final_url": url,
        "headers": {},
        "body_bytes": 0,
        "body_text": "",
        "error": None,
    }
    try:
        with opener.open(request, timeout=timeout) as response:
            result["status"] = response.status
            result["final_url"] = response.geturl()
            result["headers"] = {k.lower(): v for k, v in response.headers.items()}
            body = response.read(max_bytes + 1)
            result["body_bytes"] = len(body)
            result["body_text"] = decode_body(
                body, result["headers"].get("content-type", "")
            )
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["final_url"] = exc.geturl() or url
        result["headers"] = {k.lower(): v for k, v in exc.headers.items()}
        body = exc.read(max_bytes + 1)
        result["body_bytes"] = len(body)
        result["body_text"] = decode_body(body, result["headers"].get("content-type", ""))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def parse_robots(text: str) -> Dict[str, Any]:
    rules: Dict[str, List[Tuple[bool, str]]] = {}
    crawl_delays: Dict[str, float] = {}
    current: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current = value.lower()
            rules.setdefault(current, [])
        elif key in ("disallow", "allow") and current is not None:
            rules[current].append((key == "allow", value))
        elif key == "crawl-delay" and current is not None:
            try:
                crawl_delays[current] = float(value)
            except ValueError:
                pass
    return {"rules": rules, "crawl_delays": crawl_delays}


def robots_path_allowed(path: str, pattern: str) -> bool:
    if not pattern:
        return True
    regex = re.escape(pattern).replace(r"\*", ".*")
    if pattern.endswith("$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def robots_allowed(
    url: str, user_agent: str, robots_text: str
) -> Tuple[bool, str, Optional[float]]:
    parsed = parse_robots(robots_text)
    url_parts = urllib.parse.urlparse(url)
    target = (url_parts.path or "/") + (("?" + url_parts.query) if url_parts.query else "")
    for agent in (user_agent.lower(), "*"):
        if agent not in parsed["rules"]:
            continue
        for is_allow, pattern in parsed["rules"][agent]:
            if robots_path_allowed(target, pattern):
                return is_allow, ("Allow " if is_allow else "Disallow ") + pattern, parsed[
                    "crawl_delays"
                ].get(agent)
    return True, "no matching robots rule", None


def check_robots_and_sitemap(
    url: str,
    user_agent: str,
    timeout: float,
    proxy: Optional[str],
    max_bytes: int,
    extra_headers: Optional[Dict[str, str]] = None,
    cookie: Optional[str] = None,
) -> Dict[str, Any]:
    url_parts = urllib.parse.urlparse(url)
    base = f"{url_parts.scheme}://{url_parts.netloc}"
    robots_url = urllib.parse.urljoin(base + "/", "robots.txt")
    robots_resp = fetch(
        robots_url,
        user_agent,
        timeout,
        proxy,
        max_bytes=50_000,
        extra_headers=extra_headers,
        cookie=cookie,
    )
    robots_text = robots_resp["body_text"] if robots_resp["status"] == 200 else ""
    allowed, rule, crawl_delay = robots_allowed(url, user_agent, robots_text)
    sitemap_urls = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_text)
    return {
        "url": robots_url,
        "status": robots_resp["status"],
        "disallows_target": not allowed,
        "matched_rule": rule,
        "crawl_delay": crawl_delay,
        "sitemap": sitemap_urls[0] if sitemap_urls else None,
        "error": robots_resp["error"],
    }


def detect_blocks(response: Dict[str, Any]) -> List[Dict[str, str]]:
    status = response["status"]
    headers = response["headers"]
    body = response["body_text"].lower()
    signals: List[Dict[str, str]] = []

    if status == 401:
        signals.append(
            {
                "type": "auth_required",
                "evidence": "HTTP 401",
                "advice": "Use the official authenticated API or stop; do not bypass login.",
            }
        )
    if status == 403:
        signals.append(
            {
                "type": "waf_or_access",
                "evidence": "HTTP 403",
                "advice": "Check robots and request hygiene; if the resource is access-controlled, stop or use the official API.",
            }
        )
    if status == 429:
        signals.append(
            {
                "type": "rate_limited",
                "evidence": "HTTP 429",
                "advice": "Honor Retry-After and add exponential backoff with jitter.",
            }
        )
    if status == 503:
        signals.append(
            {
                "type": "temporarily_unavailable",
                "evidence": "HTTP 503",
                "advice": "Retry later; if the body shows a challenge, stop automation.",
            }
        )

    server = headers.get("server", "").lower()
    if "cloudflare" in server or any(key.startswith("cf-") for key in headers):
        signals.append(
            {
                "type": "cloudflare",
                "evidence": "Cloudflare server or cf-* headers present",
                "advice": "Use the official API or get permission; do not automate interactive challenges.",
            }
        )
    waf_header_keys = [
        "x-datadome",
        "x-akamai",
        "x-sucuri-id",
        "x-waf",
        "x-amz-cf-id",
        "x-azure-ref",
        "x-cdn",
    ]
    if status in (401, 403, 429, 503) and any(key in headers for key in waf_header_keys):
        signals.append(
            {
                "type": "waf_headers",
                "evidence": "Blocking status with WAF/CDN headers present",
                "advice": "Reduce volume and fix request hygiene; if access-controlled, stop or use the official API.",
            }
        )

    for kind, patterns in BLOCK_PATTERNS.items():
        hits = [pattern for pattern in patterns if pattern in body]
        if not hits:
            continue
        advice_by_kind = {
            "challenge": "Stop automation; use the official API, a documented export, or a human-in-the-loop session.",
            "waf": "Reduce volume and fix request hygiene; if still blocked, stop or get permission.",
            "js_required": "Render with Playwright/Selenium; do not add stealth patches.",
            "cookie_wall": "If data is consent-gated, use the official API or documented export.",
        }
        signals.append(
            {
                "type": kind,
                "evidence": ", ".join(hits),
                "advice": advice_by_kind[kind],
            }
        )

    unique: Dict[str, Dict[str, str]] = {}
    for signal in signals:
        unique.setdefault(signal["type"], signal)
    return list(unique.values())


def build_advice(
    robots: Dict[str, Any], blocks: List[Dict[str, str]]
) -> List[str]:
    advice: List[str] = []
    if robots.get("disallows_target"):
        advice.append(
            f"robots.txt disallows this target ({robots['matched_rule']}); do not crawl it."
        )
    if robots.get("sitemap"):
        advice.append(f"Sitemap available: {robots['sitemap']}; prefer it over guessing URLs.")
    for signal in blocks:
        advice.append(f"[{signal['type']}] {signal['evidence']} -> {signal['advice']}")
    if not advice and not blocks:
        advice.append("No block signals detected. Start with scraper_runner.py and keep volume low.")
    return advice


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose common anti-bot blocks for a web target."
    )
    parser.add_argument("--url", required=True, help="Target URL to probe.")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT, help="Crawler User-Agent.")
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds.")
    parser.add_argument("--proxy", default=None, help="HTTP/HTTPS proxy URL.")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="Extra request header; repeatable.",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help="Cookie header for an authorized session you already hold.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="JSON session file from session_capture.py or browser storage state.",
    )
    parser.add_argument("--max-bytes", type=int, default=200_000, help="Max body bytes to analyze.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)

    extra_headers = parse_headers(args.header)
    cookie = args.cookie or load_cookie_header(args.cookies_file)
    robots = check_robots_and_sitemap(
        args.url,
        args.user_agent,
        args.timeout,
        args.proxy,
        args.max_bytes,
        extra_headers,
        cookie,
    )
    response = fetch(
        args.url,
        args.user_agent,
        args.timeout,
        args.proxy,
        args.max_bytes,
        extra_headers,
        cookie,
    )
    blocks = detect_blocks(response)
    advice = build_advice(robots, blocks)
    report = {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "target": args.url,
        "robots": robots,
        "response": {
            "status": response["status"],
            "final_url": response["final_url"],
            "headers": response["headers"],
            "body_bytes": response["body_bytes"],
            "body_snippet": response["body_text"][:500],
            "error": response["error"],
        },
        "block_signals": blocks,
        "advice": advice,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("Target:", args.url)
        print("Probed at:", report["probed_at"])
        print()
        print("robots.txt:", robots["url"], "status", robots["status"])
        print("  target disallowed:", robots["disallows_target"])
        print("  matched rule:", robots["matched_rule"])
        print("  sitemap:", robots["sitemap"] or "not declared")
        print()
        print("response status:", response["status"])
        print("final URL:", response["final_url"])
        print("body bytes analyzed:", response["body_bytes"])
        if response["error"]:
            print("fetch error:", response["error"])
        print()
        print("block signals:", len(blocks))
        for signal in blocks:
            print(f"  [{signal['type']}] {signal['evidence']}")
        print()
        print("suggested next steps:")
        for item in advice:
            print("  -", item)

    if robots["disallows_target"]:
        return 2
    if blocks or response["error"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
