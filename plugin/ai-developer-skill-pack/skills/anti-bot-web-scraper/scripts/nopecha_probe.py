"""One-command probe for the nopecha.com Cloudflare full-page demo.

Reports the real public IP (STUN) versus the HTTP egress IP, runs a stealth
browser engine against the demo page, and returns a compact verdict with the
challenge state, cookie evidence, and any public IP visible on the page.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import browser_flags  # noqa: E402
import stealth_browser  # noqa: E402
from cloudflare_challenge import extract_cloudflare_state  # noqa: E402
from proxy_pool import ProxyPool  # noqa: E402
from stealth_browser import (  # noqa: E402
    _challenge_pending,  # noqa: E402
    available_stealth_engines,  # noqa: E402
    solve_cloudflare_with_stealth_browser,  # noqa: E402
)

TARGET = "https://nopecha.com/demo/cloudflare"
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_LABELED_IP_RES = (
    re.compile(
        r"(?:your\s+)?(?:public\s+)?(?:ip|ip\s+address|client\s+ip)"
        r"[^0-9]{0,40}(\d{1,3}(?:\.\d{1,3}){3})",
        re.IGNORECASE,
    ),
    re.compile(r"ip\s*[:：]\s*(\d{1,3}(?:\.\d{1,3}){3})", re.IGNORECASE),
)
_JSON_IP_RE = re.compile(
    r"""["']ip["']\s*[:=]\s*["']([^"']+)["']""",
    re.IGNORECASE,
)
_CHALLENGE_TYPE_RE = re.compile(r"cType\s*:\s*['\"]([^'\"]+)['\"]", re.IGNORECASE)
_HTTP_IP_ENDPOINTS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)
_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


@contextmanager
def _no_proxy_browser():
    """Force Chromium-family engines to bypass the Windows system proxy."""
    original_flags = browser_flags.ANTI_DETECT_ARGS
    original_stealth = stealth_browser.ANTI_DETECT_ARGS
    saved_env = {key: os.environ[key] for key in _PROXY_ENV_KEYS if key in os.environ}
    for key in saved_env:
        os.environ.pop(key, None)
    browser_flags.ANTI_DETECT_ARGS = (*original_flags, "--no-proxy-server")
    stealth_browser.ANTI_DETECT_ARGS = (*original_stealth, "--no-proxy-server")
    try:
        yield
    finally:
        browser_flags.ANTI_DETECT_ARGS = original_flags
        stealth_browser.ANTI_DETECT_ARGS = original_stealth
        os.environ.update(saved_env)


def _direct_http_egress_ip(timeout: float = 4.0) -> str | None:
    """Return the HTTP egress IP with proxy environment variables ignored."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for endpoint in _HTTP_IP_ENDPOINTS:
        try:
            request = urllib.request.Request(
                endpoint,
                headers={"User-Agent": "anti-bot-web-scraper/1.0"},
            )
            with opener.open(request, timeout=timeout) as response:
                value = response.read().decode("utf-8", "replace").strip()
            if value:
                return value
        except Exception:
            continue
    return None


def _public_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return False
    return address.version == 4 and address.is_global


def extract_page_ip(html: str) -> str | None:
    """Return a public IPv4 from the demo page, preferring labeled values."""
    if not html:
        return None
    for pattern in _LABELED_IP_RES:
        match = pattern.search(html)
        if match and _public_ipv4(match.group(1)):
            return match.group(1)
    match = _JSON_IP_RE.search(html)
    if match and _public_ipv4(match.group(1)):
        return match.group(1)
    for match in _IPV4_RE.finditer(html):
        if _public_ipv4(match.group()):
            return match.group()
    return None


def _has_clearance(cookies: list[dict[str, Any]] | None) -> bool:
    for cookie in cookies or []:
        if str(cookie.get("name") or "").lower() == "cf_clearance" and cookie.get("value"):
            return True
    return False


def _ip_report() -> dict[str, Any]:
    pool = ProxyPool()
    current_ip = pool.current_ip()
    http_egress_ip = pool._http_egress_ip()
    direct_http_egress_ip = _direct_http_egress_ip()
    return {
        "real_public_ip": current_ip,
        "real_public_ip_source": pool._current_ip_source,
        "http_egress_ip": http_egress_ip,
        "direct_http_egress_ip": direct_http_egress_ip,
        "http_egress_via_proxy": http_egress_ip != direct_http_egress_ip,
        "egress_matches_real": current_ip is not None and current_ip == http_egress_ip,
    }


def probe(
    *,
    engine: str,
    engine_order: list[str] | None,
    headless: bool,
    no_proxy: bool,
    timeout_ms: float,
    max_attempts: int,
    retry_delay: float,
    auto_install: bool,
    browser_path: str | None,
    fingerprint_binding: str | None,
) -> dict[str, Any]:
    started = time.time()
    ip_info = _ip_report()
    if no_proxy:
        with _no_proxy_browser():
            result = solve_cloudflare_with_stealth_browser(
                TARGET,
                engine=engine,
                engine_order=engine_order,
                browser_path=browser_path,
                headless=headless,
                headless_fallback=True,
                timeout_ms=timeout_ms,
                auto_install=auto_install,
                max_attempts=max_attempts,
                retry_delay=retry_delay,
                fingerprint_binding=fingerprint_binding,
            )
    else:
        result = solve_cloudflare_with_stealth_browser(
            TARGET,
            engine=engine,
            engine_order=engine_order,
            browser_path=browser_path,
            headless=headless,
            headless_fallback=True,
            timeout_ms=timeout_ms,
            auto_install=auto_install,
            max_attempts=max_attempts,
            retry_delay=retry_delay,
            fingerprint_binding=fingerprint_binding,
        )
    html = result.html or ""
    state = extract_cloudflare_state(
        html,
        page_url=result.final_url or TARGET,
        cookies=result.cookies,
    )
    has_clearance = _has_clearance(result.cookies)
    pending = _challenge_pending(html)
    page_ip = extract_page_ip(html) if not pending else None
    challenge_type_match = _CHALLENGE_TYPE_RE.search(html)
    challenge_type = challenge_type_match.group(1) if challenge_type_match else None
    passed = bool(html) and not pending and not result.error
    return {
        "target": TARGET,
        "probed_at": started,
        "elapsed_seconds": round(time.time() - started, 2),
        "ip": ip_info,
        "engine": result.engine,
        "force_direct": no_proxy,
        "passed": passed,
        "challenge_pending": pending,
        "challenge_stage": state.stage,
        "challenge_type": challenge_type,
        "sitekey": state.sitekey,
        "frame_url": state.frame_url,
        "cf_clearance": has_clearance,
        "page_ip": page_ip,
        "page_ip_matches_egress": page_ip is not None and page_ip == ip_info["http_egress_ip"],
        "page_ip_matches_real": page_ip is not None and page_ip == ip_info["real_public_ip"],
        "final_url": result.final_url or TARGET,
        "user_agent": result.user_agent,
        "html_length": len(html.encode("utf-8", "replace")),
        "error": result.error,
        "attempts": result.attempts or [],
        "installed_engines": available_stealth_engines(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe real public IP and the nopecha Cloudflare demo."
    )
    parser.add_argument(
        "--engine",
        default="auto",
        choices=[
            "auto",
            "patchright",
            "camoufox",
            "scrapling",
            "nodriver",
            "seleniumbase",
            "undetected_chromedriver",
            "drission_page",
            "selenium",
        ],
    )
    parser.add_argument(
        "--engine-order",
        default=None,
        help="comma-separated engine order, e.g. patchright,camoufox,scrapling,nodriver",
    )
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="force the browser to bypass the system proxy",
    )
    parser.add_argument("--timeout-ms", type=float, default=60000)
    parser.add_argument("--max-attempts", type=int, default=1)
    parser.add_argument("--retry-delay", type=float, default=2.0)
    parser.add_argument("--browser-path", default=None)
    parser.add_argument("--fingerprint-binding", "--profile", default=None)
    parser.add_argument(
        "--auto-install",
        action="store_true",
        help="install a missing stealth engine before running",
    )
    parser.add_argument("--save", help="write the report to a JSON file")
    parser.add_argument("--ip-only", action="store_true", help="only check public IP")
    args = parser.parse_args(argv)

    engine_order = None
    if args.engine_order:
        engine_order = [
            item.strip()
            for item in args.engine_order.split(",")
            if item.strip()
        ]

    if args.ip_only:
        report = {
            "target": TARGET,
            "ip": _ip_report(),
            "installed_engines": available_stealth_engines(),
        }
    else:
        report = probe(
            engine=args.engine,
            engine_order=engine_order,
            headless=args.headless,
            no_proxy=args.no_proxy,
            timeout_ms=args.timeout_ms,
            max_attempts=args.max_attempts,
            retry_delay=args.retry_delay,
            auto_install=args.auto_install,
            browser_path=args.browser_path,
            fingerprint_binding=args.fingerprint_binding,
        )

    if args.save:
        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
