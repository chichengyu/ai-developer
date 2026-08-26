"""Browser-side function-level call tracing for reverse engineering.

The normal deep hook records fetch/XHR provenance from the outside.  This
module adds a second browser init script that wraps matching JavaScript
functions before the page runs, so calls to candidate signature/device
functions record their actual arguments and return values.  It is opt-in
and bounded: only names/paths matching the configured patterns are wrapped,
and the scan stops after a fixed number of objects/functions.
"""

from __future__ import annotations

import json
from typing import Any


def function_probe_js(
    patterns: list[str] | tuple[str, ...] | None = None,
    global_name: str = "__deep_function_probe",
    max_scan: int = 5000,
) -> str:
    """Return a browser init script that wraps matching functions."""
    pattern_list = [str(pattern) for pattern in (patterns or []) if str(pattern).strip()]
    return r"""
(function () {
  if (typeof window === "undefined" || window[__PROBE_GLOBAL__]) return;
  var PROBE_NAME = __PROBE_GLOBAL__;
  var patterns = __PATTERNS__;
  var regexps = patterns.map(function (p) { return new RegExp(p, "i"); });
  var records = [];
  var startedAt = Date.now();
  var scanned = 0;
  function truncate(value, max) {
    if (value === undefined || value === null) return null;
    try {
      var text = typeof value === "string" ? value : JSON.stringify(value);
      if (!text) return null;
      return text.length > max ? text.slice(0, max) + "..." : text;
    } catch (e) {
      return String(value);
    }
  }
  function stackLines() {
    try {
      return (new Error().stack || "").split("\n").slice(1, 16)
        .map(function (line) { return line.trim(); }).filter(Boolean);
    } catch (e) {
      return [];
    }
  }
  function matches(name, path) {
    if (!regexps.length) return true;
    var haystack = String(name) + " " + String(path);
    for (var i = 0; i < regexps.length; i++) {
      try { if (regexps[i].test(haystack)) return true; } catch (e) {}
    }
    return false;
  }
  function wrap(fn, name, path) {
    if (typeof fn !== "function" || fn.__deepProbeWrapped) return fn;
    function wrapped() {
      var started = Date.now();
      var result;
      var error = null;
      try {
        result = fn.apply(this, arguments);
      } catch (e) {
        error = String(e && e.message || e);
      }
      try {
        records.push({
          kind: "function_call",
          name: name,
          path: path,
          args: truncate(Array.prototype.slice.call(arguments), 800),
          result: truncate(result, 800),
          error: error,
          stack: stackLines(),
          captured_at_ms: Date.now(),
          performance_ms: performance.now(),
          duration_ms: Date.now() - started
        });
      } catch (e) {}
      return result;
    }
    try { Object.defineProperty(wrapped, "name", { value: name || fn.name || "", configurable: true }); } catch (e) {}
    wrapped.__deepProbeWrapped = true;
    return wrapped;
  }
  function scan(container, depth, seen) {
    if (!container || depth > 4 || scanned > __MAX_SCAN__) return;
    if (typeof container === "function") {
      var fname = container.name || "";
      if (matches(fname, "")) return;
    }
    if (typeof container !== "object") return;
    if (seen.has(container)) return;
    seen.add(container);
    var keys = [];
    try { keys = Object.keys(container); } catch (e) {}
    for (var i = 0; i < keys.length; i++) {
      scanned++;
      if (scanned > __MAX_SCAN__) return;
      var key = keys[i];
      var value;
      try { value = container[key]; } catch (e) { continue; }
      var path = key;
      if (typeof value === "function") {
        if (matches(key, path) || matches(value.name || "", path)) {
          try { container[key] = wrap(value, value.name || key, path); } catch (e) {}
        }
      } else if (typeof value === "object" && value !== null) {
        scan(value, depth + 1, seen);
      }
    }
  }
  function rescan() {
    var seen = new Set();
    scan(window, 0, seen);
    if (window.webpackJsonp) scan(window.webpackJsonp, 0, seen);
    if (window.__webpack_modules__) scan(window.__webpack_modules__, 0, seen);
    if (window.webpackChunk) scan(window.webpackChunk, 0, seen);
    return records.length;
  }
  rescan();
  var hook = {
    started_at: startedAt,
    function_calls: records,
    rescan: rescan,
    snapshot: function () {
      return { function_calls: records };
    }
  };
  try {
    Object.defineProperty(window, PROBE_NAME, { value: hook, configurable: false, enumerable: false, writable: false });
  } catch (e) {
    window[PROBE_NAME] = hook;
  }
})();
""".strip().replace("__PROBE_GLOBAL__", json.dumps(global_name)).replace(
        "__PATTERNS__",
        json.dumps(pattern_list),
    ).replace("__MAX_SCAN__", str(int(max_scan)))


def parse_function_probes(hook: Any) -> dict[str, Any]:
    """Normalize a captured function-probe hook into a report dict."""
    if not isinstance(hook, dict):
        return {"ok": True, "function_calls": []}
    calls = list(hook.get("function_calls", []) or [])
    return {
        "ok": True,
        "function_calls": calls,
        "summary": {
            "function_calls": len(calls),
            "matched": sum(1 for call in calls if call.get("error") is None),
            "failed": sum(1 for call in calls if call.get("error") is not None),
        },
    }


def _self_test() -> None:
    js = function_probe_js(["genSign", "sign"], "__probe_test")
    assert "__probe_test" in js
    assert "new RegExp(p, \"i\")" in js
    assert "function_calls" in js
    print("function_probe self-test OK")


if __name__ == "__main__":
    _self_test()
