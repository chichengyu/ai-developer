"""WASM boundary hooking, parsing, and Node probing.

Modern anti-bot signatures increasingly hide inside WebAssembly.  This module
provides three layers: a browser init script that wraps
``WebAssembly.instantiate`` and records exported-function calls, a minimal
WASM import/export parser for captured binaries, and a Node probe that
instantiates a local ``.wasm`` with stubs and calls its exports.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_WASM_URL_RE = re.compile(r"""["']([^"']+\.wasm(?:\?[^"']*)?)["']""")


def wasm_hook_js(global_name: str = "__deep_wasm_hook") -> str:
    """Return a browser init script that records WASM export calls."""
    return r"""
(function () {
  if (typeof window === "undefined" || window[__WASM_GLOBAL__]) return;
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
  function wrapExports(exports, url) {
    if (!exports || typeof exports !== "object") return;
    Object.keys(exports).forEach(function (name) {
      var fn = exports[name];
      if (typeof fn !== "function" || fn.__deepWasmWrapped) return;
      function wrapped() {
        var started = Date.now();
        var result;
        var error = null;
        try {
          result = fn.apply(null, arguments);
        } catch (e) {
          error = String(e && e.message || e);
        }
        try {
          records.push({
            kind: "wasm_export_call",
            name: name,
            url: truncate(url, 500),
            args: truncate(Array.prototype.slice.call(arguments), 500),
            result: truncate(result, 500),
            error: error,
            captured_at_ms: Date.now(),
            duration_ms: Date.now() - started
          });
        } catch (e) {}
        return result;
      }
      try { Object.defineProperty(wrapped, "name", { value: name, configurable: true }); } catch (e) {}
      wrapped.__deepWasmWrapped = true;
      exports[name] = wrapped;
    });
  }
  var NativeInstantiate = WebAssembly.instantiate;
  var NativeInstantiateStreaming = WebAssembly.instantiateStreaming;
  WebAssembly.instantiate = function (bufferOrModule, imports) {
    return NativeInstantiate.apply(WebAssembly, arguments).then(function (result) {
      try { wrapExports(result.instance && result.instance.exports, "wasm:instantiate"); } catch (e) {}
      return result;
    });
  };
  if (NativeInstantiateStreaming) {
    WebAssembly.instantiateStreaming = function (source, imports) {
      return NativeInstantiateStreaming.apply(WebAssembly, arguments).then(function (result) {
        try { wrapExports(result.instance && result.instance.exports, "wasm:streaming"); } catch (e) {}
        return result;
      });
    };
  }
  var hook = {
    started_at: startedAt,
    wasm_calls: records,
    snapshot: function () { return { wasm_calls: records }; }
  };
  try {
    Object.defineProperty(window, __WASM_GLOBAL__, { value: hook, configurable: false, enumerable: false, writable: false });
  } catch (e) {
    window[__WASM_GLOBAL__] = hook;
  }
})();
""".strip().replace("__WASM_GLOBAL__", json.dumps(global_name))


def parse_wasm_imports_exports(wasm_bytes: bytes) -> dict[str, Any]:
    """Parse WASM import/export names with a minimal binary reader."""
    if not wasm_bytes.startswith(b"\x00asm") or len(wasm_bytes) < 8:
        return {"ok": False, "error": "invalid wasm header", "imports": [], "exports": []}
    imports: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []
    pos = 8
    while pos < len(wasm_bytes):
        section_id = wasm_bytes[pos]
        pos += 1
        size, pos = _read_leb128(wasm_bytes, pos)
        section_end = pos + size
        if section_end > len(wasm_bytes):
            break
        if section_id == 2:
            count, pos = _read_leb128(wasm_bytes, pos)
            for _ in range(count):
                module, pos = _read_name(wasm_bytes, pos)
                field, pos = _read_name(wasm_bytes, pos)
                kind = wasm_bytes[pos] if pos < len(wasm_bytes) else None
                pos += 1
                imports.append({"module": module, "field": field, "kind": kind})
        elif section_id == 7:
            count, pos = _read_leb128(wasm_bytes, pos)
            for _ in range(count):
                name, pos = _read_name(wasm_bytes, pos)
                kind = wasm_bytes[pos] if pos < len(wasm_bytes) else None
                index, pos = _read_leb128(wasm_bytes, pos + 1)
                exports.append({"name": name, "kind": kind, "index": index})
        pos = section_end
    return {
        "ok": True,
        "imports": imports,
        "exports": exports,
        "summary": {"imports": len(imports), "exports": len(exports)},
    }


def _read_leb128(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
    return result, pos


def _read_name(data: bytes, pos: int) -> tuple[str, int]:
    length, pos = _read_leb128(data, pos)
    end = min(len(data), pos + length)
    return data[pos:end].decode("utf-8", "replace"), end


def analyze_wasm_capture(capture: dict[str, Any]) -> dict[str, Any]:
    """Find WASM artifacts referenced by a capture."""
    urls: list[str] = []
    html = str(capture.get("html", "") or "")
    urls.extend(
        item for item in _WASM_URL_RE.findall(html) if item not in urls
    )
    for entry in capture.get("network", []) or []:
        url = str(entry.get("url", "") or "")
        if url.endswith(".wasm") and url not in urls:
            urls.append(url)
        body = entry.get("body") or entry.get("response_body")
        if isinstance(body, bytes) and body.startswith(b"\x00asm"):
            parsed = parse_wasm_imports_exports(body)
            return {"ok": True, "urls": urls, "inline": parsed}
    return {"ok": True, "urls": urls, "inline": None}


def run_wasm_probe(
    wasm_bytes: bytes,
    export_names: list[str] | None = None,
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Instantiate a WASM binary in Node and call its exported functions."""
    script = r"""
const fs = require("fs");
const bytes = fs.readFileSync(process.argv[2]);
const wanted = new Set(JSON.parse(process.argv[3] || "[]"));
const imports = {};
const traces = [];
const errors = [];
function changedRanges(before, after) {
  const ranges = [];
  let start = -1;
  const length = Math.min(before.length, after.length);
  for (let i = 0; i < length; i++) {
    if (before[i] !== after[i]) {
      if (start < 0) start = i;
    } else if (start >= 0) {
      ranges.push([start, i - 1]);
      start = -1;
    }
  }
  if (start >= 0) ranges.push([start, length - 1]);
  return ranges;
}
WebAssembly.instantiate(bytes, imports).then(function (result) {
  const exportsObj = result.instance.exports || {};
  const names = wanted.size ? Object.keys(exportsObj).filter(function (n) { return wanted.has(n); }) : Object.keys(exportsObj);
  for (const name of names) {
    const fn = exportsObj[name];
    if (typeof fn !== "function") continue;
    const started = Date.now();
    const memory = exportsObj.memory;
    const memoryBefore = memory ? new Uint8Array(memory.buffer) : null;
    try {
      const value = fn(0, 1, 2);
      const memoryDiff = memoryBefore && memory ? changedRanges(memoryBefore, new Uint8Array(memory.buffer)) : [];
      traces.push({ name: name, args: [0, 1, 2], result: value === undefined ? null : value, ok: true, memory_ranges: memoryDiff, duration_ms: Date.now() - started });
    } catch (e) {
      traces.push({ name: name, args: [0, 1, 2], result: null, ok: false, error: String(e && e.message || e), memory_ranges: [], duration_ms: Date.now() - started });
    }
  }
  console.log(JSON.stringify({ ok: true, traces: traces, errors: errors }));
}).catch(function (e) {
  console.log(JSON.stringify({ ok: false, error: String(e && e.message || e), traces: traces, errors: errors }));
});
"""
    try:
        from deep_reverse import node_available
    except Exception:
        return {"ok": False, "error": "deep_reverse unavailable"}
    if not node_available():
        return {"ok": False, "error": "node is not available"}
    with tempfile.TemporaryDirectory(prefix="wasm-probe-") as tmp:
        wasm_path = Path(tmp) / "probe.wasm"
        runner_path = Path(tmp) / "runner.cjs"
        wasm_path.write_bytes(wasm_bytes)
        runner_path.write_text(script, encoding="utf-8")
        try:
            proc = subprocess.run(
                [
                    os.environ.get("CODEX_NODE") or "node",
                    str(runner_path),
                    str(wasm_path),
                    json.dumps(export_names or []),
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"wasm probe timed out after {timeout}s"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or proc.stdout or "wasm probe failed")[-1000:]}
    try:
        data = json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"invalid wasm probe output: {exc}"}
    return {
        "ok": bool(data.get("ok")),
        "error": data.get("error"),
        "traces": data.get("traces", []),
        "summary": {
            "exports_called": len(data.get("traces", [])),
            "matched": sum(1 for item in data.get("traces", []) if item.get("ok")),
            "memory_ranges": sum(
                len(item.get("memory_ranges", []) or []) for item in data.get("traces", [])
            ),
        },
    }


def decompile_wasm_available() -> bool:
    """Return True when wabt's wasm-decompile or wasm2wat is installed."""
    return bool(
        shutil.which("wasm-decompile")
        or shutil.which("wasm2wat")
        or shutil.which("wat2wasm")
    )


def decompile_wasm(
    wasm_bytes: bytes,
    tool: str = "auto",
    *,
    timeout: float = 20.0,
    auto_install: bool = False,
) -> dict[str, Any]:
    """Decompile a WASM binary with wabt when available."""
    if not decompile_wasm_available():
        if auto_install:
            from ensure_reverse_tools import ensure_wabt

            ensure_wabt(install=True, timeout=timeout)
        if not decompile_wasm_available():
            return {"ok": False, "error": "wabt wasm-decompile/wasm2wat is not installed"}
    command = shutil.which("wasm-decompile") or shutil.which("wasm2wat")
    if tool == "wat" and shutil.which("wasm2wat"):
        command = shutil.which("wasm2wat")
    if not command:
        return {"ok": False, "error": "wabt tool is not installed"}
    with tempfile.TemporaryDirectory(prefix="wasm-decompile-") as tmp:
        wasm_path = Path(tmp) / "input.wasm"
        wasm_path.write_bytes(wasm_bytes)
        try:
            proc = subprocess.run(
                [command, str(wasm_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "wabt decompile failed")[-1000:]}
    text = proc.stdout or proc.stderr
    return {"ok": True, "tool": Path(command).name, "output": text[:200_000]}


def decompile_wasm_pseudocode(
    wasm_bytes: bytes,
    *,
    timeout: float = 20.0,
    auto_install: bool = False,
) -> dict[str, Any]:
    """Decompile WASM to C-style pseudocode with wasm2c when available."""
    if not shutil.which("wasm2c"):
        if auto_install:
            from ensure_reverse_tools import ensure_wabt

            ensure_wabt(install=True, timeout=timeout)
        if not shutil.which("wasm2c"):
            return {"ok": False, "error": "wasm2c is not installed"}
    with tempfile.TemporaryDirectory(prefix="wasm2c-") as tmp:
        wasm_path = Path(tmp) / "input.wasm"
        wasm_path.write_bytes(wasm_bytes)
        try:
            proc = subprocess.run(
                [shutil.which("wasm2c"), str(wasm_path), "-o", str(Path(tmp) / "out.c")],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": str(exc)}
        output_path = Path(tmp) / "out.c"
        if proc.returncode != 0:
            return {"ok": False, "error": (proc.stderr or "wasm2c failed")[-1000:]}
        output = output_path.read_text(encoding="utf-8", errors="replace") if output_path.exists() else ""
    return {"ok": True, "tool": "wasm2c", "pseudocode": output[:500_000]}


def run_wasm_memory_write_probe(
    wasm_bytes: bytes,
    export_names: list[str] | None = None,
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Probe exported WASM functions and return per-call memory write ranges."""
    result = run_wasm_probe(wasm_bytes, export_names=export_names, timeout=timeout)
    if not result.get("ok"):
        return result
    result["memory_write_summary"] = {
        "total_ranges": result.get("summary", {}).get("memory_ranges", 0),
        "functions_with_writes": sum(
            1 for trace in result.get("traces", []) if trace.get("memory_ranges")
        ),
    }
    return result


def wasm_memory_diff(before: bytes, after: bytes) -> list[dict[str, int]]:
    """Return changed byte ranges between two memory snapshots."""
    ranges: list[dict[str, int]] = []
    start = -1
    length = min(len(before), len(after))
    for index in range(length):
        if before[index] != after[index]:
            if start < 0:
                start = index
        elif start >= 0:
            ranges.append({"start": start, "end": index - 1, "bytes": index - start})
            start = -1
    if start >= 0:
        ranges.append({"start": start, "end": length - 1, "bytes": length - start})
    return ranges


def _self_test() -> None:
    js = wasm_hook_js("__wasm_test")
    assert "__wasm_test" in js
    assert "wasm_export_call" in js
    parsed = parse_wasm_imports_exports(b"\x00asm\x01\x00\x00\x00")
    assert parsed["ok"] is True
    print("wasm_hook self-test OK")


if __name__ == "__main__":
    _self_test()
