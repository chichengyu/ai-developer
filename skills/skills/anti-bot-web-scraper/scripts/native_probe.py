"""Browser native-API probes for signature provenance.

Signature functions rarely read only request params; they also read
``Date.now``, ``performance.now``, ``crypto.subtle``, ``TextEncoder``,
localStorage, and WebAssembly memory.  This module installs a bounded
browser probe that records those native calls with their arguments, results,
stack, and timing so the reverse report can show every external state a
signature consumed.
"""

from __future__ import annotations

import json
from typing import Any


def native_probe_js(global_name: str = "__deep_native_probe") -> str:
    """Return a browser init script wrapping high-value native APIs."""
    return r"""
(function () {
  if (typeof window === "undefined" || window[__NATIVE_GLOBAL__]) return;
  var records = [];
  var startedAt = Date.now();
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
      return (new Error().stack || "").split("\n").slice(1, 12)
        .map(function (line) { return line.trim(); }).filter(Boolean);
    } catch (e) {
      return [];
    }
  }
  function record(name, args, result, error) {
    try {
      records.push({
        kind: "native_call",
        name: name,
        args: truncate(Array.prototype.slice.call(args), 500),
        result: truncate(result, 500),
        error: error ? String(error && error.message || error) : null,
        stack: stackLines(),
        captured_at_ms: Date.now(),
        performance_ms: performance.now()
      });
    } catch (e) {}
  }
  function wrap(target, key, name) {
    if (!target || typeof target[key] !== "function") return;
    var original = target[key];
    target[key] = function () {
      var result;
      var error = null;
      try {
        result = original.apply(this, arguments);
      } catch (e) {
        error = e;
        throw e;
      }
      record(name, arguments, result, null);
      if (result && typeof result.then === "function") {
        return result.then(function (value) {
          record(name + ":resolved", arguments, value, null);
          return value;
        }, function (err) {
          record(name + ":rejected", arguments, null, err);
          throw err;
        });
      }
      return result;
    };
  }
  wrap(Date, "now", "Date.now");
  if (window.performance && performance.now) wrap(performance, "now", "performance.now");
  if (window.crypto && crypto.subtle && crypto.subtle.digest) {
    wrap(crypto.subtle, "digest", "crypto.subtle.digest");
  }
  if (window.TextEncoder && TextEncoder.prototype) wrap(TextEncoder.prototype, "encode", "TextEncoder.encode");
  if (window.localStorage) wrap(localStorage, "setItem", "localStorage.setItem");
  if (window.sessionStorage) wrap(sessionStorage, "setItem", "sessionStorage.setItem");
  if (window.WebAssembly && WebAssembly.Memory) {
    wrap(WebAssembly, "Memory", "WebAssembly.Memory");
  }
  var hook = {
    started_at: startedAt,
    native_calls: records,
    snapshot: function () { return { native_calls: records }; }
  };
  try {
    Object.defineProperty(window, __NATIVE_GLOBAL__, { value: hook, configurable: false, enumerable: false, writable: false });
  } catch (e) {
    window[__NATIVE_GLOBAL__] = hook;
  }
})();
""".strip().replace("__NATIVE_GLOBAL__", json.dumps(global_name))


def parse_native_probes(hook: Any) -> dict[str, Any]:
    """Normalize captured native probe records."""
    if not isinstance(hook, dict):
        return {"ok": True, "native_calls": []}
    calls = list(hook.get("native_calls", []) or [])
    return {
        "ok": True,
        "native_calls": calls,
        "summary": {
            "native_calls": len(calls),
            "unique_apis": len({item.get("name") for item in calls if isinstance(item, dict)}),
        },
    }


def _self_test() -> None:
    js = native_probe_js("__native_test")
    assert "__native_test" in js
    assert "crypto.subtle.digest" in js
    assert "localStorage.setItem" in js
    report = parse_native_probes({"native_calls": [{"name": "Date.now"}, {"name": "Date.now"}]})
    assert report["summary"]["native_calls"] == 2
    assert report["summary"]["unique_apis"] == 1
    print("native_probe self-test OK")


if __name__ == "__main__":
    _self_test()
