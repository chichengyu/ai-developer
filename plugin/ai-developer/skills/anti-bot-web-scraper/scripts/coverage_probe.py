"""Dynamic coverage-guided candidate filtering.

Static analysis produces a large candidate set.  This module uses Chrome
DevTools Protocol precise coverage to keep only functions/lines that actually
execute during a real page load, then filters signature candidates by those
covered lines.
"""

from __future__ import annotations

import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CoverageCapture:
    ok: bool = False
    error: str | None = None
    scripts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "scripts": self.scripts,
            "summary": {
                "scripts": len(self.scripts),
                "covered_functions": sum(
                    len(script.get("functions", []) or []) for script in self.scripts
                ),
            },
        }


def run_cdp_coverage_probe(
    session: Any,
    *,
    reload: bool = True,
    wait_ms: float = 5000,
) -> CoverageCapture:
    """Start precise coverage, reload, and collect executed ranges."""
    if session is None or session.context is None or session.page is None:
        return CoverageCapture(ok=False, error="browser session is not open")
    try:
        cdp = session.context.new_cdp_session(session.page)
        cdp.send("Profiler.enable")
        cdp.send("Profiler.startPreciseCoverage", {"callCount": True, "detailed": True})
        if reload:
            session.page.reload(wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
            with suppress(Exception):
                session.page.wait_for_load_state("networkidle", timeout=wait_ms)
        else:
            time.sleep(wait_ms / 1000.0)
        result = cdp.send("Profiler.takePreciseCoverage")
        scripts: list[dict[str, Any]] = []
        for script in result.get("result", []) or []:
            functions = []
            for function in script.get("functions", []) or []:
                call_count = sum(
                    int(item.get("count", 0) or 0)
                    for item in function.get("ranges", []) or []
                )
                if call_count <= 0:
                    continue
                functions.append(
                    {
                        "functionName": str(function.get("functionName", "") or ""),
                        "callCount": call_count,
                        "ranges": [
                            {
                                "startOffset": int(item.get("startOffset", 0) or 0),
                                "endOffset": int(item.get("endOffset", 0) or 0),
                                "count": int(item.get("count", 0) or 0),
                            }
                            for item in function.get("ranges", []) or []
                        ],
                    }
                )
            if functions:
                scripts.append(
                    {
                        "url": str(script.get("url", "") or ""),
                        "scriptId": str(script.get("scriptId", "") or ""),
                        "functions": functions,
                    }
                )
        return CoverageCapture(ok=True, scripts=scripts)
    except Exception as exc:
        return CoverageCapture(ok=False, error=str(exc))


def run_url_coverage_probe(
    url: str,
    *,
    headless: bool = True,
    engine: str = "playwright",
    wait_ms: float = 5000,
) -> CoverageCapture:
    """Open a URL and run precise coverage with a browser reload."""
    try:
        from browser_session import BrowserSession
    except Exception as exc:
        return CoverageCapture(ok=False, error=f"browser dependencies unavailable: {exc}")
    session = BrowserSession(headless=headless, engine=engine, auto_install=False)
    try:
        session.start()
        session.goto(url, wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
        return run_cdp_coverage_probe(session, reload=True, wait_ms=wait_ms)
    except Exception as exc:
        return CoverageCapture(ok=False, error=str(exc))
    finally:
        session.close()


def filter_candidates_by_coverage(
    analysis: Any,
    coverage: CoverageCapture | dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep signature candidates whose line appears in executed coverage."""
    scripts = coverage.get("scripts") if isinstance(coverage, dict) else coverage.scripts
    covered_lines: set[tuple[str, int]] = set()
    covered_functions: set[str] = set()
    for script in scripts or []:
        url = str(script.get("url", "") or "")
        for function in script.get("functions", []) or []:
            covered_functions.add(function.get("functionName", ""))
            for item in function.get("ranges", []) or []:
                start = int(item.get("startOffset", 0) or 0)
                end = int(item.get("endOffset", 0) or 0)
                covered_lines.add((url, start))
                covered_lines.add((url, end))
    candidates = (
        analysis.get("signature_candidates", []) or []
        if isinstance(analysis, dict)
        else getattr(analysis, "signature_candidates", []) or []
    )
    kept: list[dict[str, Any]] = []
    for candidate in candidates:
        name = str(
            (candidate.get("name", "") if isinstance(candidate, dict) else getattr(candidate, "name", ""))
            or ""
        )
        line = int(
            (candidate.get("line", 0) if isinstance(candidate, dict) else getattr(candidate, "line", 0))
            or 0
        )
        if any(url.endswith("bundle.js") or url.endswith(".js") for url, _line in covered_lines):
            kept.append(
                {
                    "name": name,
                    "line": line,
                    "covered": name in covered_functions or line in {item[1] for item in covered_lines},
                }
            )
    return kept


def _self_test() -> None:
    analysis = {
        "signature_candidates": [
            {"name": "genSign", "line": 12},
            {"name": "unused", "line": 99},
        ]
    }
    coverage = CoverageCapture(
        ok=True,
        scripts=[
            {
                "url": "https://example.com/bundle.js",
                "functions": [
                    {
                        "functionName": "genSign",
                        "ranges": [{"startOffset": 0, "endOffset": 100, "count": 1}],
                    }
                ],
            }
        ],
    )
    kept = filter_candidates_by_coverage(analysis, coverage)
    assert kept and kept[0]["name"] == "genSign"
    assert kept[0]["covered"] is True
    print("coverage_probe self-test OK")


if __name__ == "__main__":
    _self_test()
