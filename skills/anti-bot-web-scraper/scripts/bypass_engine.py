"""Adaptive challenge bypass orchestrator.

This module turns the anti-bot stack into a strategy loop:

1. Try a fingerprint-aware HTTP fetch first.
2. Classify the response into a Cloudflare stage / WAF / rate limit / CAPTCHA.
3. Pick a browser-engine order for the challenge type and active binding.
4. Solve with the stealth browser while pinning proxy and fingerprint.
5. Merge the solved cookies back into HTTP and verify the real page/API.

It is the high-level entry point used by the acceptance suite and can be
used by desktop automation that wants one call instead of manually wiring
`SmartFetchSession` and `stealth_browser.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from adaptive_policy import AdaptivePolicyStore
from alternate_access import try_alternate_access
from challenge_cookie_bank import ChallengeCookieBank
from challenge_evolution import fingerprint_challenge
from challenge_replay import save_challenge_snapshot
from cloudflare_challenge import extract_cloudflare_state
from fingerprint_binding import (
    FingerprintBinding,
    apply_binding_to_fetch_config,
    resolve_binding,
)
from metrics import MetricsRegistry
from proxy_pool import ProxyPool, create_proxy_pool, normalize_proxy
from security_detector import SecurityReport, detect_security_mechanisms
from smart_fetch import create_fetch_session
from stealth_browser import (
    STEALTH_ENGINES,
    available_stealth_engines,
    solve_cloudflare_with_stealth_browser,
)
from waf_vendor import detect_vendor, recommended_engine_order


@dataclass
class BypassResult:
    """Outcome of one adaptive bypass run."""

    passed: bool = False
    strategy: str = "none"
    status: int | None = None
    final_url: str = ""
    body: str = ""
    error: str | None = None
    engine: str | None = None
    cookies: list[dict[str, Any]] = field(default_factory=list)
    cf_clearance: bool = False
    proxy: str | None = None
    attempts: list[dict[str, Any]] = field(default_factory=list)
    security: dict[str, Any] | None = None
    duration_ms: float = 0.0
    metrics: dict[str, Any] | None = None
    reused_cookies: int = 0
    saved_cookies: int = 0
    challenge: dict[str, Any] | None = None
    snapshot_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "strategy": self.strategy,
            "status": self.status,
            "final_url": self.final_url,
            "body": self.body[:2000],
            "error": self.error,
            "engine": self.engine,
            "cookies": self.cookies,
            "cf_clearance": self.cf_clearance,
            "proxy": self.proxy,
            "attempts": self.attempts,
            "security": self.security,
            "duration_ms": round(self.duration_ms, 3),
            "metrics": self.metrics,
            "reused_cookies": self.reused_cookies,
            "saved_cookies": self.saved_cookies,
            "challenge": self.challenge,
            "snapshot_path": self.snapshot_path,
        }


def choose_engine_order(
    binding: FingerprintBinding | None,
    stage: str | None,
    available: list[str] | None = None,
    configured_order: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Choose a browser-engine order based on challenge stage and binding."""
    installed = set(available or available_stealth_engines())
    if configured_order:
        order = [
            str(item).lower().replace("-", "_")
            for item in configured_order
            if str(item).lower().replace("-", "_") in STEALTH_ENGINES
        ]
        if order:
            return [engine for engine in order if engine in installed] or order

    if stage and "turnstile" in stage:
        if binding is not None and binding.browser_family == "firefox":
            candidates = ["camoufox", "scrapling"]
        else:
            candidates = ["patchright", "nodriver", "drission_page", "seleniumbase"]
    elif binding is not None and binding.compatible_engines:
        candidates = list(binding.compatible_engines)
    else:
        candidates = list(STEALTH_ENGINES)
    return [engine for engine in candidates if engine in installed] or candidates


def _report_to_dict(report: SecurityReport) -> dict[str, Any]:
    return report.to_dict()


def _http_fetch(
    url: str,
    config: dict[str, Any],
    *,
    binding: FingerprintBinding | None,
    proxy: str | None,
    proxy_pool: ProxyPool | None,
    timeout: float,
    initial_cookies: list[dict[str, Any]] | None = None,
) -> tuple[bytes, int, dict[str, str], SecurityReport]:
    fetch = dict(config.get("fetch") or {})
    if binding is not None:
        fetch = apply_binding_to_fetch_config(fetch, binding)
    fetch["browser"] = {}
    fetch.setdefault("auto_install", False)
    session = create_fetch_session(
        fetch,
        proxy=proxy,
        proxy_pool=None if proxy else proxy_pool,
        timeout=timeout,
        min_interval=0.0,
        max_retries=0,
    )
    try:
        if initial_cookies:
            session.load_cookies(initial_cookies)
        body, status, headers = session.get_bytes_with_meta(url)
    finally:
        session.close()
    text = body.decode("utf-8", "replace")
    report = detect_security_mechanisms(
        status,
        url,
        headers,
        text,
        html=text,
        page_url=url,
    )
    return body, status, headers, report


def _verify_with_cookies(
    url: str,
    config: dict[str, Any],
    *,
    binding: FingerprintBinding | None,
    proxy: str | None,
    cookies: list[dict[str, Any]],
    timeout: float,
) -> tuple[bool, bytes, int, dict[str, str], SecurityReport]:
    fetch = dict(config.get("fetch") or {})
    if binding is not None:
        fetch = apply_binding_to_fetch_config(fetch, binding)
    fetch["browser"] = {}
    fetch.setdefault("auto_install", False)
    session = create_fetch_session(
        fetch,
        proxy=proxy,
        proxy_pool=None,
        timeout=timeout,
        min_interval=0.0,
        max_retries=0,
    )
    try:
        session.load_cookies(cookies)
        body, status, headers = session.get_bytes_with_meta(url)
    finally:
        session.close()
    text = body.decode("utf-8", "replace")
    report = detect_security_mechanisms(
        status,
        url,
        headers,
        text,
        html=text,
        page_url=url,
    )
    return (status < 400 and not report.is_blocked), body, status, headers, report


def run_bypass(
    url: str,
    config: dict[str, Any] | None = None,
    *,
    timeout: float = 30.0,
    max_rounds: int = 2,
    progress: Callable[[str, float | None, str], None] | None = None,
) -> BypassResult:
    """Run the adaptive bypass loop and return a structured result."""
    started = time.monotonic()
    cfg = dict(config or {})
    binding = resolve_binding(
        cfg.get("fingerprint_binding")
        or (cfg.get("fetch") or {}).get("fingerprint_binding")
    )
    pool = create_proxy_pool(cfg.get("proxy_pool"))
    pool_cfg = cfg.get("proxy_pool") or {}
    proxy_region = (
        pool_cfg.get("preferred_region")
        or pool_cfg.get("country")
        or pool_cfg.get("region")
        or (pool.pool_status().get("preferred_region") if pool is not None else None)
    )
    cookie_bank_path = cfg.get("cookie_store_path") or cfg.get("cookie_bank_path")
    cookie_bank = (
        ChallengeCookieBank(str(cookie_bank_path))
        if cookie_bank_path
        else None
    )
    bank_cookies = cookie_bank.cookies_for(url) if cookie_bank is not None else []
    policy = AdaptivePolicyStore(
        cfg.get("adaptive_policy_path")
        or (cfg.get("adaptive") or {}).get("policy_path")
    )
    metrics = MetricsRegistry()
    explicit_proxy = cfg.get("proxy")
    proxy = normalize_proxy(explicit_proxy or (pool.get_proxy() if pool is not None else None))
    browser_pool = None if explicit_proxy else pool
    captcha_solver = cfg.get("captcha_solver")
    result = BypassResult(proxy=proxy, reused_cookies=len(bank_cookies))
    metrics.inc("task_total")
    if pool is not None:
        metrics.set("proxy_available", len(pool.healthy_proxies()))

    if progress is not None:
        progress("http", 0.1, "fingerprint-aware HTTP fetch")
    try:
        body, status, headers, report = _http_fetch(
            url,
            cfg,
            binding=binding,
            proxy=proxy,
            proxy_pool=browser_pool,
            timeout=timeout,
            initial_cookies=bank_cookies,
        )
    except Exception as exc:
        result.error = f"http fetch failed: {exc}"
        result.duration_ms = (time.monotonic() - started) * 1000
        metrics.inc("task_failed")
        result.metrics = metrics.snapshot()
        return result
    result.status = status
    result.security = _report_to_dict(report)
    if status < 400 and not report.is_blocked:
        result.passed = True
        result.strategy = "http:cookie_bank" if bank_cookies else "http"
        result.body = body.decode("utf-8", "replace")
        result.final_url = url
        result.duration_ms = (time.monotonic() - started) * 1000
        metrics.inc("task_success")
        metrics.observe("bypass_duration_ms", result.duration_ms)
        result.metrics = metrics.snapshot()
        return result

    body_text = body.decode("utf-8", "replace")
    alt_cfg = cfg.get("alternate")
    if alt_cfg is None or alt_cfg.get("enabled", True):
        if progress is not None:
            progress("alternate", 0.15, "alternate endpoint probe")
        alt_config = alt_cfg if isinstance(alt_cfg, dict) else {}
        alt_result = try_alternate_access(
            url,
            cfg,
            proxy=proxy,
            timeout=float(
                alt_config.get(
                    "timeout",
                    min(5.0, max(1.5, timeout / 3)),
                )
            ),
            max_variants=int(alt_config.get("max_variants", 8)),
        )
        result.attempts.extend(alt_result.attempts)
        if alt_result.passed:
            result.passed = True
            result.strategy = alt_result.strategy
            result.status = alt_result.status
            result.body = alt_result.body
            result.final_url = alt_result.url
            result.security = alt_result.security
            result.error = None
            result.duration_ms = (time.monotonic() - started) * 1000
            metrics.inc("task_success")
            metrics.observe("bypass_duration_ms", result.duration_ms)
            result.metrics = metrics.snapshot()
            return result

    vendor = detect_vendor(status, headers, body_text)
    challenge_variant = fingerprint_challenge(
        vendor=vendor.vendor,
        stage=vendor.challenge_stage,
        html=body_text,
        headers=headers,
        cookies=result.cookies or bank_cookies,
    )
    result.challenge = challenge_variant.to_dict()
    metrics.inc("variant_total")
    if vendor.detected and vendor.vendor != "cloudflare" and vendor.recommended_impersonate:
        fetch_cfg = cfg.get("fetch") or {}
        if not fetch_cfg.get("impersonate") and not fetch_cfg.get("fingerprint_binding"):
            cfg["fetch"] = {**fetch_cfg, "impersonate": vendor.recommended_impersonate}
            if progress is not None:
                progress("http", 0.25, f"vendor TLS retry for {vendor.vendor}")
            try:
                body, status, headers, report = _http_fetch(
                    url,
                    cfg,
                    binding=binding,
                    proxy=proxy,
                    proxy_pool=browser_pool,
                    timeout=timeout,
                    initial_cookies=bank_cookies,
                )
                body_text = body.decode("utf-8", "replace")
                result.status = status
                result.security = _report_to_dict(report)
                if status < 400 and not report.is_blocked:
                    result.passed = True
                    result.strategy = f"http:vendor_tls:{vendor.vendor}"
                    result.body = body.decode("utf-8", "replace")
                    result.final_url = url
                    result.error = None
                    result.duration_ms = (time.monotonic() - started) * 1000
                    metrics.inc("task_success")
                    metrics.observe("bypass_duration_ms", result.duration_ms)
                    result.metrics = metrics.snapshot()
                    return result
            except Exception:
                pass

    cloudflare_state = extract_cloudflare_state(
        body_text,
        page_url=url,
        headers=headers,
    )
    stage = cloudflare_state.stage
    host = urlsplit(url).netloc.lower()
    browser_config = dict(cfg.get("browser") or {})
    engine_order = choose_engine_order(
        binding,
        stage,
        configured_order=browser_config.get("stealth_engine_order")
        or browser_config.get("engine_order"),
    )
    if vendor.detected and vendor.vendor != "cloudflare":
        vendor_engines = recommended_engine_order(
            vendor.vendor,
            available_stealth_engines(),
        )
        if vendor_engines:
            engine_order = vendor_engines
    if policy is not None:
        known = policy.known_signatures(host, vendor=vendor.vendor)
        if (
            challenge_variant.signature
            and challenge_variant.signature not in known
        ):
            metrics.inc(
                "variant_new",
                {"vendor": vendor.vendor, "signature": challenge_variant.signature},
            )
            if progress is not None:
                progress(
                    "variant",
                    0.3,
                    f"new {vendor.vendor} challenge variant {challenge_variant.signature}",
                )
        engine_order = [
            engine
            for engine in engine_order
            if not policy.should_skip(
                host,
                stage,
                engine,
                vendor=vendor.vendor,
                signature=challenge_variant.signature or None,
                proxy_region=proxy_region,
            )
        ] or engine_order
        engine_order = policy.recommend(
            host,
            stage,
            engine_order,
            vendor=vendor.vendor,
            signature=challenge_variant.signature or None,
            proxy_region=proxy_region,
        )
    rounds = max(1, int(max_rounds))
    last_error: str | None = None
    for round_no in range(rounds):
        if progress is not None:
            progress(
                "browser",
                (round_no + 1) / rounds,
                f"stealth browser round {round_no + 1}",
            )
        browser_result = solve_cloudflare_with_stealth_browser(
            url,
            engine="auto",
            engine_order=engine_order,
            proxy=proxy,
            proxy_pool=pool,
            browser_path=browser_config.get("browser_path"),
            headless=bool(browser_config.get("headless", True)),
            headless_fallback=bool(browser_config.get("headless_fallback", True)),
            storage_state=browser_config.get("storage_state"),
            timeout_ms=float(
                browser_config.get(
                    "challenge_timeout",
                    browser_config.get("timeout_ms", timeout * 1000),
                )
            ),
            auto_install=bool(browser_config.get("auto_install", False)),
            max_attempts=int(browser_config.get("max_attempts", 2)),
            retry_delay=float(browser_config.get("retry_delay", 2.0)),
            rotate_proxy_on_fail=bool(
                browser_config.get("rotate_proxy_on_fail", True)
            ),
            fingerprint_binding=binding,
            captcha_solver=captcha_solver,
            progress=progress,
        )
        result.attempts.extend(browser_result.attempts or [])
        result.engine = browser_result.engine
        result.proxy = browser_result.proxy or proxy
        result.cookies = browser_result.cookies or []
        result.cf_clearance = any(
            str(item.get("name", "")).lower() == "cf_clearance"
            for item in result.cookies
        )
        last_error = browser_result.error

        if progress is not None:
            progress("verify", (round_no + 1) / rounds, "HTTP verification")
        try:
            verified, body2, status2, _headers2, report2 = _verify_with_cookies(
                url,
                cfg,
                binding=binding,
                proxy=result.proxy,
                cookies=result.cookies,
                timeout=timeout,
            )
        except Exception as exc:
            verified = False
            body2 = b""
            status2 = None
            report2 = None
            last_error = str(exc)
        if verified:
            result.passed = True
            result.strategy = f"browser:{browser_result.engine}"
            result.status = status2
            result.body = body2.decode("utf-8", "replace")
            result.final_url = browser_result.final_url or url
            result.security = _report_to_dict(report2) if report2 is not None else None
            result.error = None
            if cookie_bank is not None:
                result.saved_cookies = cookie_bank.save(url, result.cookies)
            result.duration_ms = (time.monotonic() - started) * 1000
            metrics.inc("task_success")
            metrics.observe("bypass_duration_ms", result.duration_ms)
            result.metrics = metrics.snapshot()
            if policy is not None:
                policy.record_variant(
                    host=host,
                    vendor=vendor.vendor,
                    signature=challenge_variant.signature,
                    stage=stage,
                    engine=browser_result.engine or "browser",
                    success=True,
                    duration_ms=result.duration_ms,
                    attempts=len(result.attempts),
                    proxy_region=proxy_region,
                )
            return result

        if browser_pool is not None and result.proxy:
            browser_pool.report_failure(result.proxy)
            proxy = normalize_proxy(browser_pool.get_proxy())
        elif report.needs_proxy:
            break

    result.error = last_error or "bypass did not clear the challenge"
    result.duration_ms = (time.monotonic() - started) * 1000
    metrics.inc("task_failed")
    metrics.observe("bypass_duration_ms", result.duration_ms)
    result.metrics = metrics.snapshot()
    snapshot_path = save_challenge_snapshot(
        url,
        variant=challenge_variant,
        html=body_text,
        headers=headers,
        cookies=result.cookies or bank_cookies,
        status=result.status,
        snapshot_dir=cfg.get("snapshot_dir")
        or (cfg.get("adaptive") or {}).get("snapshot_dir")
        or "reports/challenges",
        extra={"error": result.error, "strategy": result.strategy},
    )
    if snapshot_path is not None:
        result.snapshot_path = str(snapshot_path)
    if policy is not None:
        policy.record_variant(
            host=host,
            vendor=vendor.vendor,
            signature=challenge_variant.signature,
            stage=stage,
            engine=result.engine or "browser",
            success=False,
            duration_ms=result.duration_ms,
            attempts=len(result.attempts),
            error=result.error,
            proxy_region=proxy_region,
        )
    return result


def _self_test() -> int:
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            body = b"<html><body>bypass-ok</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/"
        result = run_bypass(url, {"fetch": {"backend": "standard"}})
        assert result.passed, result.to_dict()
        print("bypass_engine self-test OK")
        return 0
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Run one adaptive bypass attempt")
    parser.add_argument("--url", default=None)
    parser.add_argument("--config", help="JSON bypass config")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.url:
        parser.error("--url is required unless --self-test is used")
    config = (
        json.loads(Path(args.config).read_text(encoding="utf-8"))
        if args.config
        else {}
    )
    result = run_bypass(
        args.url,
        config,
        timeout=args.timeout,
        max_rounds=args.rounds,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
