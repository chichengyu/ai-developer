"""Deep Turnstile container detection and solving for authorized automation.

Handles the common Cloudflare Turnstile container variants:

- `div.cf-turnstile` with `data-sitekey`
- explicit `turnstile.render(...)` widgets
- iframe-based interactive / non-interactive challenges
- Shadow DOM checkbox containers
- `execution: "execute"` widgets that require a programmatic execute call

The solver can auto-click, wait for the hidden response token, or inject a
token returned by a third-party CAPTCHA provider.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_SITEKEY_ATTR_RE = re.compile(r"data-sitekey=['\"]([^'\"]+)['\"]", re.IGNORECASE)
_IFRAME_SRC_RE = re.compile(r"<iframe[^>]+src=['\"]([^'\"]+)['\"]", re.IGNORECASE)
_RENDER_CALL_RE = re.compile(r"(?:window\.)?turnstile\.render\s*\(", re.IGNORECASE)
_READY_CALL_RE = re.compile(
    r"(?:window\.)?turnstile\.ready\s*\(",
    re.IGNORECASE,
)
_VAR_DECL_RE = re.compile(
    r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(['\"])([^'\"]*)\2",
)
_VAR_ASSIGN_RE = re.compile(
    r"(?:^|[;,\s])([A-Za-z_$][\w$]*)\s*=\s*(['\"])([^'\"]*)\2",
)
_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


def _split_top_level(text: str, separator: str = ",") -> list[str]:
    """Split JS-ish text at the top-level separator."""
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == separator and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_string_literal(value: str) -> str | None:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"', "`"}:
        try:
            return bytes(value[1:-1], "utf-8").decode("unicode_escape")
        except Exception:
            return value[1:-1]
    return None


def _parse_js_object(text: str) -> dict[str, str]:
    """Parse a small JS object literal into string values."""
    result: dict[str, str] = {}
    object_text = text.strip()
    if object_text.startswith("{"):
        object_text = object_text[1:]
    if object_text.endswith("}"):
        object_text = object_text[:-1]
    for item in _split_top_level(object_text, ","):
        if not item:
            continue
        pair = _split_top_level(item, ":")
        if len(pair) < 2:
            continue
        key = pair[0].strip().strip("'\"")
        value = ":".join(pair[1:]).strip()
        literal = _parse_string_literal(value)
        if literal is not None:
            result[key] = literal
        else:
            result[key] = value
    return result


def _find_render_calls(script: str) -> list[tuple[str, dict[str, str], bool]]:
    """Find `turnstile.render` calls and return (container, options, inline_callback)."""
    calls: list[tuple[str, dict[str, str], bool]] = []
    for match in _RENDER_CALL_RE.finditer(script):
        index = match.end()
        depth = 1
        quote: str | None = None
        escaped = False
        while index < len(script):
            char = script[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in {"'", '"', "`"}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        inner = script[match.end() : index]
        args = _split_top_level(inner, ",")
        container = ""
        options: dict[str, str] = {}
        if len(args) >= 1:
            container = args[0].strip().strip("'\"")
        if len(args) >= 2:
            options = _parse_js_object(args[1])
        inline_callback = bool(
            (options.get("callback") or "").lstrip().startswith(("function", "("))
        )
        calls.append((container, options, inline_callback))
    return calls


def _script_variables(script: str) -> dict[str, str]:
    variables: dict[str, str] = {}
    for match in _VAR_DECL_RE.finditer(script):
        variables[match.group(1)] = match.group(3)
    for match in _VAR_ASSIGN_RE.finditer(script):
        variables.setdefault(match.group(1), match.group(3))
    return variables


def _resolve_option(value: str, variables: dict[str, str]) -> str:
    candidate = value.strip()
    if _IDENT_RE.match(candidate) and candidate in variables:
        return variables[candidate]
    return candidate


@dataclass
class TurnstileWidget:
    index: int = 0
    sitekey: str | None = None
    selector: str = "div.cf-turnstile"
    iframe_selector: str = "iframe[src*='challenges.cloudflare.com']"
    widget_id: str | None = None
    container_selector: str | None = None
    action: str | None = None
    callback: str | None = None
    error_callback: str | None = None
    expired_callback: str | None = None
    execution: str = "render"
    size: str = "normal"
    theme: str = "auto"
    appearance: str = "always"
    frame_url: str | None = None
    is_inline_callback: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "sitekey": self.sitekey,
            "selector": self.selector,
            "iframe_selector": self.iframe_selector,
            "widget_id": self.widget_id,
            "container_selector": self.container_selector,
            "action": self.action,
            "callback": self.callback,
            "error_callback": self.error_callback,
            "expired_callback": self.expired_callback,
            "execution": self.execution,
            "size": self.size,
            "theme": self.theme,
            "appearance": self.appearance,
            "frame_url": self.frame_url,
            "is_inline_callback": self.is_inline_callback,
        }


@dataclass
class TurnstileSolveResult:
    passed: bool = False
    widget: TurnstileWidget | None = None
    token: str | None = None
    strategy: str = "none"
    attempts: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "widget": self.widget.to_dict() if self.widget else None,
            "token": self.token,
            "strategy": self.strategy,
            "attempts": self.attempts,
            "errors": list(self.errors),
        }


class _TurnstileParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.widgets: list[dict[str, Any]] = []
        self.scripts: list[str] = []
        self._script: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if (
            tag in {"div", "form", "span", "section", "article"}
            and "cf-turnstile" in attr_map.get("class", "").split()
            and "data-sitekey" in attr_map
        ):
            self.widgets.append(
                {
                    key[len("data-") :]: value
                    for key, value in attr_map.items()
                    if key.startswith("data-")
                }
            )
        elif tag == "script":
            self._script = []
            self._in_script = True

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            self.scripts.append("".join(self._script))
            self._in_script = False


def _attrs_to_widget(
    index: int,
    attrs: dict[str, str],
    *,
    iframe_selector: str,
) -> TurnstileWidget:
    return TurnstileWidget(
        index=index,
        sitekey=attrs.get("sitekey") or None,
        selector="div.cf-turnstile",
        iframe_selector=iframe_selector,
        action=attrs.get("action") or None,
        callback=attrs.get("callback") or None,
        error_callback=attrs.get("error-callback") or None,
        expired_callback=attrs.get("expired-callback") or None,
        execution=attrs.get("execution") or "render",
        size=attrs.get("size") or "normal",
        theme=attrs.get("theme") or "auto",
        appearance=attrs.get("appearance") or "always",
    )


def detect_turnstile_widgets(
    html: str,
    page_url: str | None = None,
) -> list[TurnstileWidget]:
    """Detect Turnstile widgets from DOM containers and render scripts."""
    parser = _TurnstileParser()
    parser.feed(html)
    widgets: list[TurnstileWidget] = []
    seen: set[tuple[str, str]] = set()
    iframe_sources = [
        src
        for src in _IFRAME_SRC_RE.findall(html)
        if "challenges.cloudflare.com" in src or "turnstile" in src.lower()
    ]
    iframe_selector = (
        "iframe[src*='challenges.cloudflare.com']"
        if iframe_sources
        else "iframe[src*='turnstile']"
    )
    for index, raw in enumerate(parser.widgets):
        attrs = raw
        if "sitekey" not in attrs:
            continue
        widget = _attrs_to_widget(index, attrs, iframe_selector=iframe_selector)
        key = (widget.sitekey or "", widget.action or "")
        if key in seen:
            continue
        seen.add(key)
        widgets.append(widget)
    for script in parser.scripts:
        variables = _script_variables(script)
        for container, options, inline_callback in _find_render_calls(script):
            sitekey = _resolve_option(options.get("sitekey", ""), variables) or None
            action = _resolve_option(options.get("action", ""), variables) or None
            callback = _resolve_option(options.get("callback", ""), variables) or None
            widget = TurnstileWidget(
                index=len(widgets),
                sitekey=sitekey,
                selector="div.cf-turnstile",
                iframe_selector=iframe_selector,
                widget_id=container if _IDENT_RE.fullmatch(container) else None,
                container_selector=(
                    f"#{container}"
                    if container and _IDENT_RE.fullmatch(container)
                    else container if container.startswith(("#", ".")) else None
                ),
                action=action,
                callback=callback,
                error_callback=options.get("error-callback"),
                expired_callback=options.get("expired-callback"),
                execution=options.get("execution", "render"),
                size=options.get("size", "normal"),
                theme=options.get("theme", "auto"),
                appearance=options.get("appearance", "always"),
                is_inline_callback=inline_callback,
            )
            key = (widget.sitekey or "", widget.action or "")
            if widget.sitekey and key not in seen:
                seen.add(key)
                widgets.append(widget)
    for src in iframe_sources:
        parsed = urllib.parse.urlsplit(src)
        params = urllib.parse.parse_qs(parsed.query)
        sitekey = (params.get("sitekey") or params.get("k") or [None])[0]
        if not sitekey:
            continue
        widget = TurnstileWidget(
            index=len(widgets),
            sitekey=sitekey,
            selector="div.cf-turnstile",
            iframe_selector=f"iframe[src*='{parsed.hostname}']",
            frame_url=src,
            execution="render",
        )
        key = (widget.sitekey or "", widget.action or "")
        if key not in seen:
            seen.add(key)
            widgets.append(widget)
    return widgets


class TurnstileSolver:
    """Solve one or more Turnstile containers through a Playwright page."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        captcha_solver: Any | None = None,
    ) -> None:
        cfg = dict(config or {})
        self.auto_click = bool(cfg.get("auto_click", True))
        self.wait_timeout = float(cfg.get("wait_timeout", 30000))
        self.poll_interval = float(cfg.get("poll_interval", 0.5))
        self.max_attempts = max(1, int(cfg.get("max_attempts", 3)))
        self.captcha_solver = captcha_solver

    def detect(self, page: Any, page_url: str | None = None) -> list[TurnstileWidget]:
        try:
            html = page.content()
        except Exception:
            return []
        widgets = detect_turnstile_widgets(html, page_url or getattr(page, "url", None))
        if widgets:
            return widgets
        try:
            return self._detect_in_page(page, page_url or getattr(page, "url", None))
        except Exception:
            return []

    def _detect_in_page(
        self,
        page: Any,
        page_url: str | None = None,
    ) -> list[TurnstileWidget]:
        """Detect widgets rendered dynamically, including Shadow DOM containers."""
        script = """
        () => {
          const found = [];
          const seen = new WeakSet();
          function visit(root) {
            if (!root || seen.has(root)) return;
            seen.add(root);
            try {
              const nodes = root.querySelectorAll
                ? root.querySelectorAll("[data-sitekey]")
                : [];
              for (const el of nodes) {
                const cls = el.className || "";
                if (!String(cls).includes("cf-turnstile") && el.tagName !== "FORM") continue;
                found.push({
                  sitekey: el.getAttribute("data-sitekey") || "",
                  action: el.getAttribute("data-action") || "",
                  callback: el.getAttribute("data-callback") || "",
                  error_callback: el.getAttribute("data-error-callback") || "",
                  expired_callback: el.getAttribute("data-expired-callback") || "",
                  execution: el.getAttribute("data-execution") || "render",
                  size: el.getAttribute("data-size") || "normal",
                  theme: el.getAttribute("data-theme") || "auto",
                  appearance: el.getAttribute("data-appearance") || "always"
                });
              }
            } catch (e) {}
            if (root.shadowRoot) visit(root.shadowRoot);
            if (root.children) {
              for (const child of root.children) visit(child);
            }
          }
          visit(document);
          return found;
        }
        """
        raw = page.evaluate(script) if hasattr(page, "evaluate") else []
        widgets: list[TurnstileWidget] = []
        seen: set[tuple[str, str]] = set()
        for item in raw or []:
            sitekey = str(item.get("sitekey") or "")
            if not sitekey:
                continue
            widget = TurnstileWidget(
                index=len(widgets),
                sitekey=sitekey,
                action=item.get("action") or None,
                callback=item.get("callback") or None,
                error_callback=item.get("error_callback") or None,
                expired_callback=item.get("expired_callback") or None,
                execution=item.get("execution") or "render",
                size=item.get("size") or "normal",
                theme=item.get("theme") or "auto",
                appearance=item.get("appearance") or "always",
                iframe_selector="iframe[src*='challenges.cloudflare.com']",
            )
            key = (sitekey, widget.action or "")
            if key in seen:
                continue
            seen.add(key)
            widgets.append(widget)
        return widgets

    def solve_page(
        self,
        page: Any,
        url: str,
        *,
        widgets: list[TurnstileWidget] | None = None,
    ) -> TurnstileSolveResult:
        widgets = widgets if widgets is not None else self.detect(page, url)
        if not widgets:
            if self.auto_click and self._click_managed_challenge(page, url):
                return TurnstileSolveResult(
                    passed=False,
                    strategy="managed_click",
                    attempts=1,
                )
            return TurnstileSolveResult(strategy="none")
        errors: list[str] = []
        for widget in widgets:
            result = self.solve_widget(page, url, widget)
            errors.extend(result.errors)
            if result.passed:
                return result
        return TurnstileSolveResult(
            passed=False,
            widget=widgets[0],
            strategy="none",
            errors=errors,
        )

    def _click_managed_challenge(self, page: Any, url: str) -> bool:
        from challenge_click import click_managed_challenge

        return click_managed_challenge(page)

    def solve_widget(
        self,
        page: Any,
        url: str,
        widget: TurnstileWidget,
    ) -> TurnstileSolveResult:
        errors: list[str] = []
        if self.captcha_solver is not None and widget.sitekey:
            try:
                answer = self.captcha_solver.solve_turnstile(widget.sitekey, url)
                token = str(getattr(answer, "answer", "") or "")
                if token:
                    if self._inject_token(page, widget, token):
                        return TurnstileSolveResult(
                            passed=True,
                            widget=widget,
                            token=token,
                            strategy="token_inject",
                            attempts=1,
                        )
                    errors.append("token injection failed")
            except Exception as exc:
                errors.append(f"provider: {exc}")
        for attempt in range(self.max_attempts):
            self._wait_for_widget_ready(page)
            token = self._wait_for_token(page, widget, timeout_ms=min(2000, self.wait_timeout))
            if token:
                return TurnstileSolveResult(
                    passed=True,
                    widget=widget,
                    token=token,
                    strategy="non_interactive_wait",
                    attempts=attempt + 1,
                    errors=errors,
                )
            if widget.execution == "execute":
                self._execute_widget(page, widget)
                strategy = "execute"
            elif self.auto_click:
                self._click_widget(page, widget)
                strategy = "auto_click"
            else:
                strategy = "none"
            if strategy == "none":
                return TurnstileSolveResult(
                    widget=widget,
                    strategy="none",
                    errors=errors,
                )
            token = self._wait_for_token(page, widget)
            if token:
                return TurnstileSolveResult(
                    passed=True,
                    widget=widget,
                    token=token,
                    strategy=strategy,
                    attempts=attempt + 1,
                    errors=errors,
                )
            time.sleep(self.poll_interval)
        return TurnstileSolveResult(
            widget=widget,
            strategy="none",
            attempts=self.max_attempts,
            errors=errors + ["no Turnstile token appeared"],
        )

    def _click_widget(self, page: Any, widget: TurnstileWidget) -> bool:
        from challenge_click import human_click

        candidates = []
        if widget.sitekey:
            with suppress(Exception):
                candidates.append(page.locator(f"[data-sitekey='{widget.sitekey}']").first)
        with suppress(Exception):
            candidates.append(page.locator(widget.selector).nth(widget.index))
        with suppress(Exception):
            candidates.append(page.locator(widget.iframe_selector).nth(widget.index))
        for locator in candidates:
            if human_click(locator, page):
                return True
        try:
            for frame in list(getattr(page, "frames", []) or []):
                frame_url = str(getattr(frame, "url", "") or "")
                if "challenges.cloudflare.com" not in frame_url:
                    continue
                if human_click(frame.locator("input[type='checkbox']").first, frame):
                    return True
        except Exception:
            pass
        return self._click_shadow_dom(page)

    def _execute_widget(self, page: Any, widget: TurnstileWidget) -> bool:
        script = """
        (args) => {
          if (!window.turnstile) return false;
          try {
            const params = args.action ? {action: args.action} : {};
            if (args.widget_id) {
              const isSelector =
                args.widget_id.startsWith("#") || args.widget_id.startsWith(".");
              const el = isSelector ? document.querySelector(args.widget_id) : null;
              window.turnstile.execute(el || args.widget_id, params);
              return true;
            }
            if (args.sitekey) {
              const el = document.querySelector(`[data-sitekey='${args.sitekey}']`);
              if (el) {
                window.turnstile.execute(el, params);
                return true;
              }
            }
            window.turnstile.execute();
            return true;
          } catch (e) {
            return false;
          }
        }
        """
        try:
            return bool(
                page.evaluate(
                    script,
                    {
                        "widget_id": widget.widget_id,
                        "sitekey": widget.sitekey,
                        "action": widget.action,
                    },
                )
            )
        except Exception:
            with suppress(Exception):
                page.evaluate("() => { if (window.turnstile) window.turnstile.execute(); }")
                return True
            return False

    def _wait_for_widget_ready(self, page: Any, timeout: float = 8000) -> bool:
        deadline = time.monotonic() + timeout / 1000.0
        script = """
        () => {
          const ready =
            document.querySelector("[data-sitekey]") ||
            document.querySelector("iframe[src*='challenges.cloudflare.com']") ||
            document.querySelector("textarea[name='cf-turnstile-response']");
          return Boolean(ready);
        }
        """
        while time.monotonic() < deadline:
            try:
                if page.evaluate(script):
                    return True
            except Exception:
                pass
            time.sleep(min(0.5, self.poll_interval))
        return False

    def _click_shadow_dom(self, page: Any) -> bool:
        from challenge_click import click_shadow_dom

        return click_shadow_dom(page)

    def _wait_for_token(
        self,
        page: Any,
        widget: TurnstileWidget,
        timeout_ms: float | None = None,
    ) -> str | None:
        deadline = time.monotonic() + (timeout_ms or self.wait_timeout) / 1000.0
        while time.monotonic() < deadline:
            try:
                token = self._read_token(page)
                if token:
                    return token
            except Exception:
                pass
            try:
                for frame in list(getattr(page, "frames", []) or []):
                    token = self._read_token(frame)
                    if token:
                        return token
            except Exception:
                pass
            time.sleep(self.poll_interval)
        return None

    def _read_token(self, page: Any) -> str | None:
        script = """
        () => {
          const selectors = [
            "textarea[name='cf-turnstile-response']",
            "textarea#cf-turnstile-response",
            "input[name='cf-turnstile-response']",
            "[name='cf-turnstile-response']"
          ];
          const seen = new WeakSet();
          function visit(root) {
            if (!root || seen.has(root)) return "";
            seen.add(root);
            for (const selector of selectors) {
              try {
                const nodes = root.querySelectorAll ? root.querySelectorAll(selector) : [];
                for (const el of nodes) {
                  if (el.value) return el.value;
                }
              } catch (e) {}
            }
            if (root.shadowRoot) {
              const value = visit(root.shadowRoot);
              if (value) return value;
            }
            if (root.documentElement) {
              const value = visit(root.documentElement);
              if (value) return value;
            }
            if (root.children) {
              for (const child of root.children) {
                const value = visit(child);
                if (value) return value;
              }
            }
            return "";
          }
          const rootValue = visit(document);
          if (rootValue) return rootValue;
          try {
            const frames = document.querySelectorAll("iframe");
            for (const frame of frames) {
              try {
                if (frame.contentDocument) {
                  const value = visit(frame.contentDocument);
                  if (value) return value;
                }
              } catch (e) {}
            }
          } catch (e) {}
          if (window.__cfTurnstileToken) return window.__cfTurnstileToken;
          return "";
        }
        """
        try:
            value = str(page.evaluate(script) or "")
            return value or None
        except Exception:
            return None

    def _inject_token(self, page: Any, widget: TurnstileWidget, token: str) -> bool:
        script = """
        (value) => {
          const selectors = [
            "textarea[name='cf-turnstile-response']",
            "textarea#cf-turnstile-response",
            "input[name='cf-turnstile-response']",
            "[name='cf-turnstile-response']"
          ];
          let found = false;
          const seen = new WeakSet();
          function visit(root) {
            if (!root || seen.has(root)) return;
            seen.add(root);
            for (const selector of selectors) {
              try {
                const nodes = root.querySelectorAll ? root.querySelectorAll(selector) : [];
                for (const el of nodes) {
                  el.value = value;
                  el.dispatchEvent(new Event("input", {bubbles: true}));
                  el.dispatchEvent(new Event("change", {bubbles: true}));
                  found = true;
                }
              } catch (e) {}
            }
            if (root.shadowRoot) visit(root.shadowRoot);
            if (root.children) {
              for (const child of root.children) visit(child);
            }
          }
          if (window.turnstile && window.turnstile.reset) {
            try { window.turnstile.reset(); } catch (e) {}
          }
          visit(document);
          window.__cfTurnstileToken = value;
          return true;
        }
        """
        try:
            if not page.evaluate(script, token):
                return False
        except Exception:
            return False
        callback = widget.callback or ""
        if callback and not widget.is_inline_callback:
            expression = _callback_expression(callback)
            if expression:
                with suppress(Exception):
                    page.evaluate(
                        f"({expression}) && typeof ({expression}) === 'function' "
                        f"&& ({expression})({json.dumps(token)})"
                    )
        return True


def _callback_expression(callback: str) -> str:
    parts = str(callback).split(".")
    if not parts or any(not _IDENT_RE.fullmatch(part) for part in parts):
        return ""
    expression = "window"
    for part in parts:
        expression += f"[{json.dumps(part)}]"
    return expression


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Detect Turnstile widgets in HTML")
    parser.add_argument("--html", required=True, help="HTML file path")
    args = parser.parse_args(argv)
    html = Path(args.html).read_text(encoding="utf-8")
    widgets = detect_turnstile_widgets(html)
    print(json.dumps([widget.to_dict() for widget in widgets], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
