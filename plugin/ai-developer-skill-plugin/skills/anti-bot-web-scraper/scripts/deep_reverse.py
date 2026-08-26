"""Deep reverse-engineering analysis for protected web scripts.

The module is deliberately dependency-free for the common path: it extracts
inline JavaScript, detects common obfuscation families, applies conservative
deobfuscation passes, locates API request construction sites, and identifies
the functions most likely to build signatures, tokens, hashes, and encrypted
payloads.  When Node.js is available it can also execute an extracted
expression or a named signature function in a local child process.

Optional integrations are used only when already installed:

- ``jsbeautifier`` is used for the beautify pass when present.
- ``node`` is used for ``--eval`` / ``--run-function`` when present.

This module complements ``page_data_parser`` / ``api_analyzer``: it focuses on
the "why does this request work" layer instead of the "what is this request"
layer.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    from page_data_parser import analyze_page  # type: ignore
except Exception:  # pragma: no cover - scripts directory is normally on sys.path
    analyze_page = None  # type: ignore[assignment]


MAX_SCRIPT_BYTES = 4 * 1024 * 1024
MAX_SNIPPET = 600


@dataclass
class ScriptSource:
    """One inline or external JavaScript source discovered in a page."""

    url: str | None = None
    content: str = ""
    inline: bool = True
    script_type: str | None = None
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "inline": self.inline,
            "type": self.script_type,
            "name": self.name,
            "size": len(self.content),
        }


@dataclass
class ObfuscationSignal:
    name: str
    count: int
    examples: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "count": self.count, "examples": self.examples[:3]}


@dataclass
class ObfuscationProfile:
    score: float = 0.0
    level: str = "clean"
    signals: list[ObfuscationSignal] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "level": self.level,
            "signals": [signal.to_dict() for signal in self.signals],
        }


@dataclass
class CryptoCall:
    algorithm: str
    expression: str
    line: int
    context: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "expression": self.expression,
            "line": self.line,
            "context": self.context[:220],
        }


@dataclass
class DynamicField:
    name: str
    kind: str
    expression: str
    confidence: float
    source: str = "js"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "expression": self.expression,
            "confidence": round(self.confidence, 2),
            "source": self.source,
        }


@dataclass
class DataFlowLink:
    source: str
    source_kind: str
    variable: str
    target: str
    target_kind: str
    line: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_kind": self.source_kind,
            "variable": self.variable,
            "target": self.target,
            "target_kind": self.target_kind,
            "line": self.line,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class RequestSite:
    method: str
    url: str
    line: int
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = None
    params: dict[str, Any] = field(default_factory=dict)
    dynamic_fields: list[DynamicField] = field(default_factory=list)
    crypto_calls: list[CryptoCall] = field(default_factory=list)
    source: str = "js"
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "line": self.line,
            "headers": self.headers,
            "body": self.body,
            "params": self.params,
            "dynamic_fields": [item.to_dict() for item in self.dynamic_fields],
            "crypto_calls": [item.to_dict() for item in self.crypto_calls],
            "source": self.source,
            "raw": self.raw[:400],
        }


@dataclass
class SignatureCandidate:
    name: str
    algorithm: str
    snippet: str
    line: int
    calls: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "algorithm": self.algorithm,
            "snippet": self.snippet[:MAX_SNIPPET],
            "line": self.line,
            "calls": self.calls,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class DeviceFingerprintField:
    name: str
    category: str
    expression: str
    line: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "expression": self.expression[:220],
            "line": self.line,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class TimestampField:
    name: str
    source: str
    unit: str
    line: int
    context: str
    confidence: float
    request_params: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source": self.source,
            "unit": self.unit,
            "line": self.line,
            "context": self.context[:220],
            "confidence": round(self.confidence, 2),
            "request_params": self.request_params[:20],
        }


@dataclass
class SignatureRecipe:
    function_name: str
    algorithm: str
    parameter_order: list[str]
    secret_keys: list[str]
    encoding: str
    snippet: str
    line: int
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_name": self.function_name,
            "algorithm": self.algorithm,
            "parameter_order": self.parameter_order,
            "secret_keys": self.secret_keys,
            "encoding": self.encoding,
            "snippet": self.snippet[:MAX_SNIPPET],
            "line": self.line,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class DeobfuscationResult:
    output: str
    passes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "passes": self.passes,
            "size": len(self.output),
        }


@dataclass
class JsAnalysis:
    url: str | None = None
    bundle: dict[str, Any] = field(default_factory=dict)
    obfuscation: ObfuscationProfile = field(default_factory=ObfuscationProfile)
    crypto_calls: list[CryptoCall] = field(default_factory=list)
    request_sites: list[RequestSite] = field(default_factory=list)
    signature_candidates: list[SignatureCandidate] = field(default_factory=list)
    device_fields: list[DeviceFingerprintField] = field(default_factory=list)
    timestamp_fields: list[TimestampField] = field(default_factory=list)
    signature_recipes: list[SignatureRecipe] = field(default_factory=list)
    dynamic_fields: list[DynamicField] = field(default_factory=list)
    data_flow: list[DataFlowLink] = field(default_factory=list)
    ast_data_flow: list[dict[str, Any]] = field(default_factory=list)
    ast_data_flow_ok: bool = False
    deobfuscated: DeobfuscationResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "bundle": self.bundle,
            "obfuscation": self.obfuscation.to_dict(),
            "crypto_calls": [item.to_dict() for item in self.crypto_calls],
            "request_sites": [item.to_dict() for item in self.request_sites],
            "signature_candidates": [item.to_dict() for item in self.signature_candidates],
            "device_fields": [item.to_dict() for item in self.device_fields],
            "timestamp_fields": [item.to_dict() for item in self.timestamp_fields],
            "signature_recipes": [item.to_dict() for item in self.signature_recipes],
            "dynamic_fields": [item.to_dict() for item in self.dynamic_fields],
            "data_flow": [item.to_dict() for item in self.data_flow],
            "ast_data_flow": self.ast_data_flow,
            "ast_data_flow_ok": self.ast_data_flow_ok,
            "deobfuscated": self.deobfuscated.to_dict() if self.deobfuscated else None,
        }


@dataclass
class CapturedRequest:
    method: str
    url: str
    resource_type: str
    status: int | None
    post_data: str | None
    dynamic_fields: list[DynamicField] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "resource_type": self.resource_type,
            "status": self.status,
            "post_data": self.post_data,
            "dynamic_fields": [item.to_dict() for item in self.dynamic_fields],
        }


@dataclass
class ReverseReport:
    url: str | None = None
    scripts: list[ScriptSource] = field(default_factory=list)
    analysis: JsAnalysis = field(default_factory=JsAnalysis)
    captured_requests: list[CapturedRequest] = field(default_factory=list)
    hook: dict[str, Any] = field(default_factory=dict)
    function_probes: dict[str, Any] = field(default_factory=dict)
    wasm_calls: dict[str, Any] = field(default_factory=dict)
    native_probes: dict[str, Any] = field(default_factory=dict)
    source_map: dict[str, Any] = field(default_factory=dict)
    bundle_cross_refs: list[dict[str, Any]] = field(default_factory=list)
    node_available: bool = False
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "scripts": [script.to_dict() for script in self.scripts],
            "analysis": self.analysis.to_dict(),
            "captured_requests": [item.to_dict() for item in self.captured_requests],
            "hook": self.hook,
            "function_probes": self.function_probes,
            "wasm_calls": self.wasm_calls,
            "native_probes": self.native_probes,
            "source_map": self.source_map,
            "bundle_cross_refs": self.bundle_cross_refs,
            "node_available": self.node_available,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# String and token helpers
# ---------------------------------------------------------------------------


def _iter_js_strings(text: str) -> Any:
    """Yield ``(start, end, quote, content, has_interpolation)`` for JS strings."""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in {"'", '"', "`"}:
            quote = ch
            start = i
            i += 1
            content: list[str] = []
            has_interp = False
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    content.append(text[i : i + 2])
                    i += 2
                    continue
                if c == quote:
                    i += 1
                    break
                if quote == "`" and c == "$" and i + 1 < n and text[i + 1] == "{":
                    has_interp = True
                content.append(c)
                i += 1
            yield start, i, quote, "".join(content), has_interp
        else:
            i += 1


def _decode_string_escapes(content: str) -> str:
    """Decode ``\\xNN`` and ``\\uNNNN`` / ``\\u{...}`` escapes in JS string content."""
    out: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = content[i + 1]
        if nxt == "x" and i + 3 < n:
            digits = content[i + 2 : i + 4]
            if re.fullmatch(r"[0-9a-fA-F]{2}", digits):
                out.append(chr(int(digits, 16)))
                i += 4
                continue
        if nxt == "u":
            if i + 2 < n and content[i + 2] == "{":
                end = content.find("}", i + 3)
                if end > i + 3 and re.fullmatch(r"[0-9a-fA-F]{1,6}", content[i + 3 : end]):
                    out.append(chr(int(content[i + 3 : end], 16)))
                    i = end + 1
                    continue
            if i + 5 < n and re.fullmatch(r"[0-9a-fA-F]{4}", content[i + 2 : i + 6]):
                out.append(chr(int(content[i + 2 : i + 6], 16)))
                i += 6
                continue
        out.append("\\")
        out.append(nxt)
        i += 2
    return "".join(out)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _context(text: str, index: int, radius: int = 160) -> str:
    return text[max(0, index - radius) : index + radius].replace("\n", " ")


# ---------------------------------------------------------------------------
# Deobfuscation passes
# ---------------------------------------------------------------------------


def decode_js_escapes(text: str) -> str:
    """Replace encoded JS string literals with readable JSON string literals."""
    replacements: list[tuple[int, int, str]] = []
    for start, end, _quote, content, has_interp in _iter_js_strings(text):
        if has_interp:
            continue
        decoded = _decode_string_escapes(content)
        if decoded != content:
            replacements.append((start, end, json.dumps(decoded, ensure_ascii=False)))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text


def decode_base64_calls(text: str) -> str:
    """Replace ``atob`` / ``Buffer.from(..., 'base64')`` literals."""

    def _replace_atob(match: re.Match[str]) -> str:
        try:
            decoded = base64.b64decode(match.group(2)).decode("utf-8")
        except Exception:
            return match.group(0)
        return json.dumps(decoded, ensure_ascii=False)

    text = re.sub(
        r"(?:window\.)?atob\s*\(\s*(['\"])([^'\"]+)\1\s*\)",
        _replace_atob,
        text,
    )
    text = re.sub(
        r"Buffer\.from\s*\(\s*(['\"])([^'\"]+)\1\s*,\s*['\"]base64['\"]\s*\)"
        r"\s*\.\s*toString\s*\(\s*\)",
        _replace_atob,
        text,
    )
    return text


_ARRAY_DECL_RE = re.compile(
    r"\b(?:var|let|const)\s+(?P<name>_0x[a-zA-Z0-9_$]{2,})\s*=\s*" r"(?P<array>\[[^\[\]]*\])\s*;?"
)
_ARRAY_INDEX_RE = re.compile(r"(?P<name>_0x[a-zA-Z0-9_$]{2,})\s*\[\s*(0x[0-9a-fA-F]+|\d+)\s*\]")


def _parse_array_literals(slice_text: str) -> list[Any]:
    items: list[tuple[int, Any]] = []
    string_ranges: list[tuple[int, int]] = []
    for start, end, _quote, content, _has_interp in _iter_js_strings(slice_text):
        string_ranges.append((start, end))
        items.append((start, _decode_string_escapes(content)))
    for match in re.finditer(r"(?<![\w$])(-?\d+(?:\.\d+)?)(?![\w$])", slice_text):
        if any(start <= match.start() < end for start, end in string_ranges):
            continue
        raw = match.group(1)
        value: Any = float(raw) if "." in raw else int(raw)
        items.append((match.start(), value))
    items.sort(key=lambda item: item[0])
    return [value for _index, value in items]


def resolve_string_arrays(text: str) -> str:
    """Resolve direct ``_0x...[]`` indexing for simple string/number arrays."""
    declarations: list[tuple[int, int, str, list[Any]]] = []
    for match in _ARRAY_DECL_RE.finditer(text):
        name = match.group("name")
        values = _parse_array_literals(match.group("array"))
        declarations.append((match.start(), match.end(), name, values))
    if not declarations:
        return text

    ranges = [(start, end) for start, end, _name, _values in declarations]
    table = {name: values for _start, _end, name, values in declarations}

    def _replace_index(match: re.Match[str]) -> str:
        name = match.group("name")
        values = table.get(name)
        if values is None:
            return match.group(0)
        raw = match.group(2)
        try:
            index = int(raw, 16) if raw.startswith("0x") else int(raw)
        except ValueError:
            return match.group(0)
        if 0 <= index < len(values):
            value = values[index]
            if isinstance(value, str):
                return json.dumps(value, ensure_ascii=False)
            return str(value)
        return match.group(0)

    string_ranges = [(start, end) for start, end, _q, _c, _i in _iter_js_strings(text)]
    out: list[str] = []
    cursor = 0
    for match in _ARRAY_INDEX_RE.finditer(text):
        if any(start <= match.start() < end for start, end in ranges):
            continue
        if any(start <= match.start() < end for start, end in string_ranges):
            continue
        out.append(text[cursor : match.start()])
        out.append(_replace_index(match))
        cursor = match.end()
    out.append(text[cursor:])
    return "".join(out)


def strip_js_comments(text: str) -> str:
    """Remove JS line/block comments without touching strings."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in {"'", '"', "`"}:
            for start, end, _quote, _content, _interp in _iter_js_strings(text[i:]):
                out.append(text[i : i + (end - start)])
                i += end - start
                break
            else:
                out.append(ch)
                i += 1
            continue
        if text.startswith("//", i):
            newline = text.find("\n", i)
            if newline == -1:
                return "".join(out)
            out.append("\n")
            i = newline + 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                return "".join(out)
            out.append("\n" * text.count("\n", i, end + 2))
            i = end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def beautify_js(text: str) -> str:
    """Use jsbeautifier when installed; otherwise apply a conservative formatter."""
    try:
        import jsbeautifier  # type: ignore

        return jsbeautifier.beautify(text)
    except Exception:
        pass
    return _simple_beautify(text)


def _simple_beautify(text: str) -> str:
    out: list[str] = []
    indent = 0
    current = ""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in {"'", '"', "`"}:
            for start, end, _quote, _content, _interp in _iter_js_strings(text[i:]):
                current += text[i : i + (end - start)]
                i += end - start
                break
            else:
                current += ch
                i += 1
            continue
        if text.startswith("//", i):
            newline = text.find("\n", i)
            if newline == -1:
                current += text[i:]
                i = n
            else:
                current += text[i : newline + 1]
                i = newline + 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
            current += text[i:end]
            i = end
            continue
        if ch == "{":
            current += ch
            out.append(current)
            indent += 1
            current = "  " * indent
            i += 1
        elif ch == "}":
            if current.strip():
                out.append(current)
            indent = max(0, indent - 1)
            current = "  " * indent + ch
            out.append(current)
            current = "  " * indent
            i += 1
        elif ch == ";":
            current += ch
            out.append(current)
            current = "  " * indent
            i += 1
        elif ch == "\n":
            if current.strip():
                out.append(current)
            current = "  " * indent
            i += 1
        else:
            current += ch
            i += 1
    if current.strip():
        out.append(current)
    return "\n".join(out)


def _unwrap_eval_inner(code: str) -> str:
    decoded = _decode_string_escapes(code)
    if not decoded.strip():
        return code
    # A statement-looking string becomes inline code; an expression stays wrapped.
    if re.search(r"function|=>|\breturn\b|[{};]", decoded):
        return decoded
    return f"({decoded})"


def unwrap_eval_calls(text: str) -> str:
    """Replace obvious ``eval("...")`` strings with their decoded code."""
    pattern = re.compile(
        r"(?:window\.)?eval\s*\(\s*(['\"])((?:\\.|(?!\1).)*)\1\s*\)",
        re.DOTALL,
    )

    def _replace(match: re.Match[str]) -> str:
        return _unwrap_eval_inner(match.group(2))

    return pattern.sub(_replace, text)


def deobfuscate_js(text: str, max_passes: int = 6) -> DeobfuscationResult:
    """Apply conservative deobfuscation passes until stable."""
    passes: list[str] = []
    current = text
    for _ in range(max_passes):
        before = current
        current = strip_js_comments(current)
        current = decode_js_escapes(current)
        current = decode_base64_calls(current)
        current = resolve_string_arrays(current)
        current = unwrap_eval_calls(current)
        if current == before:
            break
        passes.append(f"pass-{len(passes) + 1}")
    current = beautify_js(current)
    passes.append("beautify")
    return DeobfuscationResult(output=current, passes=passes)


# ---------------------------------------------------------------------------
# Obfuscation detection
# ---------------------------------------------------------------------------


OBFUSCATION_PATTERNS: tuple[tuple[str, re.Pattern[str], float, int], ...] = (
    ("eval", re.compile(r"\beval\s*\("), 18.0, 2),
    ("function_constructor", re.compile(r"\bnew\s+Function\s*\("), 12.0, 2),
    (
        "base64",
        re.compile(r"\batob\s*\(|\bBuffer\.from\s*\([^)]*base64|CryptoJS\.enc\.Base64"),
        8.0,
        4,
    ),
    ("string_from_char_code", re.compile(r"String\.fromCharCode\s*\("), 8.0, 4),
    ("hex_escapes", re.compile(r"\\x[0-9a-fA-F]{2}"), 4.0, 10),
    ("unicode_escapes", re.compile(r"\\u[0-9a-fA-F]{4}"), 3.0, 12),
    ("hex_identifiers", re.compile(r"\b_0x[a-zA-Z0-9_$]{2,}"), 6.0, 10),
    (
        "packed_arrays",
        re.compile(r"\b(?:var|let|const)\s+_0x[a-zA-Z0-9_$]{2,}\s*=\s*\["),
        14.0,
        3,
    ),
    (
        "control_flow_flattening",
        re.compile(r"while\s*\(\s*!!\[\]\s*\)|switch\s*\(|case\s+0x"),
        10.0,
        5,
    ),
    (
        "old_obfuscation",
        re.compile(r"decodeURIComponent\s*\(\s*escape\s*\(|unescape\s*\("),
        12.0,
        2,
    ),
    (
        "char_code_ops",
        re.compile(r"\.charCodeAt\s*\(|\.split\s*\(\s*['\"]\s*\)|\.join\s*\(\s*['\"]\s*\)"),
        5.0,
        8,
    ),
)


def _shannon_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in counts.values() if count)


def detect_obfuscation(js: str) -> ObfuscationProfile:
    """Score a JS source for common obfuscation markers."""
    signals: list[ObfuscationSignal] = []
    score = 0.0
    for name, pattern, weight, cap in OBFUSCATION_PATTERNS:
        matches = list(pattern.finditer(js))
        if not matches:
            continue
        count = len(matches)
        score += weight * min(count, cap)
        signals.append(
            ObfuscationSignal(
                name=name,
                count=count,
                examples=[_context(js, match.start(), 80) for match in matches[:3]],
            )
        )

    if js.count("\n") < 2 and len(js) > 2000:
        score += 15
        signals.append(
            ObfuscationSignal(
                name="minified",
                count=1,
                examples=["single long line"],
            )
        )
    elif js and len(js) / max(1, js.count("\n") + 1) > 400:
        score += 8
        signals.append(
            ObfuscationSignal(
                name="minified",
                count=1,
                examples=["average line length over 400 characters"],
            )
        )

    identifiers = re.findall(r"\b[A-Za-z_$][\w$]*\b", js)
    if identifiers:
        avg_len = sum(len(item) for item in identifiers) / len(identifiers)
        max_len = max(len(item) for item in identifiers)
        if max_len >= 24 or avg_len >= 12:
            score += 8
            signals.append(
                ObfuscationSignal(
                    name="long_identifiers",
                    count=len(identifiers),
                    examples=[
                        f"avg_length={avg_len:.1f}",
                        f"max_length={max_len}",
                    ],
                )
            )

    entropy = _shannon_entropy(js)
    if entropy > 5.8:
        score += 6
        signals.append(
            ObfuscationSignal(
                name="high_entropy",
                count=1,
                examples=[f"entropy={entropy:.2f}"],
            )
        )

    string_chars = sum(
        len(content) for _start, _end, _quote, content, _has_interp in _iter_js_strings(js)
    )
    if js and string_chars / len(js) > 0.45:
        score += 5
        signals.append(
            ObfuscationSignal(
                name="dense_strings",
                count=1,
                examples=[f"string_ratio={string_chars / len(js):.2f}"],
            )
        )

    score = min(100.0, score)
    if score < 15:
        level = "clean"
    elif score < 40:
        level = "minified"
    elif score < 70:
        level = "mild"
    else:
        level = "strong"
    return ObfuscationProfile(score=score, level=level, signals=signals)


# ---------------------------------------------------------------------------
# Crypto and request analysis
# ---------------------------------------------------------------------------


CRYPTO_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("md5", re.compile(r"\bmd5\s*\(|CryptoJS\.MD5\s*\("), "MD5"),
    ("sha1", re.compile(r"\bsha1\s*\(|CryptoJS\.SHA1\s*\("), "SHA-1"),
    ("sha256", re.compile(r"\bsha256\s*\(|CryptoJS\.SHA256\s*\("), "SHA-256"),
    ("sha512", re.compile(r"\bsha512\s*\(|CryptoJS\.SHA512\s*\("), "SHA-512"),
    (
        "hmac",
        re.compile(r"\bhmac\s*\(|createHmac\s*\(|CryptoJS\.Hmac(?:MD5|SHA1|SHA256|SHA512)\s*\("),
        "HMAC",
    ),
    ("aes", re.compile(r"\bAES\.encrypt|CryptoJS\.AES|aes-128|aes-256"), "AES"),
    ("des", re.compile(r"\bDES\.encrypt|CryptoJS\.DES|des-ede3"), "DES"),
    (
        "rsa",
        re.compile(r"\bJSEncrypt\s*\(|RSA\.encrypt|rsa\s*\.\s*encrypt|new\s+RSASign"),
        "RSA",
    ),
    (
        "base64",
        re.compile(r"\bbtoa\s*\(|\batob\s*\(|Base64\.encode|CryptoJS\.enc\.Base64"),
        "Base64",
    ),
    (
        "uri_codec",
        re.compile(r"\bencodeURIComponent\s*\(|\bdecodeURIComponent\s*\("),
        "URL-encoding",
    ),
    ("uuid", re.compile(r"\bcrypto\.randomUUID\s*\(|\buuid\s*\(|nanoid\s*\("), "UUID"),
    (
        "timestamp",
        re.compile(
            r"\bDate\.now\s*\(|\bperformance\.now\s*\(|new\s+Date\s*\(\s*\)\s*\.\s*getTime\s*\("
        ),
        "timestamp",
    ),
    ("random", re.compile(r"\bMath\.random\s*\(|\bcrypto\.getRandomValues\s*\("), "random"),
)


def analyze_crypto_calls(js: str) -> list[CryptoCall]:
    calls: list[CryptoCall] = []
    seen: set[tuple[str, str]] = set()
    for _name, pattern, algorithm in CRYPTO_PATTERNS:
        for match in pattern.finditer(js):
            expression = js[match.start() : match.end()].strip()
            key = (algorithm, _context(js, match.start(), 100))
            if key in seen:
                continue
            seen.add(key)
            calls.append(
                CryptoCall(
                    algorithm=algorithm,
                    expression=expression,
                    line=_line_of(js, match.start()),
                    context=_context(js, match.start()),
                )
            )
    calls.sort(key=lambda item: item.line)
    return calls


_FETCH_SITE_RE = re.compile(
    r"\bfetch\s*\(\s*(?P<q1>['\"`])(?P<url>(?:\\.|(?!\1).)*)(?P=q1)"
    r"(?P<url_tail>(?:\s*\+\s*(?:\([^)]*\)|[^,()]+(?:\([^)]*\))?))*)?"
    r"\s*(?:,\s*(?P<opts>\{.*?\})\s*)?\)",
    re.DOTALL,
)
_AXIOS_SITE_RE = re.compile(
    r"\baxios\s*\.\s*(?P<method>get|post|put|patch|delete|head|options|request)"
    r"\s*\(\s*(?P<q1>['\"`])(?P<url>(?:\\.|(?!\1).)*)(?P=q1)"
    r"(?P<url_tail>(?:\s*\+\s*(?:\([^)]*\)|[^,()]+(?:\([^)]*\))?))*)?"
    r"\s*(?:,\s*(?P<opts>\{.*?\})\s*)?\)",
    re.DOTALL,
)
_XHR_SITE_RE = re.compile(
    r"\.open\s*\(\s*(?P<q1>['\"])(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)(?P=q1)"
    r"\s*,\s*(?P<q2>['\"`])(?P<url>(?:\\.|(?!\3).)*)(?P=q2)"
    r"(?P<url_tail>(?:\s*\+\s*(?:\([^)]*\)|[^,()]+(?:\([^)]*\))?))*)?",
    re.DOTALL,
)
_AJAX_SITE_RE = re.compile(r"\$\.ajax\s*\(\s*(?P<opts>\{.*?\})\s*\)", re.DOTALL)
_AJAX_METHOD_RE = re.compile(
    r"\b(?:type|method)\s*:\s*(['\"])(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\1"
)

_OBJECT_HEADER_RE = re.compile(r"\bheaders\s*:\s*\{(.*?)\}", re.DOTALL)
_OBJECT_BODY_JSON_RE = re.compile(r"\bbody\s*:\s*JSON\.stringify\s*\(\s*(\{.*?\})\s*\)", re.DOTALL)
_OBJECT_BODY_STRING_RE = re.compile(
    r"\bbody\s*:\s*(?P<q1>['\"`])(?P<value>(?:\\.|(?!\1).)*)(?P=q1)",
    re.DOTALL,
)
_OBJECT_BODY_DICT_RE = re.compile(r"\bbody\s*:\s*(\{.*?\})", re.DOTALL)
_OBJECT_PARAMS_RE = re.compile(r"\bparams\s*:\s*(\{.*?\})", re.DOTALL)
_PAIR_RE = re.compile(
    r"([A-Za-z_$][\w$]*|['\"][^'\"]+['\"])\s*:\s*"
    r"((?:['\"](?:\\.|[^'\"\\])*['\"]|\{[^{}]*\}|[^,}\s]+))",
    re.DOTALL,
)


def _js_object_to_dict(text: str) -> dict[str, Any]:
    normalized = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)\s*:", r'\1"\2":', text)
    normalized = re.sub(r"(['\"])([^'\"]+)(['\"])\s*:", r'"\2":', normalized)
    normalized = normalized.replace("'", '"')
    normalized = re.sub(r",\s*([}\]])", r"\1", normalized)
    normalized = re.sub(r"\bundefined\b", "null", normalized)
    try:
        value = json.loads(normalized)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        result: dict[str, Any] = {}
        for match in _PAIR_RE.finditer(text):
            key = match.group(1).strip("'\"")
            result[key] = match.group(2)
        return result


def _extract_options(opts: str | None) -> tuple[dict[str, str], Any, dict[str, Any]]:
    headers: dict[str, str] = {}
    body: Any = None
    params: dict[str, Any] = {}
    if not opts:
        return headers, body, params
    header_match = _OBJECT_HEADER_RE.search(opts)
    if header_match:
        headers = _js_object_to_dict(header_match.group(1))
    json_body = _OBJECT_BODY_JSON_RE.search(opts)
    if json_body:
        body = _js_object_to_dict(json_body.group(1))
    else:
        string_body = _OBJECT_BODY_STRING_RE.search(opts)
        if string_body:
            body = string_body.group("value")
        else:
            dict_body = _OBJECT_BODY_DICT_RE.search(opts)
            if dict_body:
                body = _js_object_to_dict(dict_body.group(1))
    params_match = _OBJECT_PARAMS_RE.search(opts)
    if params_match:
        parsed = _js_object_to_dict(params_match.group(1))
        if parsed:
            params = parsed
    return headers, body, params


DYNAMIC_NAME_RE = re.compile(
    r"^(?:sign|sig|signature|token|access_token|ts|timestamp|nonce|rand|random|"
    r"uuid|device_id|deviceId|session_id|sessionId|_t|_sign|secret|key|encrypt|"
    r"payload|cipher|data|params|body|header|auth|authorization)$"
)


def _classify_dynamic(name: str, expression: str) -> tuple[str, float]:
    text = f"{name} {expression}".lower()
    if re.search(r"date\.now|performance\.now|gettime\(|timestamp|time\b|ts\b", text):
        return "timestamp", 0.92
    if re.search(r"math\.random|randomuuid|nanoid|getrandomvalues|nonce|rand\b|uuid", text):
        return "nonce", 0.8
    if re.search(
        r"sign|sig\b|token|secret|encrypt|decrypt|md5|sha1|sha256|sha512|hmac|aes|rsa", text
    ):
        return "signature", 0.85
    if re.search(r"btoa|atob|base64|encodeuri|escape\(", text):
        return "encoding", 0.7
    return "dynamic", 0.5


def _dynamic_from_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
    params: dict[str, Any],
    options_text: str,
    js: str,
    site_start: int,
    site_end: int,
) -> list[DynamicField]:
    fields: list[DynamicField] = []
    seen: set[tuple[str, str]] = set()

    def add(name: str, expression: str, source: str = "js") -> None:
        name = str(name)
        expression = expression.strip()[:160]
        kind, confidence = _classify_dynamic(name, expression)
        key = (name, kind)
        if key in seen:
            return
        seen.add(key)
        fields.append(
            DynamicField(
                name=name,
                kind=kind,
                expression=expression or "(inferred)",
                confidence=confidence,
                source=source,
            )
        )

    for key, value in (params or {}).items():
        if (
            DYNAMIC_NAME_RE.search(str(key))
            or _classify_dynamic(str(key), str(value))[0] != "dynamic"
        ):
            add(str(key), str(value))
    for key, value in (body or {}).items() if isinstance(body, dict) else []:
        if (
            DYNAMIC_NAME_RE.search(str(key))
            or _classify_dynamic(str(key), str(value))[0] != "dynamic"
        ):
            add(str(key), str(value))
    for key, value in (headers or {}).items():
        if re.search(r"token|sign|auth|nonce|timestamp|encrypt", str(key), re.I):
            add(str(key), str(value))

    parsed_url = urllib.parse.urlsplit(url)
    for key, values in urllib.parse.parse_qs(parsed_url.query).items():
        if DYNAMIC_NAME_RE.search(key):
            add(key, ";".join(values), source="url")

    nearby = js[max(0, site_start - 260) : site_end + 260]
    for marker in (
        ("Date.now()", r"Date\.now\s*\(\s*\)"),
        ("performance.now()", r"performance\.now\s*\(\s*\)"),
        ("Math.random()", r"Math\.random\s*\(\s*\)"),
        ("crypto.randomUUID()", r"crypto\.randomUUID\s*\(\s*\)"),
        ("nonce", r"\bnonce\b"),
        ("timestamp", r"\btimestamp\b|\bts\s*[:=]"),
        ("signature", r"\bsign(?:ature)?\b|\bsig\s*[:=]"),
        ("token", r"\btoken\b"),
    ):
        if re.search(marker[1], options_text or "") or re.search(marker[1], nearby):
            add(marker[0], marker[0])

    for match in re.finditer(
        r"\b(?:md5|sha1|sha256|sha512|hmac|aes|rsa|encrypt|sign)\s*\(", nearby
    ):
        expression = nearby[match.start() : match.end()]
        add(re.sub(r"[^A-Za-z0-9]", "", match.group(0)), expression)

    return fields


def analyze_request_sites(js: str) -> list[RequestSite]:
    sites: list[RequestSite] = []

    def add_site(
        method: str,
        url: str,
        url_tail: str,
        opts: str | None,
        match_start: int,
        match_end: int,
        source: str,
    ) -> None:
        if url_tail and url_tail.strip():
            url = url + url_tail
        headers, body, params = _extract_options(opts)
        dynamic = _dynamic_from_request(
            method,
            url,
            headers,
            body,
            params,
            opts or "",
            js,
            match_start,
            match_end,
        )
        sites.append(
            RequestSite(
                method=method.upper(),
                url=url,
                line=_line_of(js, match_start),
                headers=headers,
                body=body,
                params=params,
                dynamic_fields=dynamic,
                source=source,
                raw=f"{url} {opts or ''}",
            )
        )

    for match in _FETCH_SITE_RE.finditer(js):
        add_site(
            "GET",
            match.group("url"),
            match.group("url_tail") or "",
            match.group("opts"),
            match.start(),
            match.end(),
            "fetch",
        )
    for match in _AXIOS_SITE_RE.finditer(js):
        method = match.group("method").upper()
        add_site(
            method,
            match.group("url"),
            match.group("url_tail") or "",
            match.group("opts"),
            match.start(),
            match.end(),
            "axios",
        )
    for match in _XHR_SITE_RE.finditer(js):
        add_site(
            match.group("method"),
            match.group("url"),
            match.group("url_tail") or "",
            None,
            match.start(),
            match.end(),
            "xhr",
        )
    for match in _AJAX_SITE_RE.finditer(js):
        opts = match.group("opts")
        method_match = _AJAX_METHOD_RE.search(opts)
        method = method_match.group(2) if method_match else "GET"
        url_match = re.search(r"\burl\s*:\s*(['\"`])([^'\"`]+)\1", opts)
        url = url_match.group(2) if url_match else ""
        add_site(method, url, "", opts, match.start(), match.end(), "jquery-ajax")
    return sites


_FN_DEF_RE = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)\s*\{")
_FN_ARROW_RE = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?"
    r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{"
)
_FN_EXPR_RE = re.compile(
    r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*function\s*(?:\([^)]*\))?\s*\{"
)
SIGNATURE_KEYWORD_RE = re.compile(
    r"sign|encrypt|decrypt|token|hash|md5|sha1|sha256|sha512|hmac|aes|rsa|"
    r"nonce|timestamp|buildparam|build_param|gen_sign|genSign|get_sign|getSign",
    re.I,
)


def _braced_section(text: str, open_index: int) -> str:
    depth = 0
    i = open_index
    n = len(text)
    start = open_index
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return text[start:i]


def _algorithm_hints(body: str) -> str:
    hints: list[str] = []
    for _name, _pattern, algorithm in CRYPTO_PATTERNS:
        if _pattern.search(body):
            hints.append(algorithm)
    if re.search(r"\b(?:concat|join|split|charCodeAt)\b", body, re.I):
        hints.append("string-transform")
    return ", ".join(dict.fromkeys(hints)) if hints else "custom"


def find_signature_candidates(js: str) -> list[SignatureCandidate]:
    candidates: list[SignatureCandidate] = []
    seen: set[str] = set()
    for pattern in (_FN_DEF_RE, _FN_ARROW_RE, _FN_EXPR_RE):
        for match in pattern.finditer(js):
            name = match.group(1)
            if name in seen:
                continue
            open_brace = match.end() - 1
            if open_brace < 0 or js[open_brace] != "{":
                continue
            body = _braced_section(js, open_brace)
            combined = f"{name} {body}"
            if not SIGNATURE_KEYWORD_RE.search(combined):
                continue
            seen.add(name)
            calls = len(re.findall(rf"\b{re.escape(name)}\s*\(", js)) - 1
            algorithm = _algorithm_hints(body)
            confidence = min(
                0.95,
                0.4
                + 0.18
                * (
                    name in {"sign", "encrypt", "token"}
                    or bool(re.search(r"sign|encrypt|token", name, re.I))
                )
                + 0.12 * len(algorithm.split(", "))
                + 0.1 * min(1, calls),
            )
            candidates.append(
                SignatureCandidate(
                    name=name,
                    algorithm=algorithm,
                    snippet=f"{name}{body[:MAX_SNIPPET]}",
                    line=_line_of(js, match.start()),
                    calls=calls,
                    confidence=confidence,
                )
            )
    candidates.sort(key=lambda item: item.confidence, reverse=True)
    return candidates


def find_function_names(js: str) -> list[str]:
    """Return all function definition names in a JS source."""
    names: list[str] = []
    seen: set[str] = set()
    for pattern in (_FN_DEF_RE, _FN_ARROW_RE, _FN_EXPR_RE):
        for match in pattern.finditer(js):
            name = match.group(1)
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


BUNDLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("webpack", re.compile(r"webpackJsonp|__webpack_require__|webpackChunk|__webpack_modules__")),
    ("vite", re.compile(r"import\.meta\.hot|__vite__|vite/client")),
    ("rollup", re.compile(r"__rollupHelper|System\.register")),
    ("esbuild", re.compile(r"__esbuild|esbuild")),
    ("amd", re.compile(r"\bdefine\s*\(\s*\[")),
    ("commonjs", re.compile(r"\brequire\s*\(\s*['\"][^'\"]+['\"]\s*\)")),
)


def detect_bundle_framework(js: str) -> dict[str, Any]:
    """Detect which bundler/framework produced a JS bundle."""
    detected: dict[str, int] = {}
    for name, pattern in BUNDLE_PATTERNS:
        count = len(pattern.findall(js))
        if count:
            detected[name] = count
    webpack_modules = len(
        re.findall(
            r"function\s*\(\s*module\s*,\s*exports\s*,\s*__webpack_require__\s*\)",
            js,
        )
    )
    detail = extract_webpack_modules(js) if "webpack" in detected else {}
    return {
        "frameworks": detected,
        "webpack_modules": webpack_modules,
        "webpack_modules_detail": detail,
    }


_WEBPACK_MODULE_OBJECT_RE = re.compile(
    r"(['\"]?\d+(?:\.\d+)?['\"]?)\s*:\s*function\s*\(\s*module\s*,\s*exports\s*,\s*"
    r"__webpack_require__\s*\)"
)
_WEBPACK_MODULE_ARRAY_RE = re.compile(
    r"(?:^|\[|,)\s*function\s*\(\s*module\s*,\s*exports\s*,\s*__webpack_require__\s*\)"
)
_WEBPACK_MODULE_COMMENT_RE = re.compile(r"/\*!\s*([^*]+?)\s*\*/")


def extract_webpack_modules(js: str) -> dict[str, Any]:
    """Extract webpack module IDs and named module comments from a bundle."""
    ids: list[str] = []
    for match in _WEBPACK_MODULE_OBJECT_RE.finditer(js):
        module_id = match.group(1).strip("'\"")
        if module_id not in ids:
            ids.append(module_id)
    array_count = len(_WEBPACK_MODULE_ARRAY_RE.findall(js))
    named: list[str] = []
    for match in _WEBPACK_MODULE_COMMENT_RE.finditer(js):
        name = match.group(1).strip()
        if name.startswith("./") or "/" in name or name.startswith("webpack"):
            named.append(name)
    return {
        "module_count": max(len(ids), array_count),
        "ids": ids[:200],
        "named_modules": named[:100],
    }


def _decoder_candidates(js: str, max_candidates: int = 8) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for pattern in (_FN_DEF_RE, _FN_ARROW_RE, _FN_EXPR_RE):
        for match in pattern.finditer(js):
            name = match.group(1)
            if name in seen:
                continue
            seen.add(name)
            open_brace = match.end() - 1
            if open_brace < 0 or js[open_brace] != "{":
                continue
            body = _braced_section(js, open_brace)
            if name.startswith("_0x") or re.search(
                r"charCodeAt|fromCharCode|split\(\s*['\"]|join\(\s*['\"]|toString\(\s*16",
                body,
            ):
                candidates.append((name, body))
                if len(candidates) >= max_candidates:
                    return candidates
    return candidates


def decode_string_arrays_dynamic(
    js: str,
    max_indices: int = 64,
    max_candidates: int = 8,
    timeout: float = 10.0,
) -> DeobfuscationResult:
    """Execute suspected string decoders in Node to resolve obfuscated arrays."""
    if not node_available():
        return DeobfuscationResult(output=js, passes=["dynamic-decode-skipped"])
    decoded: dict[tuple[str, int], str] = {}
    for name, _body in _decoder_candidates(js, max_candidates):
        failures = 0
        for index in range(max_indices):
            result = run_signature_function(js, name, [index], timeout=timeout)
            if not result.get("ok"):
                failures += 1
                if failures >= 3:
                    break
                continue
            value = result.get("value")
            if (
                isinstance(value, str)
                and 1 <= len(value) <= 200
                and not value.startswith("[object")
            ):
                decoded[(name, index)] = value
                failures = 0
    if not decoded:
        return DeobfuscationResult(output=js, passes=[])
    output = js
    for (name, index), value in decoded.items():
        replacement = json.dumps(value, ensure_ascii=False)
        output = re.sub(
            rf"\b{re.escape(name)}\s*\(\s*(?:0x{index:x}|{index})\s*\)",
            replacement,
            output,
        )
        output = re.sub(
            rf"\b{re.escape(name)}\s*\[\s*(?:0x{index:x}|{index})\s*\]",
            replacement,
            output,
        )
    return DeobfuscationResult(output=output, passes=[f"dynamic-decode-{len(decoded)}"])


DEVICE_PATTERNS: tuple[tuple[str, str, str, float], ...] = (
    ("navigator.userAgent", "navigator", r"\bnavigator\s*\.\s*userAgent(?:Data)?", 0.95),
    ("navigator.platform", "navigator", r"\bnavigator\s*\.\s*platform", 0.9),
    ("navigator.language", "navigator", r"\bnavigator\s*\.\s*languages?", 0.9),
    ("navigator.hardwareConcurrency", "navigator", r"\bnavigator\s*\.\s*hardwareConcurrency", 0.9),
    ("navigator.deviceMemory", "navigator", r"\bnavigator\s*\.\s*deviceMemory", 0.9),
    (
        "navigator.maxTouchPoints",
        "navigator",
        r"\bnavigator\s*\.\s*maxTouchPoints|ontouchstart",
        0.85,
    ),
    (
        "navigator.plugins",
        "navigator",
        r"\bnavigator\s*\.\s*plugins|navigator\s*\.\s*mimeTypes",
        0.85,
    ),
    ("navigator.vendor", "navigator", r"\bnavigator\s*\.\s*vendor", 0.8),
    ("navigator.connection", "navigator", r"\bnavigator\s*\.\s*connection", 0.8),
    ("navigator.webdriver", "navigator", r"\bnavigator\s*\.\s*webdriver", 0.9),
    ("screen.size", "screen", r"\bscreen\s*\.\s*(?:width|availWidth|height|availHeight)", 0.95),
    ("screen.colorDepth", "screen", r"\bscreen\s*\.\s*(?:colorDepth|pixelDepth)", 0.9),
    ("screen.orientation", "screen", r"\bscreen\s*\.\s*orientation", 0.8),
    ("devicePixelRatio", "window", r"\bdevicePixelRatio", 0.9),
    ("window.size", "window", r"\b(?:innerWidth|innerHeight|outerWidth|outerHeight)", 0.85),
    (
        "canvas",
        "canvas",
        r"\.toDataURL\s*\(|createElement\s*\(\s*['\"]canvas['\"]\s*\)|getContext\s*\(\s*['\"]2d['\"]",
        0.95,
    ),
    (
        "webgl",
        "webgl",
        r"getContext\s*\(\s*['\"](?:experimental-)?webgl['\"]|UNMASKED_VENDOR_WEBGL|UNMASKED_RENDERER_WEBGL|WEBGL_debug_renderer_info",
        0.95,
    ),
    (
        "fonts",
        "fonts",
        r"document\s*\.\s*fonts|FontFace\s*\(|measureText\s*\(|font\s*:\s*['\"]",
        0.85,
    ),
    ("timezone", "timezone", r"Intl\s*\.\s*DateTimeFormat|getTimezoneOffset|timeZone", 0.9),
    ("battery", "battery", r"getBattery\s*\(|BatteryManager|chargingTime|dischargingTime", 0.85),
    ("storage", "storage", r"localStorage|sessionStorage|indexedDB", 0.8),
    ("crypto", "crypto", r"crypto\s*\.\s*subtle|crypto\s*\.\s*getRandomValues", 0.9),
)


def analyze_device_fingerprint(js: str) -> list[DeviceFingerprintField]:
    """Find device-fingerprint API usage that can feed request parameters."""
    fields: list[DeviceFingerprintField] = []
    seen: set[tuple[str, int]] = set()
    for name, category, pattern, confidence in DEVICE_PATTERNS:
        for match in re.finditer(pattern, js):
            key = (name, match.start())
            if key in seen:
                continue
            seen.add(key)
            fields.append(
                DeviceFingerprintField(
                    name=name,
                    category=category,
                    expression=_context(js, match.start(), 100),
                    line=_line_of(js, match.start()),
                    confidence=confidence,
                )
            )
    fields.sort(key=lambda item: item.line)
    return fields


TIMESTAMP_PATTERNS: tuple[tuple[str, re.Pattern[str], str, float], ...] = (
    ("Date.now", re.compile(r"Date\.now\s*\(\s*\)"), "Date.now()", 0.95),
    ("performance.now", re.compile(r"performance\.now\s*\(\s*\)"), "performance.now()", 0.92),
    (
        "getTime",
        re.compile(r"new\s+Date\s*\(\s*\)\s*\.\s*(?:getTime|valueOf)\s*\(\s*\)"),
        "new Date().getTime()",
        0.95,
    ),
    ("Date.parse", re.compile(r"Date\.parse\s*\("), "Date.parse(...)", 0.8),
    ("toISOString", re.compile(r"toISOString\s*\(\s*\)"), "toISOString()", 0.85),
    ("unary-date", re.compile(r"\+new\s+Date\s*\(\s*\)"), "+new Date()", 0.9),
)


def _timestamp_unit(context: str, source: str) -> str:
    if re.search(r"Math\.(?:floor|round|ceil)\s*\(\s*Date\.now\s*\(\s*\)\s*/\s*1000", context):
        return "seconds"
    if re.search(r"Date\.now\s*\(\s*\)\s*/\s*1000", context):
        return "seconds"
    if re.search(r"Date\.now\s*\(\s*\)\s*>>\s*10", context):
        return "seconds"
    if re.search(r"toString\s*\(\s*36\s*\)", context):
        return "base36"
    if re.search(r"toString\s*\(\s*16\s*\)", context):
        return "hex"
    if source == "toISOString()" or re.search(r"toISOString", context):
        return "iso8601"
    return "milliseconds"


def _nearby_param_names(context: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"['\"]?([A-Za-z_$][\w$]*)['\"]?\s*[:=]", context):
        name = match.group(1)
        if re.search(r"ts|timestamp|time|nonce|expire|deadline|st|t$", name, re.I):
            names.append(name)
    return list(dict.fromkeys(names))


def analyze_timestamp_fields(js: str) -> list[TimestampField]:
    """Locate timestamp producers and infer their unit / request param names."""
    fields: list[TimestampField] = []
    seen: set[tuple[str, int]] = set()
    for name, pattern, source, confidence in TIMESTAMP_PATTERNS:
        for match in pattern.finditer(js):
            key = (name, match.start())
            if key in seen:
                continue
            seen.add(key)
            context = js[max(0, match.start() - 240) : match.end() + 320]
            fields.append(
                TimestampField(
                    name=name,
                    source=source,
                    unit=_timestamp_unit(context, source),
                    line=_line_of(js, match.start()),
                    context=_context(js, match.start()),
                    confidence=confidence,
                    request_params=_nearby_param_names(context),
                )
            )
    fields.sort(key=lambda item: item.line)
    return fields


def _extract_param_order(body: str) -> list[str]:
    if re.search(r"Object\.keys\s*\([^)]*\)\s*\.\s*sort\s*\(\s*\)", body):
        return ["sorted-object-keys"]
    order: list[str] = []
    for array_match in re.finditer(r"\[[^\[\]]*\]", body):
        values = _parse_array_literals(array_match.group(0))
        strings = [str(value) for value in values if isinstance(value, str)]
        if len(strings) >= 2:
            order.extend(strings)
    for match in re.finditer(r"\b(?:concat|join|push)\s*\(\s*([^)]+)\)", body):
        for quoted in re.findall(r"['\"]([^'\"]{1,40})['\"]", match.group(1)):
            if quoted not in order:
                order.append(quoted)
    return list(dict.fromkeys(order))[:20]


def _extract_secret_keys(body: str) -> list[str]:
    keys: list[str] = []
    for match in re.finditer(
        r"\b(?:var|let|const|this\.)?\s*([A-Za-z_$][\w$]*)\s*=\s*['\"]([^'\"]+)['\"]",
        body,
    ):
        name = match.group(1)
        if re.search(
            r"key|secret|salt|token|appkey|appid|privatekey|publickey|signkey",
            name,
            re.IGNORECASE,
        ):
            keys.append(match.group(2))
    for match in re.finditer(r"['\"]([^'\"]{6,})['\"]\s*(?:,|\])", body):
        candidate = match.group(1)
        if re.search(r"secret|salt|key|token|sign", candidate, re.I) and candidate not in keys:
            keys.append(candidate)
    return list(dict.fromkeys(keys))[:10]


def extract_secret_hints(js: str) -> list[str]:
    """Extract candidate secret strings assigned to key-like variables."""
    secrets: list[str] = []
    for match in re.finditer(
        r"\b(?:var|let|const|this\.)?\s*([A-Za-z_$][\w$]*)\s*=\s*['\"]([^'\"]{4,80})['\"]",
        js,
    ):
        name = match.group(1)
        if re.search(
            r"key|secret|salt|token|appkey|appid|privatekey|publickey|signkey",
            name,
            re.IGNORECASE,
        ):
            secrets.append(match.group(2))
    return list(dict.fromkeys(secrets))[:100]


def _detect_encoding(body: str) -> str:
    if re.search(r"CryptoJS\.enc\.Hex|\.toString\s*\(\s*16\s*\)", body):
        return "hex"
    if re.search(r"CryptoJS\.enc\.Base64|\bbtoa\s*\(|\batob\s*\(|Base64\.encode", body):
        return "base64"
    if re.search(r"encodeURIComponent|decodeURIComponent|escape\s*\(", body):
        return "url-encoded"
    if re.search(r"CryptoJS\.enc\.Utf8|\bTextEncoder\b", body):
        return "utf8"
    if re.search(r"\.toString\s*\(\s*36\s*\)", body):
        return "base36"
    return "plain"


def analyze_signature_recipes(
    js: str,
    candidates: list[SignatureCandidate],
) -> list[SignatureRecipe]:
    """Turn signature candidates into replay recipes with ordering / keys / encoding."""
    recipes: list[SignatureRecipe] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.name in seen:
            continue
        seen.add(candidate.name)
        body = candidate.snippet[candidate.snippet.find("{") + 1 :]
        recipes.append(
            SignatureRecipe(
                function_name=candidate.name,
                algorithm=candidate.algorithm,
                parameter_order=_extract_param_order(body),
                secret_keys=_extract_secret_keys(body),
                encoding=_detect_encoding(body),
                snippet=candidate.snippet,
                line=candidate.line,
                confidence=min(0.98, candidate.confidence + 0.05),
            )
        )
    recipes.sort(key=lambda item: item.confidence, reverse=True)
    return recipes


_ASSIGN_RE = re.compile(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;{}]+?);")


def _assignment_sources(
    value: str,
    candidates: list[SignatureCandidate],
) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    for _name, pattern, algorithm in CRYPTO_PATTERNS:
        if pattern.search(value):
            sources.append(("crypto", algorithm))
    for _name, pattern, source, _confidence in TIMESTAMP_PATTERNS:
        if pattern.search(value):
            sources.append(("timestamp", source))
    for name, _category, pattern, _confidence in DEVICE_PATTERNS:
        if re.search(pattern, value):
            sources.append(("device", name))
    for candidate in candidates:
        if re.search(rf"\b{re.escape(candidate.name)}\s*\(", value):
            sources.append(("signature", candidate.name))
    return list(dict.fromkeys(sources))


def analyze_data_flow(js: str, analysis: JsAnalysis) -> list[DataFlowLink]:
    """Map device / timestamp / signature sources to request targets."""
    assignments: dict[str, list[tuple[str, str]]] = {}
    for match in _ASSIGN_RE.finditer(js):
        variable = match.group(1)
        sources = _assignment_sources(match.group(2), analysis.signature_candidates)
        if sources:
            assignments.setdefault(variable, []).extend(sources)

    links: list[DataFlowLink] = []
    seen: set[tuple[str, str, str, str, str, int]] = set()
    for site in analysis.request_sites:
        raw = f"{site.url} {site.raw}"
        for variable, sources in assignments.items():
            if not re.search(rf"\b{re.escape(variable)}\b", raw):
                continue
            targets: list[tuple[str, str]] = []
            for key, value in site.headers.items():
                if variable in str(value):
                    targets.append((str(key), "header"))
            if isinstance(site.body, dict):
                for key, value in site.body.items():
                    if variable in str(value):
                        targets.append((str(key), "body"))
            for key, value in site.params.items():
                if variable in str(value):
                    targets.append((str(key), "param"))
            for query_match in re.finditer(r"[?&]([A-Za-z_$][\w$]*)=([^&]*)", raw):
                if variable in query_match.group(2):
                    targets.append((query_match.group(1), "param"))
            if not targets and variable in site.url:
                targets.append(("url", "url"))
            if not targets:
                targets.append(("request.options", "options"))
            for source_kind, source in sources:
                for target, target_kind in targets:
                    key = (source, source_kind, variable, target, target_kind, site.line)
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append(
                        DataFlowLink(
                            source=source,
                            source_kind=source_kind,
                            variable=variable,
                            target=target,
                            target_kind=target_kind,
                            line=site.line,
                            confidence=0.82 if target_kind != "options" else 0.6,
                        )
                    )
    links.sort(key=lambda item: (item.line, item.source_kind))
    return links


def _merge_unique_requests(
    target: list[RequestSite],
    additions: list[RequestSite],
) -> None:
    seen = {(item.method, item.url) for item in target}
    for item in additions:
        key = (item.method, item.url)
        if key not in seen:
            seen.add(key)
            target.append(item)


def _merge_unique_fields(target: list[DynamicField], additions: list[DynamicField]) -> None:
    seen = {(item.name, item.kind, item.source) for item in target}
    for item in additions:
        key = (item.name, item.kind, item.source)
        if key not in seen:
            seen.add(key)
            target.append(item)


def _merge_unique_device(
    target: list[DeviceFingerprintField],
    additions: list[DeviceFingerprintField],
) -> None:
    seen = {(item.name, item.line) for item in target}
    for item in additions:
        key = (item.name, item.line)
        if key not in seen:
            seen.add(key)
            target.append(item)


def _merge_unique_timestamps(
    target: list[TimestampField],
    additions: list[TimestampField],
) -> None:
    seen = {(item.name, item.line) for item in target}
    for item in additions:
        key = (item.name, item.line)
        if key not in seen:
            seen.add(key)
            target.append(item)


def _merge_unique_links(target: list[DataFlowLink], additions: list[DataFlowLink]) -> None:
    seen = {(item.source, item.variable, item.target, item.line) for item in target}
    for item in additions:
        key = (item.source, item.variable, item.target, item.line)
        if key not in seen:
            seen.add(key)
            target.append(item)


def analyze_js(
    js: str,
    url: str | None = None,
    *,
    deep_deobfuscation: str = "auto",
    auto_install: bool = False,
    run_bundle: str = "auto",
) -> JsAnalysis:
    """Analyze one JS source and merge original + deobfuscated findings."""
    deobfuscated = deobfuscate_js(js)
    profile = detect_obfuscation(js)
    if deep_deobfuscation in {"auto", "always"} and (
        deep_deobfuscation == "always" or profile.score >= 70
    ):
        try:
            from deep_deobfuscation import deep_deobfuscate

            deep_result = deep_deobfuscate(
                js,
                mode=deep_deobfuscation,
                auto_install=auto_install,
            )
            if deep_result.get("ok") and deep_result.get("passes"):
                deobfuscated = DeobfuscationResult(
                    output=str(deep_result.get("output", deobfuscated.output)),
                    passes=list(deep_result.get("passes", deobfuscated.passes)),
                )
        except Exception:
            pass
    analysis = JsAnalysis(
        url=url,
        bundle=detect_bundle_framework(js),
        obfuscation=profile,
        crypto_calls=analyze_crypto_calls(js),
        request_sites=analyze_request_sites(js),
        signature_candidates=find_signature_candidates(js),
        device_fields=analyze_device_fingerprint(js),
        timestamp_fields=analyze_timestamp_fields(js),
        deobfuscated=deobfuscated,
    )
    cleaned = deobfuscated.output
    if cleaned != js:
        _merge_unique_requests(analysis.request_sites, analyze_request_sites(cleaned))
        _merge_unique_device(analysis.device_fields, analyze_device_fingerprint(cleaned))
        _merge_unique_timestamps(analysis.timestamp_fields, analyze_timestamp_fields(cleaned))
        _merge_unique_links(analysis.data_flow, analyze_data_flow(cleaned, analysis))
        for item in analyze_crypto_calls(cleaned):
            if item not in analysis.crypto_calls:
                analysis.crypto_calls.append(item)
        for item in find_signature_candidates(cleaned):
            if item.name not in {candidate.name for candidate in analysis.signature_candidates}:
                analysis.signature_candidates.append(item)
    analysis.crypto_calls.sort(key=lambda item: item.line)
    analysis.signature_candidates.sort(key=lambda item: item.confidence, reverse=True)
    analysis.device_fields.sort(key=lambda item: item.line)
    analysis.timestamp_fields.sort(key=lambda item: item.line)
    analysis.signature_recipes = analyze_signature_recipes(
        js + "\n" + cleaned,
        analysis.signature_candidates,
    )
    _merge_unique_links(analysis.data_flow, analyze_data_flow(js, analysis))
    analysis.data_flow.sort(key=lambda item: (item.line, item.source_kind))
    if run_bundle in {"auto", "always"} and (
        run_bundle == "always"
        or profile.score >= 70
        or bool(analysis.bundle.get("frameworks"))
    ):
        try:
            from bundle_runner import run_bundle_execution

            names = [candidate.name for candidate in analysis.signature_candidates]
            if not names:
                names = find_function_names(js)[:30]
            analysis.bundle["execution"] = run_bundle_execution(
                js,
                names,
                auto_install=auto_install,
            )
        except Exception:
            analysis.bundle["execution"] = {"ok": False, "error": "bundle execution failed"}
    if acorn_available() or (auto_install and profile.score >= 70):
        try:
            from ast_dataflow import analyze_ast_data_flow

            ast_result = analyze_ast_data_flow(js, analysis, auto_install=auto_install)
            analysis.ast_data_flow_ok = bool(ast_result.get("ok"))
            analysis.ast_data_flow = list(ast_result.get("edges", []) or [])
        except Exception:
            analysis.ast_data_flow_ok = False
    for site in analysis.request_sites:
        _merge_unique_fields(analysis.dynamic_fields, site.dynamic_fields)
    return analysis


def _source_content(source: Any) -> tuple[str, str]:
    if isinstance(source, ScriptSource):
        return source.content, source.name or "script"
    return str(source.get("content", "") or ""), str(source.get("name", "") or "script")


def cross_script_refs(sources: list[Any]) -> list[dict[str, Any]]:
    """Find functions defined in one script and referenced in another."""
    entries = [_source_content(source) for source in sources]
    names_by_index = [set(find_function_names(content)) for content, _name in entries]
    refs: list[dict[str, Any]] = []
    for index, (_content, name) in enumerate(entries):
        for function_name in sorted(names_by_index[index]):
            for other_index, (other_content, other_name) in enumerate(entries):
                if index == other_index:
                    continue
                if re.search(rf"\b{re.escape(function_name)}\s*\(", other_content):
                    refs.append(
                        {
                            "function": function_name,
                            "defined_in": name,
                            "referenced_in": other_name,
                        }
                    )
    return refs


def analyze_script_bundle(
    sources: list[Any],
    url: str | None = None,
) -> dict[str, Any]:
    """Analyze multiple scripts as one bundle and report cross-script refs."""
    combined: list[str] = []
    for source in sources:
        content, name = _source_content(source)
        combined.append(f"\n/* ==== {name} ==== */\n{content}")
    analysis = analyze_js("\n".join(combined), url)
    cross_refs = cross_script_refs(sources)
    interprocedural: dict[str, Any] = {}
    try:
        from bundle_taint import analyze_interprocedural_flow

        interprocedural = analyze_interprocedural_flow(
            [
                {"name": name, "content": content}
                for content, name in [_source_content(source) for source in sources]
            ],
            analysis,
        )
    except Exception:
        interprocedural = {"ok": False, "error": "interprocedural taint failed"}
    return {
        "analysis": analysis,
        "cross_refs": cross_refs,
        "interprocedural_flow": interprocedural,
    }


# ---------------------------------------------------------------------------
# HTML / capture extraction
# ---------------------------------------------------------------------------


_SCRIPT_BLOCK_RE = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_SRC_RE = re.compile(r"\bsrc\s*=\s*(['\"])([^'\"]+)\1", re.IGNORECASE)
_TYPE_RE = re.compile(r"\btype\s*=\s*(['\"])([^'\"]+)\1", re.IGNORECASE)
_NAME_RE = re.compile(r"\bname\s*=\s*(['\"])([^'\"]+)\1", re.IGNORECASE)


def extract_scripts(html: str, base_url: str | None = None) -> list[ScriptSource]:
    scripts: list[ScriptSource] = []
    seen: set[tuple[str, str]] = set()
    for index, match in enumerate(_SCRIPT_BLOCK_RE.finditer(html)):
        attrs, content = match.group(1), match.group(2)
        src_match = _SRC_RE.search(attrs)
        src = src_match.group(2) if src_match else None
        if src:
            resolved = urllib.parse.urljoin(base_url or "", src) if base_url else src
            key = ("src", resolved)
            if key not in seen:
                seen.add(key)
                scripts.append(
                    ScriptSource(url=resolved, content="", inline=False, name=Path(resolved).name)
                )
            continue
        type_match = _TYPE_RE.search(attrs)
        script_type = type_match.group(2) if type_match else None
        name_match = _NAME_RE.search(attrs)
        name = name_match.group(2) if name_match else f"inline-{index}"
        if len(content) > MAX_SCRIPT_BYTES:
            content = content[:MAX_SCRIPT_BYTES]
        key = ("inline", name)
        if key not in seen:
            seen.add(key)
            scripts.append(
                ScriptSource(
                    url=base_url,
                    content=content,
                    inline=True,
                    script_type=script_type,
                    name=name,
                )
            )
    return scripts


def _captured_dynamic_fields(url: str, post_data: str | None) -> list[DynamicField]:
    fields: list[DynamicField] = []
    seen: set[tuple[str, str]] = set()
    parsed = urllib.parse.urlsplit(url)
    for key, values in urllib.parse.parse_qs(parsed.query).items():
        if DYNAMIC_NAME_RE.search(key):
            kind, confidence = _classify_dynamic(key, ";".join(values))
            fields.append(
                DynamicField(key, kind, ";".join(values), confidence, source="captured-url")
            )
    if post_data:
        try:
            body = json.loads(post_data)
        except json.JSONDecodeError:
            body = None
        if isinstance(body, dict):
            for key, value in body.items():
                if DYNAMIC_NAME_RE.search(str(key)):
                    kind, confidence = _classify_dynamic(str(key), str(value))
                    fields.append(
                        DynamicField(
                            str(key), kind, str(value)[:160], confidence, source="captured-body"
                        )
                    )
    unique: list[DynamicField] = []
    for entry in fields:
        key = (entry.name, entry.kind)
        if key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def analyze_capture(
    capture: Any,
    *,
    deep_deobfuscation: str = "auto",
    auto_install: bool = False,
    run_bundle: str = "auto",
) -> ReverseReport:
    """Analyze a PageCapture dict/object plus its runtime network traffic."""
    if not isinstance(capture, dict):
        capture = capture.to_dict()  # type: ignore[attr-defined]
    html = str(capture.get("html", "") or "")
    url = str(capture.get("url", "") or "")
    scripts = extract_scripts(html, url)
    merged = JsAnalysis(url=url)
    for script in scripts:
        if not script.inline or not script.content:
            continue
        item = analyze_js(
            script.content,
            script.url or url,
            deep_deobfuscation=deep_deobfuscation,
            auto_install=auto_install,
            run_bundle=run_bundle,
        )
        merged.obfuscation = _merge_obfuscation(merged.obfuscation, item.obfuscation)
        merged.crypto_calls.extend(item.crypto_calls)
        _merge_unique_requests(merged.request_sites, item.request_sites)
        _merge_unique_fields(merged.dynamic_fields, item.dynamic_fields)
        _merge_unique_device(merged.device_fields, item.device_fields)
        _merge_unique_timestamps(merged.timestamp_fields, item.timestamp_fields)
        _merge_unique_links(merged.data_flow, item.data_flow)
        merged.signature_candidates.extend(
            candidate
            for candidate in item.signature_candidates
            if candidate.name not in {existing.name for existing in merged.signature_candidates}
        )
        merged.signature_recipes.extend(
            recipe
            for recipe in item.signature_recipes
            if recipe.function_name
            not in {existing.function_name for existing in merged.signature_recipes}
        )
        merged.ast_data_flow.extend(item.ast_data_flow)
        merged.ast_data_flow_ok = merged.ast_data_flow_ok or item.ast_data_flow_ok
        if item.deobfuscated:
            merged.deobfuscated = item.deobfuscated

    if analyze_page is not None:
        try:
            page = analyze_page(html, url)
            for endpoint in page.api_endpoints:
                merged.request_sites.append(
                    RequestSite(
                        method=endpoint.method,
                        url=endpoint.url,
                        line=0,
                        body=getattr(endpoint, "body", None),
                        params=getattr(endpoint, "params", None) or {},
                        source="page-analysis",
                    )
                )
        except Exception:
            pass

    captured: list[CapturedRequest] = []
    for entry in capture.get("network", []) or []:
        method = str(entry.get("method", "GET") or "GET")
        entry_url = str(entry.get("url", "") or "")
        resource_type = str(entry.get("resource_type", "") or "")
        status = entry.get("status")
        post_data = entry.get("post_data")
        captured.append(
            CapturedRequest(
                method=method,
                url=entry_url,
                resource_type=resource_type,
                status=int(status) if status is not None else None,
                post_data=post_data,
                dynamic_fields=_captured_dynamic_fields(entry_url, post_data),
            )
        )

    node = node_available()
    hook = capture.get("hook") or {}
    function_probes = capture.get("function_probes") or {}
    wasm_calls = capture.get("wasm_calls") or {}
    native_probes = capture.get("native_probes") or {}
    cross_refs = cross_script_refs(scripts)
    summary = {
        "scripts": len(scripts),
        "inline_scripts": sum(1 for script in scripts if script.inline and script.content),
        "crypto_calls": len(merged.crypto_calls),
        "request_sites": len(merged.request_sites),
        "signature_candidates": len(merged.signature_candidates),
        "device_fields": len(merged.device_fields),
        "timestamp_fields": len(merged.timestamp_fields),
        "signature_recipes": len(merged.signature_recipes),
        "data_flow_links": len(merged.data_flow),
        "ast_data_flow_links": len(merged.ast_data_flow),
        "captured_requests": len(captured),
        "hook_requests": len((hook or {}).get("requests", [])),
        "function_calls": len((function_probes or {}).get("function_calls", [])),
        "wasm_calls": len((wasm_calls or {}).get("wasm_calls", [])),
        "native_calls": len((native_probes or {}).get("native_calls", [])),
        "bundle_cross_refs": len(cross_refs),
        "node_available": node,
    }
    return ReverseReport(
        url=url,
        scripts=scripts,
        analysis=merged,
        captured_requests=captured,
        hook=hook,
        function_probes=function_probes,
        wasm_calls=wasm_calls,
        native_probes=native_probes,
        bundle_cross_refs=cross_refs,
        node_available=node,
        summary=summary,
    )


def _merge_obfuscation(a: ObfuscationProfile, b: ObfuscationProfile) -> ObfuscationProfile:
    by_name = {signal.name: signal for signal in a.signals}
    for signal in b.signals:
        if signal.name in by_name:
            existing = by_name[signal.name]
            existing.count += signal.count
            existing.examples.extend(signal.examples)
            existing.examples = existing.examples[:3]
        else:
            by_name[signal.name] = signal
    signals = list(by_name.values())
    score = max(a.score, b.score)
    level = (
        a.level if score < 15 else "minified" if score < 40 else "mild" if score < 70 else "strong"
    )
    return ObfuscationProfile(score=score, level=level, signals=signals)


# ---------------------------------------------------------------------------
# Node bridge
# ---------------------------------------------------------------------------


def node_available() -> bool:
    return bool(shutil.which("node") or os.environ.get("CODEX_NODE"))


def webcrack_available() -> bool:
    return bool(shutil.which("webcrack") or os.environ.get("CODEX_WEBCRACK"))


def jsbeautifier_available() -> bool:
    try:
        import importlib.util

        return importlib.util.find_spec("jsbeautifier") is not None
    except Exception:
        return False


def ensure_jsbeautifier(
    install: bool = True,
    timeout: float = 180.0,
) -> dict[str, Any]:
    """Make jsbeautifier available, auto-installing through pip when needed."""
    if jsbeautifier_available():
        return {"ok": True, "source": "existing"}
    if not install:
        return {"ok": False, "error": "jsbeautifier is not installed"}
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "jsbeautifier"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode == 0 and jsbeautifier_available():
            return {
                "ok": True,
                "source": "pip",
                "stderr": result.stderr[-300:],
            }
        return {
            "ok": False,
            "error": result.stderr[-500:] or "pip install failed",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"pip install timed out after {timeout}s"}


def _npx_command() -> str | None:
    for name in ("npx.cmd", "npx"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _npm_command() -> str | None:
    for name in ("npm.cmd", "npm"):
        path = shutil.which(name)
        if path:
            return path
    return None


def ensure_webcrack(
    install: bool = True,
    timeout: float = 240.0,
) -> dict[str, Any]:
    """Make webcrack available, auto-installing through npx/npm when needed."""
    if webcrack_available():
        return {"ok": True, "source": "existing", "command": shutil.which("webcrack")}
    if not install:
        return {"ok": False, "error": "webcrack is not installed"}
    npx = _npx_command()
    if npx:
        try:
            result = subprocess.run(
                [npx, "--yes", "webcrack", "--version"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode == 0:
                return {
                    "ok": True,
                    "source": "npx-cache",
                    "command": npx,
                    "stderr": result.stderr[-500:],
                }
        except subprocess.TimeoutExpired:
            pass
    npm = _npm_command()
    if npm:
        try:
            result = subprocess.run(
                [npm, "install", "-g", "webcrack"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode == 0:
                return {
                    "ok": True,
                    "source": "npm-global",
                    "command": shutil.which("webcrack") or "webcrack",
                    "stderr": result.stderr[-500:],
                }
        except subprocess.TimeoutExpired:
            pass
    return {
        "ok": False,
        "error": "webcrack auto-install failed: no working npx/npm",
    }


def webcrack_deobfuscate(
    text: str,
    timeout: float = 60.0,
    auto_install: bool = True,
) -> dict[str, Any]:
    """Run the open-source webcrack deobfuscator when it is installed."""
    if not webcrack_available() and auto_install:
        ensure_result = ensure_webcrack(install=True)
        if not ensure_result["ok"]:
            return {"ok": False, "error": ensure_result.get("error", "webcrack unavailable")}
    if not webcrack_available():
        return {"ok": False, "error": "webcrack is not available"}
    tmpdir = Path(tempfile.mkdtemp(prefix="webcrack-"))
    try:
        input_path = tmpdir / "input.js"
        input_path.write_text(text, encoding="utf-8")
        command = os.environ.get("CODEX_WEBCRACK") or shutil.which("webcrack")
        if command:
            argv = [command, str(input_path), "-o", str(tmpdir)]
        else:
            npx = _npx_command()
            if npx is None:
                return {"ok": False, "error": "webcrack command is not available"}
            argv = [npx, "--yes", "webcrack", str(input_path), "-o", str(tmpdir)]
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        outputs = [path for path in tmpdir.rglob("*.js") if path.resolve() != input_path.resolve()]
        output = outputs[0].read_text(encoding="utf-8") if outputs else text
        return {
            "ok": result.returncode == 0,
            "output": output,
            "stderr": result.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"webcrack timed out after {timeout}s"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def acorn_available() -> bool:
    return bool(os.environ.get("CODEX_ACORN") or shutil.which("acorn"))


def ensure_acorn(
    install: bool = True,
    timeout: float = 240.0,
) -> dict[str, Any]:
    """Make the acorn JS parser available through npx when needed."""
    if acorn_available():
        return {"ok": True, "source": "existing"}
    if not install:
        return {"ok": False, "error": "acorn is not installed"}
    npx = _npx_command()
    if npx:
        try:
            result = subprocess.run(
                [npx, "--yes", "-p", "acorn", "node", "-e", "require('acorn')"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if result.returncode == 0:
                return {"ok": True, "source": "npx-cache", "command": npx}
        except subprocess.TimeoutExpired:
            pass
    return {"ok": False, "error": "acorn auto-install failed: no working npx"}


def _acorn_runner(js: str) -> str:
    template = """\
const acorn = require('acorn');
const code = __CODE__;
const ast = acorn.parse(code, { ecmaVersion: 2022, sourceType: 'script', allowReturnOutsideFunction: true });
const out = { functions: [], strings: [], flow: [] };
function sourceSlice(node) {
  try { return code.slice(node.start, node.end); } catch (e) { return ""; }
}
function targetName(node) {
  if (!node) return "";
  if (node.type === "Identifier") return node.name;
  if (node.type === "MemberExpression") return sourceSlice(node);
  if (node.type === "AssignmentPattern") return targetName(node.left);
  return sourceSlice(node);
}
function pushFlow(kind, node, extra) {
  const row = { kind: kind, line: (node.loc && node.loc.start.line) || 0 };
  Object.assign(row, extra || {});
  out.flow.push(row);
}
function walk(node) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'FunctionDeclaration' || node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression') {
    if (node.id && node.id.name) out.functions.push(node.id.name);
  }
  if (node.type === 'Literal' && typeof node.value === 'string' && node.value) out.strings.push(node.value);
  if (node.type === 'VariableDeclaration') {
    for (const decl of node.declarations || []) {
      pushFlow('variable', decl, {
        name: targetName(decl.id),
        init: sourceSlice(decl.init),
        kind: node.kind
      });
    }
  }
  if (node.type === 'AssignmentExpression') {
    pushFlow('assignment', node, {
      target: targetName(node.left),
      value: sourceSlice(node.right),
      operator: node.operator
    });
  }
  if (node.type === 'CallExpression') {
    pushFlow('call', node, {
      callee: sourceSlice(node.callee),
      args: (node.arguments || []).map(sourceSlice).join(',')
    });
  }
  if (node.type === 'ReturnStatement' && node.argument) {
    pushFlow('return', node, { value: sourceSlice(node.argument) });
  }
  for (const key of Object.keys(node)) {
    if (key === 'parent') continue;
    const value = node[key];
    if (Array.isArray(value)) value.forEach(walk);
    else walk(value);
  }
}
walk(ast);
console.log(JSON.stringify(out));
"""
    return template.replace("__CODE__", json.dumps(js, ensure_ascii=False))


def run_acorn(
    js: str,
    timeout: float = 60.0,
    auto_install: bool = True,
) -> dict[str, Any]:
    """Parse JS with the mature acorn library through Node/npx."""
    ensure_result = ensure_acorn(install=auto_install)
    if not ensure_result["ok"]:
        return {"ok": False, "error": ensure_result.get("error", "acorn unavailable")}
    runner = _acorn_runner(js)
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".cjs",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(runner)
        path = handle.name
    try:
        command = os.environ.get("CODEX_ACORN") or shutil.which("acorn")
        if command:
            argv = [command, path]
        else:
            argv = [_npx_command(), "--yes", "-p", "acorn", "node", path]
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            return {
                "ok": False,
                "error": result.stderr[-1000:] or "acorn parse failed",
            }
        data = json.loads(result.stdout.strip())
        return {"ok": True, **data}
    except (json.JSONDecodeError, subprocess.TimeoutExpired, TypeError) as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        with suppress(OSError):
            os.unlink(path)


def acorn_extract_functions(js: str, auto_install: bool = True) -> dict[str, Any]:
    """Extract function names and string literals with acorn."""
    return run_acorn(js, auto_install=auto_install)


SOURCE_MAP_RE = re.compile(r"//[#@]\s*sourceMappingURL\s*=\s*(\S+)", re.IGNORECASE)
_VLQ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_VLQ_LOOKUP = {char: index for index, char in enumerate(_VLQ_CHARS)}


def find_source_mapping_url(js: str) -> str | None:
    """Return the ``sourceMappingURL`` value from a JS bundle."""
    match = SOURCE_MAP_RE.search(js)
    return match.group(1) if match else None


def load_source_map(path_or_url: str) -> dict[str, Any]:
    """Load a source map JSON from a local path or http(s) URL."""
    text = str(path_or_url)
    if text.startswith(("http://", "https://")):
        with urllib.request.urlopen(text, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
    else:
        data = json.loads(Path(text).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _decode_vlq_segment(segment: str) -> list[int] | None:
    values: list[int] = []
    i = 0
    while i < len(segment):
        result = 0
        shift = 0
        while True:
            if i >= len(segment):
                return None
            digit = _VLQ_LOOKUP.get(segment[i])
            if digit is None:
                return None
            i += 1
            continuation = bool(digit & 32)
            digit &= 31
            result += digit << shift
            shift += 5
            if not continuation:
                break
        negate = result & 1
        result >>= 1
        values.append(-result if negate else result)
    return values


def decode_vlq_mappings(mappings: str) -> list[dict[str, int | None]]:
    """Decode source-map ``mappings`` into generated/original positions."""
    decoded: list[dict[str, int | None]] = []
    source_index = 0
    original_line = 0
    original_column = 0
    name_index = 0
    for line_index, line_text in enumerate(mappings.split(";")):
        generated_column = 0
        for segment in line_text.split(","):
            if not segment:
                continue
            values = _decode_vlq_segment(segment)
            if not values:
                continue
            generated_column += values[0]
            row: dict[str, int | None] = {
                "generated_line": line_index,
                "generated_column": generated_column,
                "source_index": None,
                "original_line": None,
                "original_column": None,
                "name_index": None,
            }
            if len(values) >= 4:
                source_index += values[1]
                original_line += values[2]
                original_column += values[3]
                row["source_index"] = source_index
                row["original_line"] = original_line
                row["original_column"] = original_column
            if len(values) >= 5:
                name_index += values[4]
                row["name_index"] = name_index
            decoded.append(row)
    return decoded


def map_position(
    source_map: dict[str, Any],
    line: int,
    column: int = 0,
) -> dict[str, Any]:
    """Map a generated line/column back to the original source position."""
    sources = source_map.get("sources", []) or []
    names = source_map.get("names", []) or []
    rows = decode_vlq_mappings(str(source_map.get("mappings", "") or ""))
    candidates = [
        row
        for row in rows
        if row["generated_line"] == max(0, line - 1)
        and row["generated_column"] is not None
        and row["generated_column"] <= column
    ]
    if not candidates:
        return {"generated_line": line, "generated_column": column}
    best = max(candidates, key=lambda item: int(item["generated_column"] or 0))
    result = {
        "generated_line": line,
        "generated_column": column,
        "original_line": (int(best["original_line"] or 0) + 1)
        if best["original_line"] is not None
        else None,
        "original_column": best["original_column"],
        "source": (
            sources[int(best["source_index"])]
            if best["source_index"] is not None and 0 <= int(best["source_index"]) < len(sources)
            else None
        ),
    }
    if best["name_index"] is not None and 0 <= int(best["name_index"]) < len(names):
        result["name"] = names[int(best["name_index"])]
    return result


def analyze_source_map(
    js: str,
    source_map_path: str | None = None,
    js_path: str | None = None,
) -> dict[str, Any]:
    """Load and summarize a source map, optionally found in the JS itself."""
    if not source_map_path and js_path:
        url = find_source_mapping_url(js)
        if url and not url.startswith(("http://", "https://")):
            candidate = Path(js_path).parent / url
            if candidate.exists():
                source_map_path = str(candidate)
    if not source_map_path:
        return {"ok": False, "error": "no source map path or sourceMappingURL found"}
    try:
        data = load_source_map(source_map_path)
        rows = decode_vlq_mappings(str(data.get("mappings", "") or ""))
        return {
            "ok": True,
            "source_map": source_map_path,
            "sources": data.get("sources", []) or [],
            "names": data.get("names", []) or [],
            "mappings": len(rows),
            "mapped_lines": len({row["generated_line"] for row in rows}),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def map_analysis_lines(
    analysis: JsAnalysis,
    source_map: dict[str, Any],
) -> list[dict[str, Any]]:
    """Map detected signature candidates / request sites to original sources."""
    mapped: list[dict[str, Any]] = []
    for candidate in analysis.signature_candidates:
        position = map_position(source_map, candidate.line, 0)
        mapped.append(
            {
                "kind": "signature_candidate",
                "name": candidate.name,
                "generated_line": candidate.line,
                **position,
            }
        )
    for site in analysis.request_sites:
        position = map_position(source_map, site.line, 0)
        mapped.append(
            {
                "kind": "request_site",
                "method": site.method,
                "url": site.url,
                "generated_line": site.line,
                **position,
            }
        )
    return mapped


def _node_command() -> str:
    return os.environ.get("CODEX_NODE") or shutil.which("node") or "node"


def node_browser_stubs() -> str:
    """Return minimal browser globals so extracted page functions run in Node."""
    return r"""
if (!globalThis.window) globalThis.window = globalThis;
if (!globalThis.self) globalThis.self = globalThis;
Object.defineProperty(globalThis, "navigator", {
  value: {
    userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    platform: "Win32",
    language: "zh-CN",
    languages: ["zh-CN", "zh", "en"],
    hardwareConcurrency: 8,
    deviceMemory: 8,
    maxTouchPoints: 0,
    cookieEnabled: true,
    doNotTrack: null,
    webdriver: false,
    vendor: "Google Inc.",
    plugins: [],
    connection: { effectiveType: "4g" }
  },
  configurable: true
});
if (!globalThis.screen) {
  globalThis.screen = {
    width: 1920,
    height: 1080,
    availWidth: 1920,
    availHeight: 1040,
    colorDepth: 24,
    pixelDepth: 24,
    orientation: { type: "landscape-primary" }
  };
}
if (!globalThis.document) {
  globalThis.document = {
    cookie: "",
    createElement: function () {
      return {
        width: 0,
        height: 0,
        getContext: function () { return null; },
        toDataURL: function () { return ""; },
        getExtension: function () { return null; }
      };
    },
    fonts: { ready: Promise.resolve() }
  };
}
if (globalThis.devicePixelRatio === undefined) globalThis.devicePixelRatio = 1;
if (!globalThis.localStorage) {
  var _local = {};
  globalThis.localStorage = {
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(_local, k) ? _local[k] : null; },
    setItem: function (k, v) { _local[k] = String(v); },
    removeItem: function (k) { delete _local[k]; },
    clear: function () { _local = {}; },
    key: function (i) { return Object.keys(_local)[i] || null; },
    length: 0
  };
}
if (!globalThis.sessionStorage) globalThis.sessionStorage = globalThis.localStorage;
if (!globalThis.performance) globalThis.performance = { now: function () { return Date.now(); } };
if (!globalThis.crypto && typeof require !== "undefined") {
  globalThis.crypto = require("crypto").webcrypto;
}
""".strip()


def run_js(script: str, timeout: float = 10.0) -> dict[str, Any]:
    """Run JS locally with Node and return stdout/stderr/status."""
    if not node_available():
        return {"ok": False, "error": "node is not available", "returncode": -1}
    start = time.monotonic()
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".cjs",
        encoding="utf-8",
        delete=False,
    ) as handle:
        handle.write(script)
        path = handle.name
    try:
        result = subprocess.run(
            [_node_command(), path],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-20000:],
            "stderr": result.stderr[-5000:],
            "duration_ms": round((time.monotonic() - start) * 1000, 1),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {timeout}s", "returncode": -1}
    finally:
        with suppress(OSError):
            os.unlink(path)


def evaluate_js(expression: str, timeout: float = 10.0) -> dict[str, Any]:
    """Evaluate a JS expression with Node and return JSON output."""
    script = (
        node_browser_stubs()
        + "\ntry { console.log('__RESULT__' + JSON.stringify(eval("
        + json.dumps(expression, ensure_ascii=False)
        + "))); } catch (e) { console.error('__ERROR__' + (e && e.stack || String(e))); process.exit(2); }"
    )
    result = run_js(script, timeout=timeout)
    if not result["ok"]:
        return result
    out = result["stdout"]
    marker = "__RESULT__"
    if marker not in out:
        return {**result, "ok": False, "error": "no result marker"}
    try:
        value = json.loads(out.split(marker, 1)[1].strip())
        return {**result, "ok": True, "value": value}
    except json.JSONDecodeError as exc:
        return {**result, "ok": False, "error": f"invalid JSON result: {exc}"}


def run_signature_function(
    js: str,
    function_name: str,
    args: list[Any] | None = None,
    timeout: float = 10.0,
    browser_stubs: bool = True,
) -> dict[str, Any]:
    """Prepend JS and call a named function with Node."""
    args_json = json.dumps(args or [], ensure_ascii=False)
    call = f"JSON.stringify(({function_name})(...{args_json}))"
    script = (
        f"{node_browser_stubs() if browser_stubs else ''}\n{js}\n"
        f"try {{ console.log('__RESULT__' + {call}); }} "
        "catch (e) { console.error('__ERROR__' + (e && e.stack || String(e))); process.exit(2); }"
    )
    result = run_js(script, timeout=timeout)
    if not result["ok"]:
        return result
    out = result["stdout"]
    marker = "__RESULT__"
    if marker not in out:
        return {**result, "ok": False, "error": "no result marker"}
    try:
        value = json.loads(out.split(marker, 1)[1].strip())
        return {**result, "ok": True, "value": value}
    except json.JSONDecodeError as exc:
        return {**result, "ok": False, "error": f"invalid JSON result: {exc}"}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _self_test() -> None:
    obfuscated = (
        'var _0xabc=["sign","token"];'
        'function build(){var _0x1=atob("c2lnbg==");'
        'return fetch("/api/x?sign="+_0xabc[0]+"&t="+Date.now(),'
        '{method:"POST",headers:{"X-Token":_0xabc[1]},'
        'body:JSON.stringify({nonce:_0x1,sig:md5("a")})});}'
    )
    analysis = analyze_js(obfuscated)
    assert analysis.obfuscation.score >= 20
    assert any(call.algorithm == "MD5" for call in analysis.crypto_calls)
    assert any(site.dynamic_fields for site in analysis.request_sites)
    assert any(
        field.category == "canvas"
        for field in analyze_device_fingerprint('canvas.getContext("2d").toDataURL()')
    )
    assert any(
        field.unit == "seconds" for field in analyze_timestamp_fields("Math.floor(Date.now()/1000)")
    )
    assert any(recipe.function_name for recipe in analysis.signature_recipes)
    print("deep_reverse self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deep reverse engineering for web scripts")
    parser.add_argument("--html", default=None, help="HTML file containing inline scripts")
    parser.add_argument("--capture", default=None, help="PageCapture JSON file")
    parser.add_argument("--js", default=None, help="standalone JS bundle file")
    parser.add_argument("--output", default=None, help="write JSON report")
    parser.add_argument(
        "--deobfuscate", action="store_true", help="include deobfuscated source in output"
    )
    parser.add_argument(
        "--webcrack",
        action="store_true",
        help="use external webcrack deobfuscator (auto-installs via npx/npm when needed)",
    )
    parser.add_argument(
        "--source-map",
        default=None,
        help="source map JSON file for --js input",
    )
    parser.add_argument(
        "--dynamic-decode",
        action="store_true",
        help="execute suspected string decoders in Node to resolve _0x arrays",
    )
    parser.add_argument(
        "--acorn",
        action="store_true",
        help="parse JS with acorn via npx (auto-installs when needed)",
    )
    parser.add_argument(
        "--install-beautifier",
        action="store_true",
        help="auto-install jsbeautifier through pip",
    )
    parser.add_argument(
        "--deep-deobfuscation",
        default="auto",
        choices=("auto", "always", "disabled"),
        help="enable deep deobfuscation on strong obfuscation",
    )
    parser.add_argument(
        "--run-bundle",
        default="auto",
        choices=("auto", "always", "disabled"),
        help="execute whole JS bundles in Node on demand",
    )
    parser.add_argument("--eval", default=None, help="evaluate a JS expression with Node")
    parser.add_argument(
        "--run-function", default=None, help="call a named signature function with Node"
    )
    parser.add_argument("--args", default="[]", help="JSON array of arguments for --run-function")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        _self_test()
        return 0

    if args.eval:
        result = evaluate_js(args.eval)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2

    if args.run_function:
        if not args.js:
            parser.error("--run-function requires --js")
        js = Path(args.js).read_text(encoding="utf-8")
        try:
            arg_list = json.loads(args.args)
        except json.JSONDecodeError:
            cleaned = args.args.strip().strip("[]")
            arg_list = [item.strip().strip("'\"") for item in cleaned.split(",") if item.strip()]
            if not isinstance(arg_list, list):
                parser.error("--args must be a JSON array")
        result = run_signature_function(js, args.run_function, arg_list)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 2

    report: ReverseReport | None = None
    if args.html:
        html = Path(args.html).read_text(encoding="utf-8")
        url = str(Path(args.html).resolve())
        report = analyze_capture(
            {"url": url, "html": html, "network": []},
            deep_deobfuscation=args.deep_deobfuscation,
            run_bundle=args.run_bundle,
        )
    elif args.capture:
        capture = json.loads(Path(args.capture).read_text(encoding="utf-8"))
        report = analyze_capture(
            capture,
            deep_deobfuscation=args.deep_deobfuscation,
            run_bundle=args.run_bundle,
        )
    elif args.js:
        js = Path(args.js).read_text(encoding="utf-8")
        url = str(Path(args.js).resolve())
        if args.install_beautifier:
            beautify_result = ensure_jsbeautifier(install=True)
            if not beautify_result["ok"]:
                print(
                    f"jsbeautifier install failed: {beautify_result.get('error')}",
                    file=sys.stderr,
                )
        analysis = analyze_js(
            js,
            url,
            deep_deobfuscation=args.deep_deobfuscation,
            run_bundle=args.run_bundle,
        )
        if args.acorn:
            acorn_result = acorn_extract_functions(js)
            if acorn_result.get("ok"):
                analysis.bundle["acorn"] = {
                    "functions": acorn_result.get("functions", []),
                    "strings": acorn_result.get("strings", []),
                }
            else:
                print(
                    f"acorn unavailable: {acorn_result.get('error')}",
                    file=sys.stderr,
                )
        source_map: dict[str, Any] = {}
        if args.source_map:
            source_map = analyze_source_map(
                js,
                source_map_path=args.source_map,
                js_path=url,
            )
            if source_map.get("ok"):
                source_map["mapped_analysis"] = map_analysis_lines(
                    analysis,
                    load_source_map(args.source_map),
                )
        if args.dynamic_decode:
            dynamic = decode_string_arrays_dynamic(js)
            if dynamic.passes:
                analysis.deobfuscated = DeobfuscationResult(
                    output=dynamic.output,
                    passes=(analysis.deobfuscated.passes if analysis.deobfuscated else [])
                    + dynamic.passes,
                )
        if args.webcrack:
            result = webcrack_deobfuscate(js, auto_install=True)
            if result.get("ok"):
                analysis.deobfuscated = DeobfuscationResult(
                    output=str(result.get("output", "")),
                    passes=["webcrack"],
                )
            else:
                print(f"webcrack unavailable: {result.get('error')}", file=sys.stderr)
        report = ReverseReport(
            url=url,
            scripts=[ScriptSource(url=url, content=js, inline=False, name=Path(args.js).name)],
            analysis=analysis,
            source_map=source_map,
            node_available=node_available(),
            summary={
                "scripts": 1,
                "inline_scripts": 0,
                "crypto_calls": len(analysis.crypto_calls),
                "request_sites": len(analysis.request_sites),
                "signature_candidates": len(analysis.signature_candidates),
                "device_fields": len(analysis.device_fields),
                "timestamp_fields": len(analysis.timestamp_fields),
                "signature_recipes": len(analysis.signature_recipes),
                "data_flow_links": len(analysis.data_flow),
                "captured_requests": 0,
                "node_available": node_available(),
            },
        )
    else:
        parser.error(
            "one of --html, --capture, --js, --eval, --run-function, --self-test is required"
        )

    if report is None:
        parser.error("analysis produced no report")
    data = report.to_dict()
    if not args.deobfuscate and report.analysis.deobfuscated:
        data["analysis"]["deobfuscated"] = {
            "passes": report.analysis.deobfuscated.passes,
            "size": len(report.analysis.deobfuscated.output),
            "output": "" if not args.deobfuscate else report.analysis.deobfuscated.output,
        }
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
