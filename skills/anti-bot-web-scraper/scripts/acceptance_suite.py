"""Real-site acceptance suite for the anti-bot web scraping skill.

The existing tests are protocol-level and run against local HTTP servers.
This runner provides a repeatable baseline for real Cloudflare, Turnstile,
CAPTCHA provider, and residential proxy targets. It never guarantees a
bypass; it records pass/fail/skip evidence so the pipeline can be tuned
against the user's actual targets.

Example config:

    {
      "fingerprint_binding": "chrome126",
      "fetch": {"backend": "auto", "auto_install": false},
      "browser": {"engine": "auto", "headless": true},
      "captcha": {"provider": "capsolver", "api_key_env": "CAPSOLVER_API_KEY"},
      "proxy_pool": {"source": {"url": "https://provider.example/list"}},
      "targets": [
        {
          "name": "cloudflare-basic",
          "url": "https://example.com/",
          "kind": "page",
          "expected_status": [200],
          "expected_marker": "Example Domain",
          "checks": ["http", "browser"]
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bypass_engine import run_bypass  # noqa: E402
from challenge_evolution import ChallengeVariant  # noqa: E402
from challenge_replay import save_challenge_snapshot  # noqa: E402
from fingerprint_binding import (  # noqa: E402
    available_bindings,
    binding_report,
    resolve_binding,
)
from proxy_pool import create_proxy_pool  # noqa: E402
from security_detector import detect_security_mechanisms  # noqa: E402
from smart_fetch import backend_status, create_fetch_session  # noqa: E402
from stealth_browser import (  # noqa: E402
    _challenge_pending,
    available_stealth_engines,
    preflight_stealth_engines,
    solve_cloudflare_with_stealth_browser,
)


@dataclass
class AcceptanceTarget:
    name: str
    url: str
    kind: str = "page"
    expected_status: tuple[int, ...] = (200,)
    expected_marker: str | None = None
    checks: tuple[str, ...] = ("http",)
    skip_without: tuple[str, ...] = ()
    timeout: float = 30.0
    sitekey: str | None = None
    max_attempts: int = 2

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AcceptanceTarget:
        expected = data.get("expected_status", 200)
        statuses = (expected,) if isinstance(expected, int) else tuple(expected or (200,))
        return cls(
            name=str(data.get("name") or data.get("url") or "target"),
            url=str(data.get("url") or ""),
            kind=str(data.get("kind") or "page").lower(),
            expected_status=tuple(int(item) for item in statuses),
            expected_marker=data.get("expected_marker"),
            checks=tuple(data.get("checks") or ("http",)),
            skip_without=tuple(data.get("skip_without") or ()),
            timeout=float(data.get("timeout") or 30.0),
            sitekey=data.get("sitekey"),
            max_attempts=int(data.get("max_attempts") or 2),
        )


@dataclass
class TargetResult:
    name: str
    url: str
    status: str
    duration_ms: float = 0.0
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 3),
            "error": self.error,
            "details": self.details,
        }


def _captcha_solver(config: dict[str, Any] | None) -> Any | None:
    captcha = dict(config or {})
    provider = str(captcha.get("provider") or "2captcha").lower()
    env_key = str(captcha.get("api_key_env") or "CAPTCHA_API_KEY")
    api_key = os.environ.get(env_key) or captcha.get("api_key")
    if not api_key:
        return None
    if provider in {"capsolver", "capsolver_solver"}:
        from captcha_solver import CapSolverSolver

        return CapSolverSolver(api_key)
    if provider in {"anticaptcha", "anti-captcha"}:
        from captcha_solver import AntiCaptchaSolver

        return AntiCaptchaSolver(api_key)
    from captcha_solver import CaptchaSolver

    return CaptchaSolver(api_key, base_url=str(captcha.get("base_url") or "https://2captcha.com"))


def _captcha_balance(solver: Any | None) -> dict[str, Any]:
    if solver is None:
        return {"configured": False}
    result: dict[str, Any] = {"configured": True}
    get_balance = getattr(solver, "get_balance", None)
    if get_balance is None:
        result["balance"] = None
        result["note"] = "provider adapter has no balance method"
        return result
    try:
        result["balance"] = get_balance()
    except Exception as exc:
        result["balance_error"] = str(exc)
    return result


def _skip_reason(target: AcceptanceTarget, ctx: dict[str, Any]) -> str | None:
    for requirement in target.skip_without:
        key = str(requirement).lower()
        if key in {"network", "live"} and ctx.get("offline"):
            return "offline mode"
        if key in {"browser", "browser_engine"} and not ctx.get("stealth_engines"):
            return "no stealth browser engine installed"
        if key == "captcha" and ctx.get("captcha_solver") is None:
            return "captcha API key not configured"
        if key == "proxy" and (
            ctx.get("proxy_pool") is None
            or not ctx["proxy_pool"].healthy_proxies()
        ):
            return "proxy pool not configured or empty"
        if key == "proxy_pool" and (
            ctx.get("proxy_pool") is None
            or not getattr(ctx["proxy_pool"], "total", 0)
        ):
            return "proxy pool not configured or empty"
        if key in {"binding", "fingerprint"} and ctx.get("binding") is None:
            return "fingerprint binding not configured"
    return None


def _target_proxy(ctx: dict[str, Any]) -> str | None:
    pool = ctx.get("proxy_pool")
    if pool is not None:
        return pool.get_proxy()
    return None


def _run_target(target: AcceptanceTarget, ctx: dict[str, Any]) -> TargetResult:
    started = time.monotonic()
    reason = _skip_reason(target, ctx)
    if reason is not None:
        return TargetResult(
            name=target.name,
            url=target.url,
            status="skipped",
            duration_ms=(time.monotonic() - started) * 1000,
            error=reason,
        )
    if ctx.get("dry_run"):
        return TargetResult(
            name=target.name,
            url=target.url,
            status="planned",
            duration_ms=0.0,
            details={"binding": ctx.get("binding_name")},
        )

    details: dict[str, Any] = {}
    error: str | None = None
    passed = False
    try:
        if target.kind == "captcha" and ctx.get("captcha_solver") is None:
            return TargetResult(
                name=target.name,
                url=target.url,
                status="skipped",
                duration_ms=(time.monotonic() - started) * 1000,
                error="captcha API key not configured",
            )
        if target.kind == "cloudflare" or "bypass" in target.checks:
            passed, error, details = _run_bypass_target(target, ctx, details)
        elif "browser" in target.checks:
            passed, error, details = _run_browser_target(target, ctx, details)
        elif target.kind == "api":
            passed, error, details = _run_api_target(target, ctx, details)
        elif target.kind == "captcha":
            passed, error, details = _run_captcha_target(target, ctx, details)
        else:
            passed, error, details = _run_page_target(target, ctx, details)
    except Exception as exc:
        error = str(exc)
        details["exception"] = error
        passed = False
    return TargetResult(
        name=target.name,
        url=target.url,
        status="pass" if passed else "fail",
        duration_ms=(time.monotonic() - started) * 1000,
        error=error,
        details=details,
    )


def _run_page_target(
    target: AcceptanceTarget,
    ctx: dict[str, Any],
    details: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    proxy = _target_proxy(ctx)
    session = _new_session(target, ctx, proxy)
    try:
        body, status, headers = session.get_bytes_with_meta(
            target.url,
            timeout=target.timeout,
        )
    finally:
        session.close()
    text = body.decode("utf-8", "replace")
    report = detect_security_mechanisms(
        status,
        target.url,
        headers,
        text,
        html=text,
        page_url=target.url,
    )
    details.update(
        {
            "status": status,
            "security": report.primary_kind,
            "blocked": report.is_blocked,
            "bytes": len(body),
            "backend": getattr(session, "backend_mode", "standard"),
            "proxy": proxy,
        }
    )
    if report.is_blocked and ctx.get("snapshot_dir"):
        variant = ChallengeVariant(
            vendor=report.primary_kind or "generic",
            stage=report.primary_kind or "unknown",
            markers=[item.kind for item in report.findings],
        )
        snapshot_path = save_challenge_snapshot(
            target.url,
            variant=variant,
            html=text,
            headers=headers,
            status=status,
            snapshot_dir=ctx["snapshot_dir"],
            extra={"target": target.name},
        )
        if snapshot_path is not None:
            details["snapshot_path"] = str(snapshot_path)
    errors: list[str] = []
    if status not in target.expected_status:
        errors.append(f"status {status} not in {list(target.expected_status)}")
    if target.expected_marker and target.expected_marker not in text:
        errors.append(f"marker {target.expected_marker!r} not found")
    if report.is_blocked:
        errors.append(f"blocked as {report.primary_kind}")
    return not errors, "; ".join(errors) or None, details


def _run_api_target(
    target: AcceptanceTarget,
    ctx: dict[str, Any],
    details: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    proxy = _target_proxy(ctx)
    session = _new_session(target, ctx, proxy)
    try:
        data, status, headers = session.request_json_with_meta(
            "GET",
            target.url,
            timeout=target.timeout,
        )
    finally:
        session.close()
    text = json.dumps(data, ensure_ascii=False, default=str) if not isinstance(data, str) else data
    details.update(
        {
            "status": status,
            "content_type": headers.get("Content-Type"),
            "bytes": len(text.encode("utf-8")),
            "proxy": proxy,
        }
    )
    errors: list[str] = []
    if status not in target.expected_status:
        errors.append(f"status {status} not in {list(target.expected_status)}")
    if target.expected_marker and target.expected_marker not in text:
        errors.append(f"marker {target.expected_marker!r} not found")
    return not errors, "; ".join(errors) or None, details


def _run_browser_target(
    target: AcceptanceTarget,
    ctx: dict[str, Any],
    details: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    browser = ctx.get("browser_config") or {}
    result = solve_cloudflare_with_stealth_browser(
        target.url,
        engine=str(browser.get("engine") or "auto"),
        engine_order=browser.get("stealth_engine_order"),
        proxy=_target_proxy(ctx),
        browser_path=browser.get("browser_path"),
        headless=bool(browser.get("headless", True)),
        headless_fallback=bool(browser.get("headless_fallback", True)),
        storage_state=browser.get("storage_state"),
        timeout_ms=float(browser.get("challenge_timeout", target.timeout * 1000)),
        auto_install=bool(browser.get("auto_install", False)),
        max_attempts=target.max_attempts,
        retry_delay=float(browser.get("retry_delay", 2.0)),
        rotate_proxy_on_fail=bool(browser.get("rotate_proxy_on_fail", True)),
        fingerprint_binding=ctx.get("binding"),
    )
    text = result.html or ""
    details.update(
        {
            "status": result.status,
            "engine": result.engine,
            "user_agent": result.user_agent,
            "cookies": len(result.cookies or []),
            "html_bytes": len(text.encode("utf-8")),
            "error": result.error,
            "attempts": result.attempts or [],
        }
    )
    errors: list[str] = []
    if result.status not in target.expected_status:
        errors.append(f"status {result.status} not in {list(target.expected_status)}")
    if target.expected_marker and target.expected_marker not in text:
        errors.append(f"marker {target.expected_marker!r} not found")
    if not text:
        errors.append("browser returned empty HTML")
    if _challenge_pending(text):
        errors.append("challenge page still present")
    if result.error:
        errors.append(result.error)
    return not errors, "; ".join(errors) or None, details


def _run_bypass_target(
    target: AcceptanceTarget,
    ctx: dict[str, Any],
    details: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    config = {
        "fingerprint_binding": ctx.get("binding"),
        "fetch": ctx.get("fetch_config"),
        "browser": ctx.get("browser_config"),
        "proxy_pool": ctx.get("proxy_pool"),
        "proxy": _target_proxy(ctx),
        "captcha_solver": ctx.get("captcha_solver"),
    }
    result = run_bypass(
        target.url,
        config,
        timeout=target.timeout,
        max_rounds=target.max_attempts,
    )
    details.update(result.to_dict())
    if not result.passed and result.challenge and ctx.get("snapshot_dir"):
        variant = ChallengeVariant.from_dict(result.challenge)
        snapshot_path = save_challenge_snapshot(
            target.url,
            variant=variant,
            html=result.body,
            cookies=result.cookies,
            status=result.status,
            snapshot_dir=ctx["snapshot_dir"],
            extra={"target": target.name, "error": result.error},
        )
        if snapshot_path is not None:
            details["snapshot_path"] = str(snapshot_path)
    errors: list[str] = []
    if not result.passed:
        errors.append(result.error or "bypass did not clear the challenge")
    if target.expected_marker and target.expected_marker not in result.body:
        errors.append(f"marker {target.expected_marker!r} not found")
    if result.status is not None and result.status not in target.expected_status:
        errors.append(f"status {result.status} not in {list(target.expected_status)}")
    return not errors, "; ".join(errors) or None, details


def _run_captcha_target(
    target: AcceptanceTarget,
    ctx: dict[str, Any],
    details: dict[str, Any],
) -> tuple[bool, str | None, dict[str, Any]]:
    solver = ctx.get("captcha_solver")
    if solver is None:
        return False, "captcha solver not configured", details
    if not target.sitekey:
        return False, "captcha target requires sitekey", details
    balance = _captcha_balance(solver)
    details["balance"] = balance
    result = solver.solve_turnstile(target.sitekey, target.url)
    details.update(
        {
            "task_id": result.task_id,
            "success": result.success,
            "has_answer": bool(result.answer),
        }
    )
    return bool(result.success and result.answer), None, details


def _new_session(target: AcceptanceTarget, ctx: dict[str, Any], proxy: str | None) -> Any:
    fetch = dict(ctx.get("fetch_config") or {})
    fetch.setdefault("auto_install", False)
    return create_fetch_session(
        fetch,
        proxy=proxy,
        proxy_pool=ctx.get("proxy_pool"),
        timeout=target.timeout,
        min_interval=0.0,
        max_retries=0,
    )


def run_acceptance(
    config: dict[str, Any],
    *,
    offline: bool = False,
    dry_run: bool = False,
    only: set[str] | None = None,
) -> dict[str, Any]:
    binding = resolve_binding(
        config.get("fingerprint_binding")
        or (config.get("fetch") or {}).get("fingerprint_binding")
    )
    pool = create_proxy_pool(config.get("proxy_pool"))
    captcha_solver = _captcha_solver(config.get("captcha"))
    ctx: dict[str, Any] = {
        "offline": offline,
        "dry_run": dry_run,
        "binding": binding,
        "binding_name": binding.name if binding is not None else None,
        "proxy_pool": pool,
        "captcha_solver": captcha_solver,
        "fetch_config": config.get("fetch") or {},
        "browser_config": config.get("browser") or {},
        "stealth_engines": available_stealth_engines(),
        "snapshot_dir": config.get("snapshot_dir") or "reports/challenges",
    }
    targets = [
        AcceptanceTarget.from_dict(item)
        for item in config.get("targets") or []
        if isinstance(item, dict) and item.get("url")
    ]
    if only:
        targets = [target for target in targets if target.name in only]
    results = [_run_target(target, ctx) for target in targets]
    counts = {"pass": 0, "fail": 0, "skipped": 0, "error": 0, "planned": 0}
    for item in results:
        counts[item.status] = counts.get(item.status, 0) + 1
    total = len(results)
    return {
        "generated_at": time.time(),
        "offline": offline,
        "dry_run": dry_run,
        "counts": counts,
        "success_rate": round(counts["pass"] / total, 4) if total else 0.0,
        "environment": {
            "backends": backend_status(),
            "stealth_engines": ctx["stealth_engines"],
            "stealth_preflight": preflight_stealth_engines(),
            "bindings": available_bindings(),
            "fingerprint_binding": (
                binding_report(binding) if binding is not None else None
            ),
            "captcha": _captcha_balance(captcha_solver),
            "proxy_pool": pool.pool_status() if pool is not None else None,
        },
        "results": [item.to_dict() for item in results],
    }


class _LocalHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/api":
            body = json.dumps({"ok": True, "items": [1, 2]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = b"<html><head><title>Acceptance Local</title></head><body>acceptance-ok</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


def _self_test() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _LocalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        config = {
            "fetch": {"backend": "standard", "auto_install": False},
            "targets": [
                {
                    "name": "local-page",
                    "url": f"{base}/",
                    "expected_status": 200,
                    "expected_marker": "acceptance-ok",
                },
                {
                    "name": "local-api",
                    "url": f"{base}/api",
                    "kind": "api",
                    "expected_status": 200,
                    "expected_marker": "items",
                },
            ],
        }
        report = run_acceptance(config)
        assert report["counts"]["pass"] == 2, report
        print("acceptance_suite self-test OK")
        return 0
    finally:
        server.shutdown()
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run real-site acceptance baselines")
    parser.add_argument("--config", help="JSON acceptance config")
    parser.add_argument("--report", help="write the full report to JSON")
    parser.add_argument("--only", help="comma-separated target names")
    parser.add_argument("--offline", action="store_true", help="skip live-network targets")
    parser.add_argument("--dry-run", action="store_true", help="validate config without requests")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    if not args.config:
        parser.error("--config is required unless --self-test is used")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    only = {item.strip() for item in args.only.split(",") if item.strip()} if args.only else None
    report = run_acceptance(
        config,
        offline=args.offline,
        dry_run=args.dry_run,
        only=only,
    )
    from run_summary import _path_info, final_report, print_report, write_report

    full_report = final_report(
        save_paths=[_path_info(args.report, "acceptance_report")] if args.report else [],
        resources=[],
        summary=report,
    )
    if args.report:
        out = Path(args.report)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_report(full_report, out)
    print_report(full_report)
    return 1 if report["counts"].get("fail", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
