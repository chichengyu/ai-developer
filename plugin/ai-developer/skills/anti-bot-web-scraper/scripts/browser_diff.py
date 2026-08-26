"""Dual-browser DOM/JS diff for locating injected anti-bot code.

Comparing a clean browser against a protected browser on the same URL makes
injected scripts, global functions, storage keys, and network calls stand
out.  The diff is the starting point for focusing reverse engineering on the
code the target site actually added.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any


def snapshot_page(session: Any) -> dict[str, Any]:
    """Collect a lightweight page snapshot from a browser session."""
    if session is None or session.page is None:
        return {"ok": False, "error": "browser page is not open"}
    html = ""
    global_functions: list[str] = []
    storage: dict[str, dict[str, str]] = {}
    cookies = ""
    with suppress(Exception):
        html = session.page.content()
    with suppress(Exception):
        global_functions = session.page.evaluate(
            "Object.keys(window).filter(function(k){return typeof window[k]==='function';})"
        ) or []
    with suppress(Exception):
        storage = session.page.evaluate(
            """
            (function(){
              var out={local:{},session:{}};
              for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i);out.local[k]=localStorage.getItem(k);}
              for(var j=0;j<sessionStorage.length;j++){var k2=sessionStorage.key(j);out.session[k2]=sessionStorage.getItem(k2);}
              return out;
            })()
            """
        ) or {}
    with suppress(Exception):
        cookies = session.page.evaluate("document.cookie") or ""
    return {
        "ok": True,
        "html": html,
        "global_functions": [str(item) for item in (global_functions or [])],
        "storage": storage,
        "cookies": str(cookies or ""),
        "scripts": _extract_script_urls(html),
    }


def diff_snapshots(
    baseline: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any]:
    """Diff two page snapshots and return injected/removed artifacts."""
    baseline_scripts = set(baseline.get("scripts", []) or [])
    target_scripts = set(target.get("scripts", []) or [])
    baseline_functions = set(baseline.get("global_functions", []) or [])
    target_functions = set(target.get("global_functions", []) or [])
    baseline_storage = _storage_keys(baseline.get("storage") or {})
    target_storage = _storage_keys(target.get("storage") or {})
    baseline_html = str(baseline.get("html", "") or "")
    target_html = str(target.get("html", "") or "")
    ratio = difflib.SequenceMatcher(None, baseline_html, target_html).ratio()
    return {
        "ok": True,
        "added_scripts": sorted(target_scripts - baseline_scripts),
        "removed_scripts": sorted(baseline_scripts - target_scripts),
        "added_functions": sorted(target_functions - baseline_functions),
        "removed_functions": sorted(baseline_functions - target_functions),
        "added_storage": sorted(target_storage - baseline_storage),
        "removed_storage": sorted(baseline_storage - target_storage),
        "html_similarity": round(ratio, 4),
        "summary": {
            "added_scripts": len(target_scripts - baseline_scripts),
            "added_functions": len(target_functions - baseline_functions),
            "added_storage": len(target_storage - baseline_storage),
        },
    }


def find_injected_scripts(
    baseline: dict[str, Any],
    target: dict[str, Any],
) -> list[str]:
    """Return script URLs present in target but not baseline."""
    return diff_snapshots(baseline, target)["added_scripts"]


def run_browser_dom_diff(
    baseline_url: str,
    target_url: str,
    *,
    headless: bool = True,
    engine: str = "playwright",
    wait_ms: float = 5000,
) -> dict[str, Any]:
    """Snapshot two URLs and return their injected/removed artifact diff."""
    try:
        from browser_session import BrowserSession
    except Exception as exc:
        return {"ok": False, "error": f"browser dependencies unavailable: {exc}"}
    baseline_session = BrowserSession(headless=headless, engine=engine, auto_install=False)
    target_session = BrowserSession(headless=headless, engine=engine, auto_install=False)
    try:
        baseline_session.start()
        baseline_session.goto(baseline_url, wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
        with_baseline = snapshot_page(baseline_session)
        target_session.start()
        target_session.goto(target_url, wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
        with_target = snapshot_page(target_session)
        return diff_snapshots(with_baseline, with_target)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        baseline_session.close()
        target_session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dual-browser DOM/JS diff")
    parser.add_argument("--baseline-url", default=None)
    parser.add_argument("--target-url", default=None)
    parser.add_argument("--engine", default="playwright")
    parser.add_argument("--headless", action="store_true", default=True)
    parser.add_argument("--no-headless", action="store_true")
    parser.add_argument("--wait-ms", type=float, default=5000)
    parser.add_argument("--output", default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.baseline_url or not args.target_url:
        parser.error("--baseline-url and --target-url are required")
    report = run_browser_dom_diff(
        args.baseline_url,
        args.target_url,
        headless=not args.no_headless,
        engine=args.engine,
        wait_ms=args.wait_ms,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if report.get("ok") else 2

def _extract_script_urls(html: str) -> list[str]:
    import re

    return re.findall(r"""<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""", html, re.I)


def _storage_keys(storage: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for bucket in storage.values() if isinstance(storage, dict) else []:
        if isinstance(bucket, dict):
            keys.update(str(key) for key in bucket)
    return keys


def _self_test() -> None:
    baseline = {
        "html": '<script src="app.js"></script>',
        "scripts": ["app.js"],
        "global_functions": ["fetch"],
        "storage": {"local": {"a": "1"}},
    }
    target = {
        "html": '<script src="app.js"></script><script src="sensor.js"></script>',
        "scripts": ["app.js", "sensor.js"],
        "global_functions": ["fetch", "genSign"],
        "storage": {"local": {"a": "1", "fp": "x"}},
    }
    report = diff_snapshots(baseline, target)
    assert "sensor.js" in report["added_scripts"]
    assert "genSign" in report["added_functions"]
    assert "fp" in report["added_storage"]
    print("browser_diff self-test OK")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

if __name__ == "__main__":
    _self_test()
