"""Runtime deep-reverse hook for browser pages.

The hook is installed with Playwright/Patchright ``add_init_script`` and runs
before page scripts.  It wraps ``fetch`` and ``XMLHttpRequest``, records each
request's URL / method / headers / body / call stack, and snapshots device
fingerprint plus local/session storage at call time.  The result is exposed
as ``window.__deep_reverse_hook`` and combined with the regular network
capture into one JSON report.

The JavaScript itself is dependency-free and can be printed with
``--print-hook`` and injected anywhere.  Browser execution is optional; only
the ``--url`` mode needs ``browser_session`` plus an installed engine.
"""

from __future__ import annotations

import argparse
import json
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from deep_reverse import node_available, run_js
except Exception:  # pragma: no cover - scripts directory is normally on sys.path

    def node_available() -> bool:
        return False

    run_js = None  # type: ignore[assignment]


def deep_hook_js(global_name: str = "__deep_reverse_hook") -> str:
    """Return a browser init script that captures deep request provenance."""
    return r"""
(function () {
  if (typeof window === "undefined" || window[__HOOK_GLOBAL__]) return;
  var HOOK_NAME = __HOOK_GLOBAL__;
  var records = [];
  var startedAt = Date.now();
  function truncate(value, max) {
    if (value === undefined || value === null) return null;
    try {
      var text = typeof value === "string" ? value : JSON.stringify(value);
      if (!text) return text;
      return text.length > max ? text.slice(0, max) + "..." : text;
    } catch (e) {
      return String(value);
    }
  }
  function headersObject(headers) {
    try {
      if (!headers) return {};
      if (typeof Headers !== "undefined" && headers instanceof Headers) {
        return Object.fromEntries(headers.entries());
      }
      var out = {};
      for (var key in headers) out[key] = headers[key];
      return out;
    } catch (e) {
      return {};
    }
  }
  function xhrHeaders(xhr) {
    try {
      return (xhr && xhr.__deepReverseHeaders) || {};
    } catch (e) {
      return {};
    }
  }
  function bodyText(body) {
    if (body === undefined || body === null) return null;
    if (typeof body === "string") return truncate(body, 800);
    if (typeof URLSearchParams !== "undefined" && body instanceof URLSearchParams) {
      return truncate(body.toString(), 800);
    }
    if (typeof FormData !== "undefined" && body instanceof FormData) {
      var form = {};
      body.forEach(function (value, key) { form[key] = value; });
      return truncate(JSON.stringify(form), 800);
    }
    try {
      return truncate(JSON.stringify(body), 800);
    } catch (e) {
      return truncate(String(body), 800);
    }
  }
  function stackLines() {
    try {
      return (new Error().stack || "").split("\n").slice(1, 16)
        .map(function (line) { return line.trim(); })
        .filter(Boolean);
    } catch (e) {
      return [];
    }
  }
  function deviceSnapshot() {
    var out = { navigator: {}, screen: {}, window: {}, page: {}, canvas: null, webgl: null, timezone: null };
    try {
      out.navigator = {
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        language: navigator.language,
        languages: navigator.languages,
        hardwareConcurrency: navigator.hardwareConcurrency,
        deviceMemory: navigator.deviceMemory,
        maxTouchPoints: navigator.maxTouchPoints,
        cookieEnabled: navigator.cookieEnabled,
        doNotTrack: navigator.doNotTrack,
        webdriver: navigator.webdriver,
        vendor: navigator.vendor,
        plugins: Array.prototype.slice.call(navigator.plugins || []).map(function (p) { return p.name; })
      };
    } catch (e) {}
    try {
      out.screen = {
        width: screen.width,
        height: screen.height,
        availWidth: screen.availWidth,
        availHeight: screen.availHeight,
        colorDepth: screen.colorDepth,
        pixelDepth: screen.pixelDepth,
        orientation: screen.orientation && screen.orientation.type
      };
    } catch (e) {}
    try {
      out.window = {
        devicePixelRatio: window.devicePixelRatio,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        outerWidth: window.outerWidth,
        outerHeight: window.outerHeight
      };
    } catch (e) {}
    try {
      out.page = {
        referrer: document.referrer,
        location: window.location.href,
        windowName: window.name,
        historyLength: window.history.length,
        performanceResources: performance.getEntriesByType
          ? performance.getEntriesByType("resource").slice(0, 20).map(function (entry) { return entry.name; })
          : []
      };
    } catch (e) {}
    try {
      var c = document.createElement("canvas");
      c.width = 300;
      c.height = 60;
      var ctx = c.getContext("2d");
      ctx.textBaseline = "top";
      ctx.font = "14px Arial";
      ctx.fillStyle = "#f60";
      ctx.fillRect(0, 0, 300, 60);
      ctx.fillStyle = "#069";
      ctx.fillText("deep-reverse-" + Date.now(), 2, 15);
      out.canvas = c.toDataURL().slice(0, 200);
    } catch (e) {}
    try {
      var glCanvas = document.createElement("canvas");
      var gl = glCanvas.getContext("webgl") || glCanvas.getContext("experimental-webgl");
      if (gl) {
        var ext = gl.getExtension("WEBGL_debug_renderer_info");
        out.webgl = {
          vendor: gl.getParameter(ext ? ext.UNMASKED_VENDOR_WEBGL : gl.VENDOR),
          renderer: gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER)
        };
      }
    } catch (e) {}
    try {
      out.timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch (e) {}
    return out;
  }
  function storageSnapshot() {
    var out = { local: {}, session: {} };
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i);
        out.local[key] = truncate(localStorage.getItem(key), 200);
      }
    } catch (e) {}
    try {
      for (var j = 0; j < sessionStorage.length; j++) {
        var skey = sessionStorage.key(j);
        out.session[skey] = truncate(sessionStorage.getItem(skey), 200);
      }
    } catch (e) {}
    return out;
  }
  function timingFor(url) {
    try {
      if (!performance || !performance.getEntriesByName) return null;
      var entries = performance.getEntriesByName(url);
      if (!entries || !entries.length) return null;
      var entry = entries[entries.length - 1];
      return {
        startTime: entry.startTime,
        duration: entry.duration,
        responseEnd: entry.responseEnd,
        transferSize: entry.transferSize
      };
    } catch (e) {
      return null;
    }
  }
  function record(kind, method, url, headers, body) {
    try {
      records.push({
        kind: kind,
        method: method,
        url: truncate(url, 800),
        headers: headersObject(headers),
        body: bodyText(body),
        stack: stackLines(),
        captured_at_ms: Date.now(),
        performance_ms: performance.now(),
        cookies: truncate(document.cookie, 2000),
        resource_timing: timingFor(url),
        device: deviceSnapshot(),
        storage: storageSnapshot()
      });
    } catch (e) {}
  }
  var origFetch = window.fetch;
  if (origFetch) {
    window.fetch = function (input, init) {
      try {
        var isRequest = typeof input !== "string" && input && typeof input.url === "string";
        var url = isRequest ? input.url : String(input);
        var method = (init && init.method) || (isRequest && input.method) || "GET";
        var headers = (init && init.headers) || (isRequest && input.headers) || {};
        var body = init && "body" in init ? init.body : (isRequest && "body" in input ? input.body : undefined);
        record("fetch", method, url, headers, body);
      } catch (e) {}
      return origFetch.apply(this, arguments);
    };
  }
  var origOpen = XMLHttpRequest.prototype.open;
  var origSend = XMLHttpRequest.prototype.send;
  var origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.open = function (method, url, asyncFlag, user, password) {
    try { this.__deepReverse = { method: method, url: url, headers: {} }; } catch (e) {}
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    try {
      if (this.__deepReverse) this.__deepReverse.headers[name] = value;
    } catch (e) {}
    return origSetHeader.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    try {
      var meta = this.__deepReverse;
      if (meta) record("xhr", meta.method, meta.url, xhrHeaders(this), body);
    } catch (e) {}
    return origSend.apply(this, arguments);
  };
  var NativeWebSocket = window.WebSocket;
  if (NativeWebSocket) {
    function DeepWebSocket(url, protocols) {
      var ws = protocols === undefined
        ? new NativeWebSocket(url)
        : new NativeWebSocket(url, protocols);
      var send = ws.send.bind(ws);
      ws.send = function (data) {
        try { record("websocket", "WS", url, {}, data); } catch (e) {}
        return send(data);
      };
      return ws;
    }
    DeepWebSocket.prototype = NativeWebSocket.prototype;
    DeepWebSocket.CONNECTING = NativeWebSocket.CONNECTING;
    DeepWebSocket.OPEN = NativeWebSocket.OPEN;
    DeepWebSocket.CLOSING = NativeWebSocket.CLOSING;
    DeepWebSocket.CLOSED = NativeWebSocket.CLOSED;
    window.WebSocket = DeepWebSocket;
  }
  var origSendBeacon = navigator.sendBeacon && navigator.sendBeacon.bind(navigator);
  if (origSendBeacon) {
    navigator.sendBeacon = function (url, data) {
      try { record("beacon", "POST", url, {}, data); } catch (e) {}
      return origSendBeacon.apply(this, arguments);
    };
  }
  var NativeEventSource = window.EventSource;
  if (NativeEventSource) {
    function DeepEventSource(url, config) {
      var es = config === undefined
        ? new NativeEventSource(url)
        : new NativeEventSource(url, config);
      try { record("eventsource", "GET", url, {}, null); } catch (e) {}
      return es;
    }
    DeepEventSource.prototype = NativeEventSource.prototype;
    DeepEventSource.CONNECTING = NativeEventSource.CONNECTING;
    DeepEventSource.OPEN = NativeEventSource.OPEN;
    DeepEventSource.CLOSED = NativeEventSource.CLOSED;
    window.EventSource = DeepEventSource;
  }
  try {
    Object.defineProperty(window, HOOK_NAME, {
      value: {
        started_at: startedAt,
        requests: records,
        snapshot: function () {
          return {
            device: deviceSnapshot(),
            storage: storageSnapshot(),
            cookies: truncate(document.cookie, 2000)
          };
        }
      },
      configurable: false,
      enumerable: false,
      writable: false
    });
  } catch (e) {
    window[HOOK_NAME] = {
      started_at: startedAt,
      requests: records,
      snapshot: function () {
        return {
          device: deviceSnapshot(),
          storage: storageSnapshot(),
          cookies: truncate(document.cookie, 2000)
        };
      }
    };
  }
})();
""".strip().replace("__HOOK_GLOBAL__", json.dumps(global_name))


@dataclass
class DeepHookCapture:
    url: str = ""
    hook: dict[str, Any] = field(default_factory=dict)
    function_probes: dict[str, Any] = field(default_factory=dict)
    wasm_calls: dict[str, Any] = field(default_factory=dict)
    native_probes: dict[str, Any] = field(default_factory=dict)
    network: list[dict[str, Any]] = field(default_factory=list)
    html_size: int = 0
    ok: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "ok": self.ok,
            "error": self.error,
            "hook": self.hook,
            "function_probes": self.function_probes,
            "wasm_calls": self.wasm_calls,
            "native_probes": self.native_probes,
            "network": self.network,
            "html_size": self.html_size,
            "summary": {
                "hook_requests": len((self.hook or {}).get("requests", [])),
                "function_calls": len(
                    (self.function_probes or {}).get("function_calls", [])
                ),
                "wasm_calls": len((self.wasm_calls or {}).get("wasm_calls", [])),
                "native_calls": len(
                    (self.native_probes or {}).get("native_calls", [])
                ),
                "network_requests": len(self.network),
                "device_fields": len((self.hook or {}).get("requests", [{}])[0].get("device", {})),
            },
        }


def run_browser_hook(
    url: str,
    *,
    headless: bool = True,
    engine: str = "playwright",
    probe_patterns: list[str] | tuple[str, ...] | None = None,
    wasm_hook: bool = False,
    native_probe: bool = False,
    wait_ms: float = 5000,
    timeout_ms: float = 30000,
) -> DeepHookCapture:
    """Open a URL with the deep hook installed and return captured provenance."""
    try:
        from browser_session import BrowserSession, NetworkCaptureOptions
    except Exception as exc:
        return DeepHookCapture(url=url, ok=False, error=f"browser dependencies unavailable: {exc}")

    session = BrowserSession(
        headless=headless,
        engine=engine,
        auto_install=False,
        deep_hook=True,
        function_probe_patterns=probe_patterns,
        wasm_hook=wasm_hook,
        native_probe=native_probe,
    )
    try:
        session.start()
        if session.context is None:
            return DeepHookCapture(url=url, ok=False, error="browser context is None")
        session.start_capture(NetworkCaptureOptions(include_headers=True, include_bodies=True))
        session.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        if session.page is not None:
            with suppress(Exception):
                session.page.wait_for_load_state("networkidle", timeout=wait_ms)
        hook: Any = None
        html = ""
        if session.page is not None:
            hook = session.capture_deep_hook()
            function_probes = session.capture_function_probes()
            wasm_calls = session.capture_wasm_calls()
            native_probes = session.capture_native_probes()
            html = session.page.content()
        network = [entry.to_dict(include_body=True) for entry in session.stop_capture()]
        return DeepHookCapture(
            url=url,
            hook=hook or {},
            function_probes=function_probes,
            wasm_calls=wasm_calls,
            native_probes=native_probes,
            network=network,
            html_size=len(html),
            ok=True,
        )
    except Exception as exc:
        return DeepHookCapture(url=url, ok=False, error=str(exc))
    finally:
        session.close()


def _self_test() -> int:
    hook = deep_hook_js()
    assert "window.fetch" in hook
    assert "XMLHttpRequest.prototype.open" in hook
    assert "NativeWebSocket" in hook
    assert "deviceSnapshot" in hook
    if node_available() and run_js is not None:
        result = run_js(hook + "\nconsole.log(typeof window);")
        assert result["ok"], result.get("stderr") or result.get("error")
    print("deep_hook self-test OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deep runtime reverse hook for browsers")
    parser.add_argument("--url", default=None, help="page URL to open with the hook")
    parser.add_argument("--print-hook", action="store_true", help="print the hook JavaScript")
    parser.add_argument("--headless", action="store_true", default=True, help="run headless")
    parser.add_argument("--no-headless", action="store_true", help="run headed")
    parser.add_argument("--engine", default="playwright", help="playwright or patchright")
    parser.add_argument(
        "--probe-patterns",
        default="",
        help="comma-separated function name patterns to wrap with the probe",
    )
    parser.add_argument(
        "--wasm-hook",
        action="store_true",
        help="install the WASM export-call hook",
    )
    parser.add_argument(
        "--native-probe",
        action="store_true",
        help="install the native API probe (Date.now/crypto.subtle/TextEncoder/storage)",
    )
    parser.add_argument("--wait-ms", type=float, default=5000, help="networkidle wait")
    parser.add_argument("--timeout-ms", type=float, default=30000, help="page load timeout")
    parser.add_argument("--output", default=None, help="write capture JSON")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()
    if args.print_hook:
        print(deep_hook_js())
        return 0
    if not args.url:
        parser.error("--url is required unless --print-hook / --self-test is used")

    capture = run_browser_hook(
        args.url,
        headless=not args.no_headless,
        engine=args.engine,
        probe_patterns=[item.strip() for item in args.probe_patterns.split(",") if item.strip()],
        wasm_hook=args.wasm_hook,
        native_probe=args.native_probe,
        wait_ms=args.wait_ms,
        timeout_ms=args.timeout_ms,
    )
    text = json.dumps(capture.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if capture.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
