"""CDP breakpoint-level reverse probing.

Function-name scanning cannot see webpack closures.  This module uses Chrome
DevTools Protocol breakpoints at the exact source locations found by static
analysis, then dumps the real call frame: function name, arguments, ``this``
scope keys, URL, line, and column.  It is optional and only runs when a
real browser session is available.
"""

from __future__ import annotations

import time
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BreakpointCapture:
    ok: bool = False
    error: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error": self.error,
            "calls": self.calls,
            "summary": {
                "breakpoint_hits": len(self.calls),
                "with_arguments": sum(1 for item in self.calls if item.get("evaluation")),
            },
        }


def build_breakpoints_from_analysis(
    analysis: Any,
    js_url: str | None = None,
) -> list[dict[str, Any]]:
    """Build CDP breakpoint specs from static signature candidates."""
    breakpoints: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    candidates = (
        analysis.get("signature_candidates", []) or []
        if isinstance(analysis, dict)
        else getattr(analysis, "signature_candidates", []) or []
    )
    request_sites = (
        analysis.get("request_sites", []) or []
        if isinstance(analysis, dict)
        else getattr(analysis, "request_sites", []) or []
    )
    for candidate in candidates:
        line = int(
            (candidate.get("line", 0) if isinstance(candidate, dict) else getattr(candidate, "line", 0))
            or 0
        )
        if line <= 0:
            continue
        url = js_url or "bundle.js"
        key = (url, line)
        if key in seen:
            continue
        seen.add(key)
        breakpoints.append(
            {
                "url": url,
                "line": line,
                "column": 0,
                "function": str(
                    (candidate.get("name", "") if isinstance(candidate, dict) else getattr(candidate, "name", ""))
                    or ""
                ),
                "reason": "signature_candidate",
            }
        )
    for site in request_sites:
        line = int(
            (site.get("line", 0) if isinstance(site, dict) else getattr(site, "line", 0))
            or 0
        )
        if line <= 0:
            continue
        url = js_url or "bundle.js"
        key = (url, line)
        if key in seen:
            continue
        seen.add(key)
        breakpoints.append(
            {
                "url": url,
                "line": line,
                "column": 0,
                "function": "request-site",
                "reason": "request_site",
            }
        )
    return breakpoints[:50]


def build_paused_record(
    event: dict[str, Any],
    evaluate: Any = None,
) -> dict[str, Any]:
    """Convert one Debugger.paused event into a probe record."""
    frames = list(event.get("callFrames", []) or [])
    if not frames:
        return {}
    frame = frames[0]
    location = dict(frame.get("location", {}) or {})
    record: dict[str, Any] = {
        "functionName": str(frame.get("functionName", "") or ""),
        "url": str(location.get("url", "") or ""),
        "line": int(location.get("lineNumber", 0) or 0) + 1,
        "column": int(location.get("columnNumber", 0) or 0),
        "callFrameId": str(frame.get("callFrameId", "") or ""),
        "paused_at_ms": int(time.time() * 1000),
        "evaluation": None,
    }
    if evaluate is not None:
        try:
            result = evaluate(record["callFrameId"])
            record["evaluation"] = result
        except Exception as exc:
            record["evaluation_error"] = str(exc)
    return record


def run_cdp_breakpoint_probe(
    session: Any,
    breakpoints: list[dict[str, Any]],
    *,
    reload: bool = True,
    wait_ms: float = 5000,
) -> BreakpointCapture:
    """Set breakpoints, reload, and collect paused call frames."""
    if session is None or session.context is None or session.page is None:
        return BreakpointCapture(ok=False, error="browser session is not open")
    try:
        cdp = session.context.new_cdp_session(session.page)
        cdp.send("Debugger.enable")
        for item in breakpoints[:50]:
            cdp.send(
                "Debugger.setBreakpointByUrl",
                {
                    "lineNumber": max(0, int(item.get("line", 1)) - 1),
                    "columnNumber": int(item.get("column", 0) or 0),
                    "url": str(item.get("url", "bundle.js")),
                    "condition": "",
                },
            )
        calls: list[dict[str, Any]] = []

        def on_paused(event: dict[str, Any]) -> None:
            record = build_paused_record(
                event,
                evaluate=lambda frame_id: cdp.send(
                    "Debugger.evaluateOnCallFrame",
                    {
                        "callFrameId": frame_id,
                        "expression": (
                            "JSON.stringify({args:Array.prototype.slice.call(arguments)"
                            ".map(function(a){try{return typeof a==='string'?a:JSON.stringify(a)}"
                            "catch(e){return String(a)}}),thisType:typeof this,"
                            "scopeKeys:Object.keys(this)})"
                        ),
                        "returnByValue": True,
                    },
                ).get("result", {}).get("value"),
            )
            if record:
                calls.append(record)
            with suppress(Exception):
                cdp.send("Debugger.resume")

        cdp.on("Debugger.paused", on_paused)
        if reload:
            session.page.reload(wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
            with suppress(Exception):
                session.page.wait_for_load_state("networkidle", timeout=wait_ms)
        else:
            time.sleep(wait_ms / 1000.0)
        with suppress(Exception):
            cdp.send("Debugger.disable")
        return BreakpointCapture(ok=True, calls=calls)
    except Exception as exc:
        return BreakpointCapture(ok=False, error=str(exc))


def run_url_cdp_probe(
    url: str,
    breakpoints: list[dict[str, Any]],
    *,
    headless: bool = True,
    engine: str = "playwright",
    wait_ms: float = 5000,
) -> BreakpointCapture:
    """Open a URL in a browser and run the CDP breakpoint probe."""
    try:
        from browser_session import BrowserSession
    except Exception as exc:
        return BreakpointCapture(ok=False, error=f"browser dependencies unavailable: {exc}")
    session = BrowserSession(
        headless=headless,
        engine=engine,
        auto_install=False,
    )
    try:
        session.start()
        session.goto(url, wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
        return run_cdp_breakpoint_probe(
            session,
            breakpoints,
            reload=True,
            wait_ms=wait_ms,
        )
    except Exception as exc:
        return BreakpointCapture(ok=False, error=str(exc))
    finally:
        session.close()


def run_url_cdp_return_probe(
    url: str,
    breakpoints: list[dict[str, Any]],
    *,
    headless: bool = True,
    engine: str = "playwright",
    wait_ms: float = 5000,
) -> BreakpointCapture:
    """Open a URL and run the entry + return-value CDP probe."""
    try:
        from browser_session import BrowserSession
    except Exception as exc:
        return BreakpointCapture(ok=False, error=f"browser dependencies unavailable: {exc}")
    session = BrowserSession(headless=headless, engine=engine, auto_install=False)
    try:
        session.start()
        session.goto(url, wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
        return run_cdp_return_probe(
            session,
            breakpoints,
            reload=True,
            wait_ms=wait_ms,
        )
    except Exception as exc:
        return BreakpointCapture(ok=False, error=str(exc))
    finally:
        session.close()


def run_cdp_return_probe(
    session: Any,
    breakpoints: list[dict[str, Any]],
    *,
    reload: bool = True,
    wait_ms: float = 5000,
) -> BreakpointCapture:
    """Capture both entry arguments and return values via step-out."""
    if session is None or session.context is None or session.page is None:
        return BreakpointCapture(ok=False, error="browser session is not open")
    try:
        cdp = session.context.new_cdp_session(session.page)
        cdp.send("Debugger.enable")
        for item in breakpoints[:50]:
            cdp.send(
                "Debugger.setBreakpointByUrl",
                {
                    "lineNumber": max(0, int(item.get("line", 1)) - 1),
                    "columnNumber": int(item.get("column", 0) or 0),
                    "url": str(item.get("url", "bundle.js")),
                    "condition": "",
                },
            )
        calls: list[dict[str, Any]] = []
        state = {"phase": "entry", "function": None}

        def on_paused(event: dict[str, Any]) -> None:
            frames = list(event.get("callFrames", []) or [])
            if not frames:
                with suppress(Exception):
                    cdp.send("Debugger.resume")
                return
            frame = frames[0]
            if state["phase"] == "entry":
                record = build_paused_record(
                    event,
                    evaluate=lambda frame_id: cdp.send(
                        "Debugger.evaluateOnCallFrame",
                        {
                            "callFrameId": frame_id,
                            "expression": (
                                "JSON.stringify({args:Array.prototype.slice.call(arguments)"
                                ".map(function(a){try{return typeof a==='string'?a:JSON.stringify(a)}"
                                "catch(e){return String(a)}}),thisType:typeof this})"
                            ),
                            "returnByValue": True,
                        },
                    ).get("result", {}).get("value"),
                )
                record["returnValue"] = None
                calls.append(record)
                state["phase"] = "return"
                state["function"] = record.get("functionName")
                try:
                    cdp.send("Debugger.stepOut")
                except Exception:
                    with suppress(Exception):
                        cdp.send("Debugger.resume")
                    state["phase"] = "entry"
                return
            return_value = None
            try:
                result = cdp.send("Debugger.getReturnValue")
                return_value = result.get("result", {}).get("value")
            except Exception:
                try:
                    evaluated = cdp.send(
                        "Debugger.evaluateOnCallFrame",
                        {
                            "callFrameId": frame.get("callFrameId", ""),
                            "expression": "({})",
                            "returnByValue": True,
                        },
                    )
                    return_value = evaluated.get("result", {}).get("value")
                except Exception:
                    return_value = None
            if calls:
                calls[-1]["returnValue"] = return_value
            state["phase"] = "entry"
            with suppress(Exception):
                cdp.send("Debugger.resume")

        cdp.on("Debugger.paused", on_paused)
        if reload:
            session.page.reload(wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
            with suppress(Exception):
                session.page.wait_for_load_state("networkidle", timeout=wait_ms)
        else:
            time.sleep(wait_ms / 1000.0)
        with suppress(Exception):
            cdp.send("Debugger.disable")
        return BreakpointCapture(ok=True, calls=calls)
    except Exception as exc:
        return BreakpointCapture(ok=False, error=str(exc))


def _self_test() -> None:
    breakpoints = build_breakpoints_from_analysis(
        type(
            "A",
            (),
            {
                "signature_candidates": [
                    type("C", (), {"name": "genSign", "line": 12, "confidence": 0.9})()
                ],
                "request_sites": [],
            },
        )()
    )
    assert breakpoints and breakpoints[0]["line"] == 12
    record = build_paused_record(
        {
            "callFrames": [
                {
                    "functionName": "genSign",
                    "location": {"url": "bundle.js", "lineNumber": 11, "columnNumber": 2},
                    "callFrameId": "frame-1",
                }
            ]
        },
        evaluate=lambda _frame_id: {"args": ["a"], "thisType": "object"},
    )
    assert record["functionName"] == "genSign"
    assert record["line"] == 12
    print("cdp_probe self-test OK")


if __name__ == "__main__":
    _self_test()
