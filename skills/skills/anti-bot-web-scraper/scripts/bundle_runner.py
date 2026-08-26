"""Whole-bundle execution for strongly obfuscated JavaScript.

Instead of guessing at individual functions with regex, this module loads a
full bundle into a Node VM with browser stubs, scans the resulting global
object graph for candidate functions, and calls them with plausible
argument templates.  The runtime traces give ``deep_reverse`` another signal:
which functions actually execute, what they return, and whether they can be
replayed in Node.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_WEBPACK_TABLE_RE = re.compile(r"(?:__webpack_modules__|_webpack_modules)\s*=\s*(\{)", re.DOTALL)
_WEBPACK_FN_RE = re.compile(r"""["'](\d+)["']\s*:\s*(function\s*\()""", re.DOTALL)


def extract_webpack_module_table(js: str) -> dict[str, str]:
    """Extract ``{id: function(...) {...}}`` module sources from a bundle."""
    table_match = _WEBPACK_TABLE_RE.search(js)
    if not table_match:
        return {}
    open_index = table_match.start(1)
    close_index = _match_braces(js, open_index)
    if close_index < 0:
        return {}
    body = js[open_index : close_index + 1]
    modules: dict[str, str] = {}
    for match in _WEBPACK_FN_RE.finditer(body):
        module_id = match.group(1)
        fn_start = match.start(2)
        fn_open = body.index("(", fn_start)
        param_close = _match_braces(body, fn_open)
        body_open = body.index("{", param_close)
        fn_close = _match_braces(body, body_open)
        if fn_close < 0:
            continue
        modules[module_id] = body[fn_start : fn_close + 1]
    return modules


def _match_braces(text: str, open_index: int) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _node_script() -> str:
    return r"""
const fs = require("fs");
const vm = require("vm");
const crypto = require("crypto");
const code = fs.readFileSync(process.argv[2], "utf8");
const candidates = JSON.parse(process.argv[3] || "[]");
const timeoutMs = Number(process.argv[4] || 10000);
const modules = JSON.parse(process.argv[5] || "{}");
const startedAt = Date.now();

const storage = { local: {}, session: {} };
const sandbox = {
  console: console,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  setInterval: setInterval,
  clearInterval: clearInterval,
  Buffer: Buffer,
  URL: URL,
  URLSearchParams: URLSearchParams,
  TextEncoder: TextEncoder,
  TextDecoder: TextDecoder,
  crypto: crypto,
  require: function (name) {
    if (name === "crypto") return crypto;
    throw new Error("require(" + name + ") is not available in bundle sandbox");
  },
  location: {
    href: "https://example.com/",
    protocol: "https:",
    host: "example.com",
    hostname: "example.com",
    pathname: "/",
    search: "",
    hash: ""
  },
  navigator: {
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    platform: "Win32",
    language: "zh-CN",
    languages: ["zh-CN", "zh", "en"],
    hardwareConcurrency: 8,
    deviceMemory: 8,
    maxTouchPoints: 0,
    cookieEnabled: true,
    webdriver: false,
    vendor: "Google Inc.",
    plugins: []
  },
  screen: { width: 1920, height: 1080, availWidth: 1920, availHeight: 1040, colorDepth: 24, pixelDepth: 24 },
  document: {
    referrer: "",
    cookie: "",
    title: "",
    createElement: function () {
      return {
        width: 0,
        height: 0,
        style: {},
        setAttribute: function () {},
        getContext: function () {
          return { fillRect: function () {}, fillText: function () {}, toDataURL: function () { return "data:image/png;base64,"; } };
        }
      };
    },
    getElementById: function () { return null; },
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    addEventListener: function () {},
    body: { appendChild: function () {} }
  },
  localStorage: {
    _data: storage.local,
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(this._data, k) ? this._data[k] : null; },
    setItem: function (k, v) { this._data[k] = String(v); },
    removeItem: function (k) { delete this._data[k]; },
    clear: function () { this._data = {}; },
    key: function (i) { return Object.keys(this._data)[i] || null; },
    get length() { return Object.keys(this._data).length; }
  },
  sessionStorage: {
    _data: storage.session,
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(this._data, k) ? this._data[k] : null; },
    setItem: function (k, v) { this._data[k] = String(v); },
    removeItem: function (k) { delete this._data[k]; },
    clear: function () { this._data = {}; },
    key: function (i) { return Object.keys(this._data)[i] || null; },
    get length() { return Object.keys(this._data).length; }
  },
  performance: {
    now: function () { return Date.now() - startedAt; },
    getEntriesByType: function () { return []; },
    getEntriesByName: function () { return []; }
  },
  fetch: function (url, init) { return Promise.resolve({ ok: true, status: 200, url: String(url), json: function () { return Promise.resolve({}); }, text: function () { return Promise.resolve(""); } }); },
  XMLHttpRequest: function () { this.open = function () {}; this.send = function () {}; this.setRequestHeader = function () {}; this.getAllResponseHeaders = function () { return ""; }; },
  WebSocket: function () { this.send = function () {}; this.close = function () {}; },
  EventSource: function () { this.close = function () {}; },
  atob: function (s) { return Buffer.from(s, "base64").toString("binary"); },
  btoa: function (s) { return Buffer.from(s, "binary").toString("base64"); }
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.self = sandbox;

const errors = [];
const webpackModuleErrors = [];
const webpackModulesExecuted = [];
const wanted = new Set(candidates);
try {
  vm.runInNewContext(code, sandbox, { timeout: timeoutMs, displayErrors: false });
} catch (e) {
  errors.push(String(e && e.message || e));
}

const seen = new Set();
const functions = [];
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
function collect(obj, depth, path) {
  if (!obj || depth > 4 || seen.size > 5000) return;
  if (typeof obj === "function") {
    var name = obj.name || path.split(".").pop() || "";
    var isWanted = wanted.has(name) || wanted.has(path);
    if (functions.length >= 60 && !isWanted) return;
    functions.push({ name: name, path: path, fn: obj });
    return;
  }
  if (typeof obj !== "object") return;
  if (seen.has(obj)) return;
  seen.add(obj);
  var keys = [];
  try { keys = Object.keys(obj); } catch (e) {}
  for (var i = 0; i < keys.length && functions.length < 60; i++) {
    var key = keys[i];
    try {
      collect(obj[key], depth + 1, path + "." + key);
    } catch (e) {}
  }
}
collect(sandbox, 0, "global");
for (const moduleId of Object.keys(modules)) {
  try {
    const source = String(modules[moduleId] || "");
    const fn = vm.runInContext("(" + source + ")", sandbox, { timeout: timeoutMs });
    const mod = { exports: {} };
    fn(mod, mod.exports, function (request) {
      throw new Error("__webpack_require__(" + request + ") not available in probe sandbox");
    });
    webpackModulesExecuted.push(moduleId);
    collect(mod.exports, 0, "webpack." + moduleId);
    for (const exportName of Object.keys(mod.exports || {})) {
      try {
        const exported = mod.exports[exportName];
        if (typeof exported === "function") {
          functions.push({ name: exportName, path: "webpack." + moduleId + "." + exportName, fn: exported });
        }
      } catch (e) {}
    }
  } catch (e) {
    webpackModuleErrors.push(moduleId + ": " + String(e && e.message || e));
  }
}
for (var wantedName of wanted) {
  try {
    if (typeof sandbox[wantedName] === "function") {
      functions.push({ name: wantedName, path: "global." + wantedName, fn: sandbox[wantedName] });
    }
  } catch (e) {}
}

function argsFor(name, length) {
  var lower = String(name || "").toLowerCase();
  var args = [];
  for (var i = 0; i < length; i++) {
    if (i === 0 && /sign|hash|md5|hmac|token|secret|device|finger/.test(lower)) {
      args.push("a=1&b=2&ts=1786000000");
    } else if (i === 0) {
      args.push("a=1&b=2&ts=1786000000");
    } else if (i === 1) {
      args.push("1786000000");
    } else if (i === 2) {
      args.push({"a": "1", "b": "2", "ts": "1786000000"});
    } else {
      args.push(String(i));
    }
  }
  return args;
}

const traces = [];
for (var j = 0; j < functions.length; j++) {
  var item = functions[j];
  if (wanted.size && !wanted.has(item.name) && !wanted.has(item.path)) continue;
  var start = Date.now();
  var result = null;
  var ok = true;
  var error = null;
  try {
    result = item.fn.apply(null, argsFor(item.name, item.fn.length));
  } catch (e) {
    ok = false;
    error = String(e && e.message || e);
  }
  traces.push({
    name: item.name,
    path: item.path,
    args: truncate(argsFor(item.name, item.fn.length), 500),
    result: truncate(result, 500),
    ok: ok,
    error: error,
    duration_ms: Date.now() - start
  });
}
console.log(JSON.stringify({
  ok: true,
  functions: functions.map(function (f) { return { name: f.name, path: f.path }; }),
  traces: traces,
  errors: errors.slice(0, 5),
  candidates: candidates,
  webpack_modules_executed: webpackModulesExecuted,
  webpack_module_errors: webpackModuleErrors
}));
"""


def run_bundle_execution(
    js: str,
    candidate_names: list[str] | None = None,
    *,
    auto_install: bool = False,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Execute a JS bundle in a Node VM and return candidate traces."""
    try:
        from deep_reverse import find_function_names, node_available
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable"}
    if not node_available():
        return {"ok": False, "error": "node is not available"}
    candidates = list(candidate_names or [])
    if not candidates:
        try:
            candidates = find_function_names(js)[:30]
        except Exception:
            candidates = []
    module_table = extract_webpack_module_table(js)
    script = _node_script()
    with tempfile.TemporaryDirectory(prefix="bundle-runner-") as tmp:
        js_path = Path(tmp) / "bundle.js"
        runner_path = Path(tmp) / "runner.cjs"
        js_path.write_text(js, encoding="utf-8")
        runner_path.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run(
                [
                    os.environ.get("CODEX_NODE") or "node",
                    str(runner_path),
                    str(js_path),
                    json.dumps(candidates),
                    str(int(timeout * 1000)),
                    json.dumps(module_table),
                ],
                capture_output=True,
                text=True,
                timeout=timeout + 5,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"bundle execution timed out after {timeout}s"}
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "bundle execution failed")[-1000:],
        }
    try:
        data = json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid runner output: {exc}"}
    traces = list(data.get("traces") or [])
    webpack_modules = list(data.get("webpack_modules_executed") or [])
    webpack_errors = list(data.get("webpack_module_errors") or [])
    return {
        "ok": True,
        "functions": data.get("functions", []),
        "traces": traces,
        "errors": data.get("errors", []),
        "candidates": data.get("candidates", []),
        "webpack_modules_executed": webpack_modules,
        "webpack_module_errors": webpack_errors,
        "summary": {
            "functions_scanned": len(data.get("functions", [])),
            "functions_called": len(traces),
            "matched": sum(1 for trace in traces if trace.get("ok") and trace.get("result") is not None),
            "webpack_modules_executed": len(webpack_modules),
        },
    }


def _self_test() -> None:
    result = run_bundle_execution(
        "function genSign(a,b){return a+':'+b;}",
        candidate_names=["genSign"],
        timeout=5,
    )
    assert result["ok"] is True
    assert any(trace["name"] == "genSign" for trace in result["traces"])
    print("bundle_runner self-test OK")


if __name__ == "__main__":
    _self_test()
