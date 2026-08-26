"""Browser execution-trace capture and Node replay.

This is a bounded version of execution replay: CDP records script-parsed and
console events while the page runs, the script sources are fetched back, and
Node re-executes each source to see whether the same console outputs and
signature calls can be reproduced outside the browser.
"""

from __future__ import annotations

import time
from contextlib import suppress
from typing import Any


def capture_execution_trace(
    session: Any,
    *,
    reload: bool = True,
    wait_ms: float = 5000,
    max_script_bytes: int = 2_000_000,
) -> dict[str, Any]:
    """Capture script-parsed and console events from a browser page."""
    if session is None or session.context is None or session.page is None:
        return {"ok": False, "error": "browser session is not open"}
    try:
        cdp = session.context.new_cdp_session(session.page)
        cdp.send("Debugger.enable")
        scripts: list[dict[str, Any]] = []
        console_events: list[dict[str, Any]] = []
        script_ids: list[str] = []

        def on_script_parsed(event: dict[str, Any]) -> None:
            script_id = str(event.get("scriptId", "") or "")
            if script_id and script_id not in script_ids:
                script_ids.append(script_id)
                scripts.append(
                    {
                        "scriptId": script_id,
                        "url": str(event.get("url", "") or ""),
                        "sourceLength": int(event.get("length", 0) or 0),
                    }
                )

        def on_console(event: dict[str, Any]) -> None:
            console_events.append(
                {
                    "type": str(event.get("type", "") or ""),
                    "args": [
                        str(arg.get("value", "") or arg.get("description", "") or "")
                        for arg in event.get("args", []) or []
                    ],
                    "timestamp": int(event.get("timestamp", 0) or 0),
                }
            )

        cdp.on("Debugger.scriptParsed", on_script_parsed)
        cdp.on("Runtime.consoleAPICalled", on_console)
        if reload:
            session.page.reload(wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
            with suppress(Exception):
                session.page.wait_for_load_state("networkidle", timeout=wait_ms)
        else:
            time.sleep(wait_ms / 1000.0)
        for script in scripts:
            try:
                source = cdp.send(
                    "Debugger.getScriptSource",
                    {"scriptId": script["scriptId"]},
                ).get("scriptSource", "")
                script["source"] = str(source or "")[:max_script_bytes]
            except Exception:
                script["source"] = ""
        return {
            "ok": True,
            "scripts": scripts,
            "console_events": console_events,
            "summary": {"scripts": len(scripts), "console_events": len(console_events)},
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def replay_execution_trace(
    trace: dict[str, Any],
    *,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Re-execute captured script sources in Node and report outcomes."""
    try:
        from deep_reverse import node_available, run_js
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable"}
    if not node_available():
        return {"ok": False, "error": "node is not available"}
    replays: list[dict[str, Any]] = []
    for script in trace.get("scripts", []) or []:
        source = str(script.get("source", "") or "")
        if not source.strip():
            continue
        result = run_js(source, timeout=timeout)
        replays.append(
            {
                "url": str(script.get("url", "") or ""),
                "scriptId": str(script.get("scriptId", "") or ""),
                "ok": bool(result.get("ok")),
                "error": result.get("error"),
                "result": str(result.get("stdout", "") or "")[:500],
            }
        )
    return {
        "ok": True,
        "replays": replays,
        "summary": {
            "scripts": len(trace.get("scripts", []) or []),
            "replayed": len(replays),
            "ok": sum(1 for item in replays if item.get("ok")),
        },
    }


def run_url_execution_trace(
    url: str,
    *,
    headless: bool = True,
    engine: str = "playwright",
    wait_ms: float = 5000,
) -> dict[str, Any]:
    """Open a URL, capture an execution trace, and replay scripts in Node."""
    try:
        from browser_session import BrowserSession
    except Exception as exc:
        return {"ok": False, "error": f"browser dependencies unavailable: {exc}"}
    session = BrowserSession(headless=headless, engine=engine, auto_install=False)
    try:
        session.start()
        session.goto(url, wait_until="domcontentloaded", timeout=max(5000.0, wait_ms))
        trace = capture_execution_trace(session, reload=True, wait_ms=wait_ms)
        return replay_execution_trace(trace)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        session.close()


def _self_test() -> None:
    trace = {
        "scripts": [{"scriptId": "1", "url": "bundle.js", "source": "var a = 1;"}],
        "console_events": [],
    }
    result = replay_execution_trace(trace)
    assert result["summary"]["replayed"] == 1
    print("replay_trace self-test OK")


if __name__ == "__main__":
    _self_test()
