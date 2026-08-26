"""Cross-request reverse-engineering laboratory.

``deep_reverse.py`` explains one script or one capture.  This module works
with a set of captures: it diffs requests to the same endpoint, correlates
timestamp parameters with the moment the hook captured the request, hashes
device snapshots into stable tokens, and tries common signature constructions
against real captured values to find the actual algorithm and secret.

It is dependency-free and works with:

- ``deep_hook.py`` JSON output (``hook.requests`` + ``network``)
- ``PageCapture`` JSON files (``network`` entries)
- ``deep_reverse.py`` JSON reports (``captured_requests``)
"""

from __future__ import annotations

import argparse
import base64
import email.utils
import hashlib
import hmac
import json
import random
import re
import time
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from deep_reverse import (
        SignatureRecipe,
        extract_secret_hints,
        find_function_names,
        node_available,
        run_signature_function,
    )
except Exception:  # pragma: no cover - scripts directory is normally on sys.path
    SignatureRecipe = object  # type: ignore[assignment]

    def extract_secret_hints(js: str) -> list[str]:
        return []

    def find_function_names(js: str) -> list[str]:
        return []

    def node_available() -> bool:
        return False

    run_signature_function = None  # type: ignore[assignment]


@dataclass
class RequestDiff:
    method: str
    path: str
    samples: int
    constant_params: dict[str, Any] = field(default_factory=dict)
    changing_params: dict[str, list[Any]] = field(default_factory=dict)
    signature_params: list[str] = field(default_factory=list)
    timestamp_params: list[str] = field(default_factory=list)
    device_params: list[str] = field(default_factory=list)
    constant_headers: dict[str, str] = field(default_factory=dict)
    changing_headers: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "samples": self.samples,
            "constant_params": self.constant_params,
            "changing_params": self.changing_params,
            "signature_params": self.signature_params,
            "timestamp_params": self.timestamp_params,
            "device_params": self.device_params,
            "constant_headers": self.constant_headers,
            "changing_headers": self.changing_headers,
        }


@dataclass
class TimestampCorrelation:
    url: str
    param: str
    value: str
    captured_at_ms: int
    unit: str
    delta_ms: int
    confidence: float
    server_synced: bool = False
    server_delta_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "param": self.param,
            "value": self.value,
            "captured_at_ms": self.captured_at_ms,
            "unit": self.unit,
            "delta_ms": self.delta_ms,
            "confidence": round(self.confidence, 2),
            "server_synced": self.server_synced,
            "server_delta_ms": self.server_delta_ms,
        }


@dataclass
class ServerClockOffset:
    url: str
    header: str
    server_time_ms: int
    captured_at_ms: int
    delta_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "header": self.header,
            "server_time_ms": self.server_time_ms,
            "captured_at_ms": self.captured_at_ms,
            "delta_ms": self.delta_ms,
        }


@dataclass
class ResponseErrorSignal:
    url: str
    status: int
    error_text: str
    hint: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "error_text": self.error_text[:300],
            "hint": self.hint,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class FingerprintToken:
    name: str
    value: str
    sha256: str
    stable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value[:240],
            "sha256": self.sha256,
            "stable": self.stable,
        }


@dataclass
class SignatureVerification:
    url: str
    signature_param: str
    pattern: str
    secret: str
    algorithm: str
    payload: str
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "signature_param": self.signature_param,
            "pattern": self.pattern,
            "secret": self.secret,
            "algorithm": self.algorithm,
            "payload": self.payload[:240],
            "verified": self.verified,
        }


@dataclass
class SignatureConsistency:
    pattern: str
    secret: str
    algorithm: str
    verified_samples: int
    total_samples: int
    confidence: float
    sample_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "secret": self.secret,
            "algorithm": self.algorithm,
            "verified_samples": self.verified_samples,
            "total_samples": self.total_samples,
            "confidence": round(self.confidence, 2),
            "sample_urls": self.sample_urls[:20],
        }


@dataclass
class DeviceParamMatch:
    url: str
    param: str
    value: str
    fingerprint_sha256: str
    candidate: str
    algorithm: str
    matched: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "param": self.param,
            "value": self.value[:240],
            "fingerprint_sha256": self.fingerprint_sha256,
            "candidate": self.candidate[:240],
            "algorithm": self.algorithm,
            "matched": self.matched,
        }


@dataclass
class StorageDiff:
    bucket: str
    key: str
    values: list[str]
    changed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "bucket": self.bucket,
            "key": self.key,
            "values": self.values[:20],
            "changed": self.changed,
        }


@dataclass
class JsReplayVerification:
    function_name: str
    kind: str
    captured_value: str
    computed_value: str
    matched: bool
    error: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "function_name": self.function_name,
            "kind": self.kind,
            "captured_value": self.captured_value[:240],
            "computed_value": self.computed_value[:240],
            "matched": self.matched,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SignatureCoverage:
    url: str
    signature_param: str
    signed_params: list[str]
    unsigned_params: list[str]
    total_params: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "signature_param": self.signature_param,
            "signed_params": self.signed_params[:50],
            "unsigned_params": self.unsigned_params[:50],
            "total_params": self.total_params,
        }


@dataclass
class ReverseLabReport:
    request_diffs: list[RequestDiff] = field(default_factory=list)
    timestamp_correlations: list[TimestampCorrelation] = field(default_factory=list)
    server_clock_offsets: list[ServerClockOffset] = field(default_factory=list)
    fingerprint_tokens: list[FingerprintToken] = field(default_factory=list)
    fingerprint_sha256: str = ""
    signature_verifications: list[SignatureVerification] = field(default_factory=list)
    signature_consistency: list[SignatureConsistency] = field(default_factory=list)
    device_param_matches: list[DeviceParamMatch] = field(default_factory=list)
    brute_force_secrets: list[str] = field(default_factory=list)
    storage_diffs: list[StorageDiff] = field(default_factory=list)
    generated_python: list[str] = field(default_factory=list)
    generated_node: list[str] = field(default_factory=list)
    generated_request_builders: list[str] = field(default_factory=list)
    generated_node_request_builders: list[str] = field(default_factory=list)
    generated_device_python: list[str] = field(default_factory=list)
    js_replay_verifications: list[JsReplayVerification] = field(default_factory=list)
    signature_coverages: list[SignatureCoverage] = field(default_factory=list)
    response_error_signals: list[ResponseErrorSignal] = field(default_factory=list)
    active_diff: dict[str, Any] = field(default_factory=dict)
    secret_inference: dict[str, Any] = field(default_factory=dict)
    knowledge: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_diffs": [item.to_dict() for item in self.request_diffs],
            "timestamp_correlations": [item.to_dict() for item in self.timestamp_correlations],
            "server_clock_offsets": [item.to_dict() for item in self.server_clock_offsets],
            "fingerprint_tokens": [item.to_dict() for item in self.fingerprint_tokens],
            "fingerprint_sha256": self.fingerprint_sha256,
            "signature_verifications": [item.to_dict() for item in self.signature_verifications],
            "signature_consistency": [item.to_dict() for item in self.signature_consistency],
            "device_param_matches": [item.to_dict() for item in self.device_param_matches],
            "brute_force_secrets": self.brute_force_secrets,
            "storage_diffs": [item.to_dict() for item in self.storage_diffs],
            "generated_python": self.generated_python,
            "generated_node": self.generated_node,
            "generated_request_builders": self.generated_request_builders,
            "generated_node_request_builders": self.generated_node_request_builders,
            "generated_device_python": self.generated_device_python,
            "js_replay_verifications": [item.to_dict() for item in self.js_replay_verifications],
            "signature_coverages": [item.to_dict() for item in self.signature_coverages],
            "response_error_signals": [item.to_dict() for item in self.response_error_signals],
            "active_diff": self.active_diff,
            "secret_inference": self.secret_inference,
            "knowledge": self.knowledge,
            "summary": self.summary,
        }


SIGNATURE_PARAM_RE = re.compile(
    r"^(?:sign|sig|signature|token|access_token|x_sign|x-sign|_sign|auth|authorization|"
    r"encrypt|encrypted|payload|cipher|data|params|body|hmac|hash|md5|sha256)$",
    re.IGNORECASE,
)
TIMESTAMP_PARAM_RE = re.compile(
    r"^(?:ts|timestamp|time|st|_t|nonce|expire|expires|deadline|ttl|datetime|date)$",
    re.IGNORECASE,
)
DEVICE_PARAM_RE = re.compile(
    r"^(?:device|deviceid|device_id|did|clientid|client_id|fingerprint|fp|finger|"
    r"ua|useragent|platform|screen|canvas|webgl|timezone|language|lang|hardware|"
    r"browser|os|appversion|version|channel|installid|install_id|sessionid|session_id)$",
    re.IGNORECASE,
)


def _iter_requests(capture: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    hook = capture.get("hook") or {}
    for entry in hook.get("requests", []) or []:
        if isinstance(entry, dict):
            out.append(entry)
    for entry in capture.get("network", []) or []:
        if isinstance(entry, dict):
            out.append(entry)
    for entry in capture.get("captured_requests", []) or []:
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _request_params(request: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    url = str(request.get("url", "") or "")
    parsed = urllib.parse.urlsplit(url)
    query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    body: dict[str, Any] = {}
    raw_body = request.get("body") or request.get("post_data")
    if isinstance(raw_body, dict):
        body = dict(raw_body)
    elif isinstance(raw_body, str):
        try:
            parsed_body = json.loads(raw_body)
            if isinstance(parsed_body, dict):
                body = parsed_body
        except json.JSONDecodeError:
            try:
                body = dict(urllib.parse.parse_qsl(raw_body, keep_blank_values=True))
            except Exception:
                body = {}
    headers = request.get("headers") or request.get("request_headers") or {}
    if not isinstance(headers, dict):
        headers = {}
    return {**query, **body}, {str(k): str(v) for k, v in headers.items()}


def _flatten_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}

    def walk(value: Any, prefix: str = "") -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                walk(child, path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{prefix}[{index}]")
        else:
            out[prefix] = value

    walk(params)
    return out


def diff_captured_requests(captures: list[dict[str, Any]]) -> list[RequestDiff]:
    """Diff repeated requests to the same endpoint."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for capture in captures:
        for request in _iter_requests(capture):
            method = str(request.get("method", "GET") or "GET").upper()
            url = str(request.get("url", "") or "")
            path = urllib.parse.urlsplit(url).path
            groups.setdefault((method, path), []).append(request)

    diffs: list[RequestDiff] = []
    for (method, path), samples in sorted(groups.items()):
        parsed = [_request_params(request) for request in samples]
        all_params: set[str] = set()
        for params, _headers in parsed:
            all_params.update(params)
        constant: dict[str, Any] = {}
        changing: dict[str, list[Any]] = {}
        for name in sorted(all_params):
            values = [str(params.get(name, "<missing>")) for params, _ in parsed]
            if len(set(values)) == 1:
                constant[name] = values[0]
            else:
                changing[name] = values
        all_headers: set[str] = set()
        for _params, headers in parsed:
            all_headers.update(headers)
        constant_headers: dict[str, str] = {}
        changing_headers: dict[str, list[str]] = {}
        for name in sorted(all_headers):
            values = [headers.get(name, "<missing>") for _params, headers in parsed]
            if len(set(values)) == 1:
                constant_headers[name] = values[0]
            else:
                changing_headers[name] = values
        names = list(all_params)
        diffs.append(
            RequestDiff(
                method=method,
                path=path,
                samples=len(samples),
                constant_params=constant,
                changing_params=changing,
                signature_params=[name for name in names if SIGNATURE_PARAM_RE.search(name)],
                timestamp_params=[name for name in names if TIMESTAMP_PARAM_RE.search(name)],
                device_params=[name for name in names if DEVICE_PARAM_RE.search(name)],
                constant_headers=constant_headers,
                changing_headers=changing_headers,
            )
        )
    return diffs


def _parse_timestamp_value(value: Any) -> tuple[int, str] | None:
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(("0x", "0X")):
        try:
            return int(text, 16), "hex"
        except ValueError:
            return None
    try:
        number = int(text)
    except ValueError:
        try:
            number = int(text, 36)
            return number, "base36"
        except ValueError:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
                return int(parsed.timestamp() * 1000), "iso8601"
            except ValueError:
                return None
    digits = len(text)
    if digits <= 10:
        return number * 1000, "seconds"
    if digits <= 13:
        return number, "milliseconds"
    return number, "microseconds"


def _parse_header_timestamp(value: Any) -> tuple[int, str] | None:
    parsed = _parse_timestamp_value(value)
    if parsed:
        return parsed
    try:
        parsed_date = email.utils.parsedate_to_datetime(str(value).strip())
        return int(parsed_date.timestamp() * 1000), "http-date"
    except (TypeError, ValueError, OverflowError):
        return None


def correlate_timestamps(captures: list[dict[str, Any]]) -> list[TimestampCorrelation]:
    """Correlate timestamp params with hook capture time."""
    correlations: list[TimestampCorrelation] = []
    for capture in captures:
        for request in _iter_requests(capture):
            captured_at_ms = request.get("captured_at_ms")
            if not isinstance(captured_at_ms, int | float):
                continue
            params, headers = _request_params(request)
            url = str(request.get("url", "") or "")
            for name, value in params.items():
                if not TIMESTAMP_PARAM_RE.search(str(name)):
                    continue
                parsed = _parse_timestamp_value(value)
                if parsed is None:
                    continue
                ts_ms, unit = parsed
                delta_ms = int(captured_at_ms) - ts_ms
                confidence = 0.92 if abs(delta_ms) < 60_000 else 0.55
                correlations.append(
                    TimestampCorrelation(
                        url=url,
                        param=str(name),
                        value=str(value),
                        captured_at_ms=int(captured_at_ms),
                        unit=unit,
                        delta_ms=delta_ms,
                        confidence=confidence,
                    )
                )
            for name, value in headers.items():
                header_key = re.sub(r"^x-", "", str(name), flags=re.IGNORECASE)
                if not TIMESTAMP_PARAM_RE.search(header_key):
                    continue
                parsed = _parse_header_timestamp(value)
                if parsed is None:
                    continue
                ts_ms, unit = parsed
                delta_ms = int(captured_at_ms) - ts_ms
                confidence = 0.92 if abs(delta_ms) < 60_000 else 0.55
                correlations.append(
                    TimestampCorrelation(
                        url=url,
                        param=str(name),
                        value=str(value),
                        captured_at_ms=int(captured_at_ms),
                        unit=unit,
                        delta_ms=delta_ms,
                        confidence=confidence,
                    )
                )
    correlations.sort(key=lambda item: abs(item.delta_ms))
    return correlations


SERVER_TIME_HEADERS = (
    "date",
    "x-server-time",
    "server-time",
    "x-timestamp",
    "server-timestamp",
)


def _parse_server_time(value: str) -> int | None:
    text = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        return int(parsed.timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        number = int(text)
        return number * 1000 if len(text) <= 10 else number
    except ValueError:
        return None


def server_clock_offsets(captures: list[dict[str, Any]]) -> list[ServerClockOffset]:
    """Compare server response time headers with hook capture time."""
    offsets: list[ServerClockOffset] = []
    for capture in captures:
        hook_by_key: dict[tuple[str, str], int] = {}
        for request in (capture.get("hook") or {}).get("requests", []) or []:
            if not isinstance(request, dict):
                continue
            captured = request.get("captured_at_ms")
            if isinstance(captured, int | float):
                key = (str(request.get("method", "") or ""), str(request.get("url", "") or ""))
                hook_by_key[key] = int(captured)
        for entry in capture.get("network", []) or []:
            if not isinstance(entry, dict):
                continue
            headers = entry.get("response_headers") or {}
            if not isinstance(headers, dict):
                continue
            key = (str(entry.get("method", "") or ""), str(entry.get("url", "") or ""))
            captured = hook_by_key.get(key)
            if captured is None:
                continue
            url = str(entry.get("url", "") or "")
            for name, value in headers.items():
                if str(name).lower() not in SERVER_TIME_HEADERS:
                    continue
                server_ms = _parse_server_time(str(value))
                if server_ms is not None:
                    offsets.append(
                        ServerClockOffset(
                            url=url,
                            header=str(name),
                            server_time_ms=server_ms,
                            captured_at_ms=captured,
                            delta_ms=server_ms - captured,
                        )
                    )
    offsets.sort(key=lambda item: abs(item.delta_ms))
    return offsets


_ERROR_HINT_RE = (
    (
        "signature",
        re.compile(r"signature|sign\b|sig\b|校验|签名|md5|sha|hmac|token|鉴权|auth", re.IGNORECASE),
    ),
    (
        "timestamp",
        re.compile(r"timestamp|ts\b|time\b|expire|expired|过期|超时|时间戳", re.IGNORECASE),
    ),
    (
        "device",
        re.compile(r"device|fingerprint|设备|指纹|canvas|webgl|ua\b|platform|风控", re.IGNORECASE),
    ),
    (
        "param",
        re.compile(r"param|parameter|参数|missing|invalid|required|格式", re.IGNORECASE),
    ),
)


def _error_text(entry: dict[str, Any]) -> str:
    for key in ("body", "body_text", "json", "json_data"):
        value = entry.get(key)
        if value:
            if isinstance(value, dict | list):
                value = json.dumps(value, ensure_ascii=False)
            return str(value)
    return ""


def response_error_signals(captures: list[dict[str, Any]]) -> list[ResponseErrorSignal]:
    """Turn 4xx/5xx response bodies into reverse-engineering hints."""
    rows: list[ResponseErrorSignal] = []
    for capture in captures:
        for request in _iter_requests(capture):
            status = request.get("status")
            if not isinstance(status, int) or status < 400:
                continue
            text = _error_text(request)
            if not text:
                continue
            hints = [name for name, pattern in _ERROR_HINT_RE if pattern.search(text)]
            hint = hints[0] if hints else "other"
            rows.append(
                ResponseErrorSignal(
                    url=str(request.get("url", "") or ""),
                    status=status,
                    error_text=text,
                    hint=hint,
                    confidence=0.9 if hints else 0.4,
                )
            )
    rows.sort(key=lambda item: item.status)
    return rows


def _flatten(value: Any, prefix: str = "", out: dict[str, str] | None = None) -> dict[str, str]:
    out = out if out is not None else {}
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            _flatten(child, path, out)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _flatten(child, f"{prefix}[{index}]", out)
    else:
        out[prefix] = str(value)
    return out


def tokenize_device_snapshot(snapshot: Any) -> tuple[list[FingerprintToken], str]:
    """Flatten a hook device snapshot and hash it into stable tokens."""
    if not isinstance(snapshot, dict):
        return [], ""
    flat = _flatten(snapshot)
    tokens: list[FingerprintToken] = []
    canonical: list[str] = []
    for name in sorted(flat):
        value = flat[name]
        digest = hashlib.sha256(f"{name}={value}".encode()).hexdigest()
        stable = name not in {"canvas", "webgl", "captured_at_ms", "performance_ms"}
        tokens.append(FingerprintToken(name=name, value=value, sha256=digest, stable=stable))
        canonical.append(f"{name}={value}")
    full = hashlib.sha256("&".join(canonical).encode()).hexdigest()
    return tokens, full


def _payload_serializations(params: dict[str, Any]) -> list[str]:
    items = sorted((str(k), str(v)) for k, v in params.items())
    original = list(params.items())
    return [
        urllib.parse.urlencode(original),
        urllib.parse.urlencode(items),
        "&".join(f"{key}={value}" for key, value in items),
        ";".join(f"{key}={value}" for key, value in items),
        "".join(f"{key}={value}" for key, value in items),
        "".join(value for _key, value in items),
        "".join(key for key, _value in items),
        json.dumps(dict(items), ensure_ascii=False, sort_keys=True),
        json.dumps(
            dict(original),
            ensure_ascii=False,
            sort_keys=False,
            separators=(",", ":"),
        ),
    ]


def _payload_bytes(text: str) -> list[bytes]:
    return [text.encode("utf-8"), text.encode("utf-16-le")]


def _payload_with_url(payload: str, url: str) -> list[str]:
    parsed = urllib.parse.urlsplit(url)
    path = parsed.path or ""
    forms = [f"{payload}&{path}", f"{path}&{payload}", f"{payload}{path}"]
    return list(dict.fromkeys(forms))


AUTH_HEADER_RE = re.compile(
    r"token|auth|cookie|sign|nonce|timestamp|device|fingerprint|x-request-id",
    re.IGNORECASE,
)


def _payload_with_headers(payload: str, headers: dict[str, str]) -> list[str]:
    selected = {key: value for key, value in headers.items() if AUTH_HEADER_RE.search(str(key))}
    items = sorted((str(key), str(value)) for key, value in selected.items())
    if not items:
        return []
    forms = [
        urllib.parse.urlencode(items),
        "&".join(f"{key}={value}" for key, value in items),
        "".join(f"{key}={value}" for key, value in items),
    ]
    return [f"{payload}&{form}" for form in forms] + [f"{form}&{payload}" for form in forms]


def _raw_body_payloads(request: dict[str, Any], headers: dict[str, str]) -> list[str]:
    raw = request.get("body") or request.get("post_data")
    if isinstance(raw, dict):
        raw_text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    elif isinstance(raw, str) and raw.strip():
        raw_text = raw
    else:
        return []
    return list(dict.fromkeys([raw_text] + _payload_with_headers(raw_text, headers)))


def _signature_candidates(
    secret: str, payload: str, timestamp: str | None
) -> list[tuple[str, str]]:
    base = [
        (payload, "payload"),
        (f"{payload}{secret}", "payload+secret"),
        (f"{secret}{payload}", "secret+payload"),
        (f"{secret}{payload}{secret}", "secret+payload+secret"),
    ]
    if timestamp:
        base.extend(
            [
                (f"{payload}{timestamp}{secret}", "payload+timestamp+secret"),
                (f"{timestamp}{payload}{secret}", "timestamp+payload+secret"),
                (f"{secret}{payload}{timestamp}", "secret+payload+timestamp"),
            ]
        )
    return base


def _hash_digest(algorithm: str, data: bytes, secret: bytes) -> str:
    if algorithm.startswith("hmac-"):
        digest_name = algorithm.split("-", 1)[1]
        return hmac.new(secret, data, getattr(hashlib, digest_name)).hexdigest()
    return getattr(hashlib, algorithm)(data).hexdigest()


def _digest_variants(algorithm: str, data: bytes, secret: bytes) -> list[tuple[str, str]]:
    """Return hex/base64 variants for hash/HMAC plus AES/RSA attempts."""
    lowered = algorithm.lower().replace("_", "-")
    if lowered in {
        "aes-128-cbc",
        "aes-192-cbc",
        "aes-256-cbc",
        "aes-128-gcm",
        "aes-256-gcm",
        "chacha20",
        "pbkdf2-sha256",
        "scrypt",
        "rsa-pkcs1v15",
        "rsa-oaep",
    }:
        return _encryption_digests(lowered, data, secret)
    try:
        hex_digest = _hash_digest(algorithm, data, secret)
        variants: list[tuple[str, str]] = [(hex_digest, "hex")]
        with suppress(ValueError):
            variants.append((base64.b64encode(bytes.fromhex(hex_digest)).decode(), "base64"))
            variants.append(
                (
                    base64.urlsafe_b64encode(bytes.fromhex(hex_digest)).decode().rstrip("="),
                    "base64url",
                )
            )
            variants.append((hex_digest[::-1], "hex-reversed"))
        return variants
    except Exception:
        return []


def _encryption_digests(algorithm: str, data: bytes, secret: bytes) -> list[tuple[str, str]]:
    try:
        from cryptography.hazmat.primitives import hashes, padding, serialization
        from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
        from cryptography.hazmat.primitives.ciphers import Cipher, aead, algorithms, modes
    except Exception:
        return []

    out: list[tuple[str, str]] = []
    try:
        if algorithm.startswith("aes-"):
            key_size = int(algorithm.split("-")[1])
            key = hashlib.sha256(secret).digest()[: key_size // 8]
            ivs = [hashlib.sha256(data).digest()[:16], b"\x00" * 16]
            for iv in ivs:
                padder = padding.PKCS7(128).padder()
                padded = padder.update(data) + padder.finalize()
                encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
                ciphertext = encryptor.update(padded) + encryptor.finalize()
                out.append((base64.b64encode(ciphertext).decode(), "base64"))
                out.append((ciphertext.hex(), "hex"))
    except Exception:
        pass
    try:
        if algorithm.endswith("-gcm"):
            key_size = int(algorithm.split("-")[1])
            key = hashlib.sha256(secret).digest()[: key_size // 8]
            nonce = hashlib.sha256(data).digest()[:12]
            ciphertext = aead.AESGCM(key).encrypt(nonce, data, None)
            out.append((base64.b64encode(ciphertext).decode(), "base64"))
            out.append((ciphertext.hex(), "hex"))
    except Exception:
        pass
    try:
        if algorithm == "chacha20":
            key = hashlib.sha256(secret).digest()[:32]
            nonce = hashlib.sha256(data).digest()[:16]
            ciphertext = (
                Cipher(algorithms.ChaCha20(key, nonce), mode=None).encryptor().update(data)
            )
            out.append((base64.b64encode(ciphertext).decode(), "base64"))
            out.append((ciphertext.hex(), "hex"))
    except Exception:
        pass
    try:
        if algorithm == "pbkdf2-sha256":
            derived = hashlib.pbkdf2_hmac("sha256", secret, data, 10_000)[:32]
            out.append((derived.hex(), "hex"))
            out.append((base64.b64encode(derived).decode(), "base64"))
    except Exception:
        pass
    try:
        if algorithm == "scrypt":
            derived = hashlib.scrypt(secret, salt=data, n=2**12, r=8, p=1)[:32]
            out.append((derived.hex(), "hex"))
            out.append((base64.b64encode(derived).decode(), "base64"))
    except Exception:
        pass
    try:
        if algorithm.startswith("rsa-"):
            public_key = serialization.load_pem_public_key(secret)
            if algorithm == "rsa-pkcs1v15":
                ciphertext = public_key.encrypt(data, asym_padding.PKCS1v15())
            else:
                ciphertext = public_key.encrypt(
                    data,
                    asym_padding.OAEP(
                        mgf=asym_padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None,
                    ),
                )
            out.append((base64.b64encode(ciphertext).decode(), "base64"))
            out.append((ciphertext.hex(), "hex"))
    except Exception:
        pass
    return list(dict.fromkeys(out))


_KNOWN_SECRET_PATTERNS = (
    "secret",
    "key",
    "token",
    "sign",
    "salt",
    "123456",
    "abcdef0123456789",
    "0123456789abcdef",
    "d41d8cd98f00b204e9800998ecf8427e",
)


def infer_secret_candidates(
    captures: list[dict[str, Any]],
    js_bundle: str | None = None,
) -> dict[str, Any]:
    """Infer candidate secrets from recipes, storage, responses, and JS."""
    secrets: list[str] = []
    sources: dict[str, str] = {}

    def add(value: Any, source: str) -> None:
        if not isinstance(value, str) or not value or len(value) > 128:
            return
        if value not in secrets:
            secrets.append(value)
            sources[value] = source

    for capture in captures:
        for recipe in (capture.get("analysis") or {}).get("signature_recipes", []) or []:
            if isinstance(recipe, dict):
                for item in recipe.get("secret_keys", []) or []:
                    add(item, "signature_recipe")
        for request in (capture.get("hook") or {}).get("requests", []) or []:
            if not isinstance(request, dict):
                continue
            storage = request.get("storage") or {}
            for bucket_name, bucket in storage.items() if isinstance(storage, dict) else []:
                if isinstance(bucket, dict):
                    for key, value in bucket.items():
                        if re.search(r"key|secret|salt|token|sign", str(key), re.I) or isinstance(value, str) and 6 <= len(value) <= 64:
                            add(value, f"storage:{bucket_name}:{key}")
            headers = request.get("headers") or {}
            for key, value in headers.items():
                if re.search(r"key|secret|salt|token|sign|auth", str(key), re.I):
                    add(value, f"header:{key}")
            params = _flatten_params(_request_params(request)[0])
            for key, value in params.items():
                if re.search(r"key|secret|salt|token|sign", str(key), re.I):
                    add(value, f"param:{key}")
        for entry in capture.get("network", []) or []:
            if not isinstance(entry, dict):
                continue
            for key, value in (entry.get("request_headers") or {}).items():
                if re.search(r"key|secret|salt|token|sign|auth", str(key), re.I):
                    add(value, f"request_header:{key}")
            response_body = entry.get("response_body") or entry.get("body")
            if isinstance(response_body, dict):
                for key, value in response_body.items():
                    if re.search(r"key|secret|salt|token|sign", str(key), re.I):
                        add(value, f"response:{key}")
            elif isinstance(response_body, str):
                for match in re.finditer(
                    r"[\"']([A-Za-z0-9_\-+=/]{8,64})[\"']",
                    response_body,
                ):
                    add(match.group(1), "response_text")
        for call in (capture.get("function_probes") or {}).get("function_calls", []) or []:
            if not isinstance(call, dict):
                continue
            values = list(call.get("args", []) or []) + [call.get("result")]
            for value in values:
                if isinstance(value, dict):
                    for key, item in value.items():
                        if re.search(r"key|secret|salt|token|sign", str(key), re.I):
                            add(item, f"function_probe:{call.get('name', '')}")
                elif isinstance(value, str) and 6 <= len(value) <= 128:
                    add(value, f"function_probe:{call.get('name', '')}")

    if js_bundle:
        try:
            from deep_reverse import extract_secret_hints

            for value in extract_secret_hints(js_bundle):
                add(value, "js_literal")
        except Exception:
            pass
    for pattern in _KNOWN_SECRET_PATTERNS:
        add(pattern, "known_pattern")
    return {
        "candidates": secrets[:200],
        "sources": sources,
        "summary": {
            "candidates": len(secrets[:200]),
            "from_recipe": sum(1 for value in secrets if sources.get(value) == "signature_recipe"),
            "from_storage": sum(1 for value in secrets if str(sources.get(value, "")).startswith("storage:")),
            "from_response": sum(1 for value in secrets if str(sources.get(value, "")).startswith("response")),
            "from_js": sum(1 for value in secrets if sources.get(value) == "js_literal"),
        },
    }


def _auto_candidate_secrets(captures: list[dict[str, Any]]) -> list[str]:
    """Collect secrets from reverse recipes and hook storage without user input."""
    return list(infer_secret_candidates(captures).get("candidates", []) or [])


def _verified_combos_for_request(
    request: dict[str, Any],
    secrets: list[str],
    algorithms: list[str],
    exclude_params: list[str] | None = None,
) -> list[tuple[str, str, str, str, str, str]]:
    params, headers = _request_params(request)
    flat_params = _flatten_params(params)
    signature_names = [name for name in flat_params if SIGNATURE_PARAM_RE.search(str(name))]
    if not signature_names:
        return []
    url = str(request.get("url", "") or "")
    signature_param = str(signature_names[0])
    expected = str(flat_params[signature_param])
    excluded = set(exclude_params or [])
    remaining = {
        key: value
        for key, value in flat_params.items()
        if key != signature_param and key not in excluded
    }
    timestamp = next(
        (str(value) for key, value in remaining.items() if TIMESTAMP_PARAM_RE.search(str(key))),
        None,
    )
    combos: list[tuple[str, str, str, str, str, str]] = []
    for payload in _payload_serializations(remaining):
        combined_payloads = list(
            dict.fromkeys(
                [payload]
                + _payload_with_headers(payload, headers)
                + _payload_with_url(payload, url)
                + _raw_body_payloads(request, headers)
            )
        )
        for combined in combined_payloads:
            for secret in secrets:
                for algorithm in algorithms:
                    for data, pattern in _signature_candidates(secret, combined, timestamp):
                        for raw_bytes in _payload_bytes(data):
                            for digest, _encoding in _digest_variants(
                                algorithm,
                                raw_bytes,
                                secret.encode("utf-8"),
                            ):
                                if digest.lower() == expected.lower():
                                    combos.append(
                                        (
                                            url,
                                            signature_param,
                                            secret,
                                            algorithm,
                                            pattern,
                                            combined,
                                        )
                                    )
    unique_combos: list[tuple[str, str, str, str, str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for combo in combos:
        key = (combo[2], combo[3], combo[4], combo[5])
        if key not in seen:
            seen.add(key)
            unique_combos.append(combo)
    return unique_combos


def verify_signature_candidates(
    captures: list[dict[str, Any]],
    secrets: list[str] | None = None,
    algorithms: list[str] | None = None,
    exclude_params: list[str] | None = None,
) -> list[SignatureVerification]:
    """Try common signature constructions against captured signature values."""
    if secrets is None:
        secrets = _auto_candidate_secrets(captures)
    algorithms = algorithms or [
        "md5",
        "sha1",
        "sha256",
        "sha512",
        "sha3_256",
        "sha3_512",
        "blake2b",
        "hmac-md5",
        "hmac-sha1",
        "hmac-sha256",
        "hmac-sha512",
    ]
    verifications: list[SignatureVerification] = []
    for capture in captures:
        for request in _iter_requests(capture):
            combos = _verified_combos_for_request(
                request,
                secrets,
                algorithms,
                exclude_params=exclude_params,
            )
            if not combos:
                params, _headers = _request_params(request)
                signature_names = [name for name in params if SIGNATURE_PARAM_RE.search(str(name))]
                if not signature_names:
                    continue
                url = str(request.get("url", "") or "")
                verifications.append(
                    SignatureVerification(
                        url=url,
                        signature_param=str(signature_names[0]),
                        pattern="none",
                        secret="",
                        algorithm="",
                        payload="",
                        verified=False,
                    )
                )
            else:
                for url, signature_param, secret, algorithm, pattern, payload in combos:
                    verifications.append(
                        SignatureVerification(
                            url=url,
                            signature_param=signature_param,
                            pattern=pattern,
                            secret=secret,
                            algorithm=algorithm,
                            payload=payload,
                            verified=True,
                        )
                    )
    unique: list[SignatureVerification] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for item in verifications:
        key = (
            item.url,
            item.signature_param,
            item.pattern,
            item.secret,
            item.algorithm,
            item.payload,
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _payload_param_names(payload: str) -> list[str]:
    if "&" in payload:
        return [part.split("=", 1)[0] for part in payload.split("&") if "=" in part]
    stripped = payload.strip()
    if stripped.startswith(("{", "[")):
        try:
            data = json.loads(stripped)
            if isinstance(data, dict):
                return list(data.keys())
        except json.JSONDecodeError:
            pass
    return [
        match.group(1)
        for match in re.finditer(
            r"([A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*|\[\d+\])*)\s*=",
            payload,
        )
    ]


def signature_coverage(
    captures: list[dict[str, Any]],
    verifications: list[SignatureVerification] | None = None,
) -> list[SignatureCoverage]:
    """List which request params are signed and which are excluded."""
    if verifications is None:
        verifications = verify_signature_candidates(captures)
    rows: list[SignatureCoverage] = []
    seen: set[tuple[str, str, str]] = set()
    for verification in verifications:
        if not verification.verified:
            continue
        key = (verification.url, verification.signature_param, verification.pattern)
        if key in seen:
            continue
        seen.add(key)
        signed = _payload_param_names(verification.payload)
        flat: dict[str, Any] = {}
        for capture in captures:
            for request in _iter_requests(capture):
                if str(request.get("url", "") or "") == verification.url:
                    params, _headers = _request_params(request)
                    flat = _flatten_params(params)
                    break
            if flat:
                break
        if not flat:
            continue
        unsigned = [name for name in flat if name not in signed]
        rows.append(
            SignatureCoverage(
                url=verification.url,
                signature_param=verification.signature_param,
                signed_params=signed,
                unsigned_params=unsigned,
                total_params=len(flat),
            )
        )
    return rows


def signature_consistency(
    captures: list[dict[str, Any]],
    secrets: list[str] | None = None,
    algorithms: list[str] | None = None,
    exclude_params: list[str] | None = None,
) -> list[SignatureConsistency]:
    """Count how many samples each verified signature construction matches."""
    if secrets is None:
        secrets = _auto_candidate_secrets(captures)
    algorithms = algorithms or [
        "md5",
        "sha1",
        "sha256",
        "sha512",
        "sha3_256",
        "hmac-md5",
        "hmac-sha1",
        "hmac-sha256",
        "hmac-sha512",
    ]
    counts: dict[tuple[str, str, str], int] = {}
    sample_urls: dict[tuple[str, str, str], list[str]] = {}
    total = 0
    for capture in captures:
        for request in _iter_requests(capture):
            params, _headers = _request_params(request)
            if not any(SIGNATURE_PARAM_RE.search(str(name)) for name in params):
                continue
            total += 1
            for url, _param, secret, algorithm, pattern, _payload in _verified_combos_for_request(
                request,
                secrets,
                algorithms,
                exclude_params=exclude_params,
            ):
                key = (pattern, secret, algorithm)
                counts[key] = counts.get(key, 0) + 1
                sample_urls.setdefault(key, []).append(url)
    rows: list[SignatureConsistency] = []
    for (pattern, secret, algorithm), verified in counts.items():
        urls = sample_urls.get((pattern, secret, algorithm), [])
        ratio = verified / max(1, total)
        confidence = min(0.99, 0.45 + 0.25 * ratio + 0.2 * min(1.0, len(urls) / max(1, total)))
        rows.append(
            SignatureConsistency(
                pattern=pattern,
                secret=secret,
                algorithm=algorithm,
                verified_samples=verified,
                total_samples=total,
                confidence=confidence,
                sample_urls=urls,
            )
        )
    rows.sort(key=lambda item: (item.verified_samples, item.confidence), reverse=True)
    return rows


def brute_force_secret(
    captures: list[dict[str, Any]],
    max_length: int = 3,
    charset: str = "abcdefghijklmnopqrstuvwxyz0123456789",
    algorithms: list[str] | None = None,
    max_combos: int = 50_000,
) -> list[str]:
    """Brute-force short signature secrets against captured requests."""
    from itertools import product

    algorithms = algorithms or ["md5"]
    found: list[str] = []
    count = 0
    for length in range(1, max_length + 1):
        for chars in product(charset, repeat=length):
            count += 1
            if count > max_combos:
                return found
            secret = "".join(chars)
            for capture in captures:
                for request in _iter_requests(capture):
                    if _verified_combos_for_request(request, [secret], algorithms):
                        if secret not in found:
                            found.append(secret)
                        break
                else:
                    continue
                break
    return found


def constrained_secret_search(
    captures: list[dict[str, Any]],
    hints: list[str] | None = None,
    *,
    max_length: int = 6,
    charset: str = "abcdefghijklmnopqrstuvwxyz0123456789",
    algorithms: list[str] | None = None,
    max_combos: int = 50_000,
    max_tested: int = 2_000,
) -> dict[str, Any]:
    """Search secrets using inferred hints and pattern constraints.

    This is the practical replacement for an SMT solver on captured traffic:
    it reduces the brute-force alphabet with hints from JS/storage/response
    values and tests prefix/suffix/known-pattern shapes before expanding to
    the full alphabet.  It returns only secrets verified against real
    captures.
    """
    if hints is None:
        hints = list(infer_secret_candidates(captures).get("candidates", []) or [])
    hints = hints[:20]
    algorithms = algorithms or ["md5", "sha1", "sha256"]
    tested: set[str] = set()
    found: list[str] = []

    def verify(secret: str) -> bool:
        if secret in tested:
            return False
        tested.add(secret)
        for capture in captures:
            for request in _iter_requests(capture):
                if _verified_combos_for_request(request, [secret], algorithms):
                    return True
        return False

    for hint in hints:
        hint = str(hint)
        variants = [
            hint,
            hint.lower(),
            hint.upper(),
            f"{hint}1",
            f"{hint}123",
            f"1{hint}",
            f"123{hint}",
            f"{hint}!",
            f"!{hint}",
        ]
        if len(hint) <= max_length:
            variants.extend([hint[i:] for i in range(1, min(4, len(hint)))])
        for secret in variants:
            if 1 <= len(secret) <= max_length and verify(secret) and secret not in found:
                found.append(secret)
            if len(tested) >= max_tested:
                break
        if found:
            break
        if len(tested) >= max_tested:
            break

    if not found and hints:
        reduced = "".join(dict.fromkeys("".join(str(h) for h in hints[:10])))
        if reduced:
            found.extend(
                brute_force_secret(
                    captures,
                    max_length=min(max_length, 4),
                    charset=reduced,
                    algorithms=algorithms,
                    max_combos=max_combos,
                )
            )
    return {
        "ok": True,
        "found": list(dict.fromkeys(found)),
        "tested": len(tested),
        "hints": len(hints),
        "strategy": "constraint-guided",
        "summary": {"found": len(list(dict.fromkeys(found))), "tested": len(tested)},
    }


def _pattern_expression(pattern: str) -> str:
    return {
        "payload": "payload",
        "payload+secret": "payload + secret",
        "secret+payload": "secret + payload",
        "secret+payload+secret": "secret + payload + secret",
        "payload+timestamp+secret": "payload + timestamp + secret",
        "timestamp+payload+secret": "timestamp + payload + secret",
        "secret+payload+timestamp": "secret + payload + timestamp",
    }.get(pattern, "payload + secret")


def generate_python_request_builder(
    request: dict[str, Any],
    verification: SignatureVerification,
) -> str:
    """Generate a full Python request builder from a verified signature."""
    url = str(request.get("url", "") or "")
    base_url = urllib.parse.urlunsplit(urllib.parse.urlsplit(url)._replace(query="", fragment=""))
    method = str(request.get("method", "GET") or "GET").upper()
    algorithm = verification.algorithm
    hmac_mode = algorithm.startswith("hmac-")
    digest = algorithm.split("-", 1)[1] if hmac_mode else algorithm
    digest = digest if digest in {"md5", "sha1", "sha256", "sha512"} else "md5"
    expression = _pattern_expression(verification.pattern)
    hashmethod = (
        f"hmac.new(key, data, hashlib.{digest}).hexdigest()"
        if hmac_mode
        else f"hashlib.{digest}(data).hexdigest()"
    )
    return f"""\
def build_request(params, headers=None, timestamp=None, secret={json.dumps(verification.secret, ensure_ascii=False)}):
    import hashlib, hmac, urllib.parse
    items = sorted((str(k), str(v)) for k, v in params.items())
    payload = "&".join(f"{{k}}={{v}}" for k, v in items)
    if headers:
        h_items = sorted((str(k), str(v)) for k, v in headers.items())
        payload = payload + "&" + "&".join(f"{{k}}={{v}}" for k, v in h_items)
    timestamp = timestamp or str(int(__import__("time").time()))
    data = ({expression}).encode("utf-8")
    key = str(secret).encode("utf-8")
    params["{verification.signature_param}"] = {hashmethod}
    return ({json.dumps(method)}, {json.dumps(base_url)}, params, headers or {{}})
"""


def generate_node_request_builder(
    request: dict[str, Any],
    verification: SignatureVerification,
) -> str:
    """Generate a Node.js request builder from a verified signature."""
    url = str(request.get("url", "") or "")
    base_url = urllib.parse.urlunsplit(urllib.parse.urlsplit(url)._replace(query="", fragment=""))
    method = str(request.get("method", "GET") or "GET").upper()
    algorithm = verification.algorithm
    hmac_mode = algorithm.startswith("hmac-")
    digest = algorithm.split("-", 1)[1] if hmac_mode else algorithm
    digest = digest if digest in {"md5", "sha1", "sha256", "sha512"} else "md5"
    expression = _pattern_expression(verification.pattern)
    hashcall = (
        f'crypto.createHmac("{digest}", key).update(data).digest("hex")'
        if hmac_mode
        else f'crypto.createHash("{digest}").update(data).digest("hex")'
    )
    return f"""\
const crypto = require("crypto");
function buildRequest(params, headers, timestamp, secret = {json.dumps(verification.secret, ensure_ascii=False)}) {{
  const items = Object.entries(params).sort(([a], [b]) => a.localeCompare(b));
  let payload = items.map(([k, v]) => k + "=" + v).join("&");
  if (headers) {{
    const hItems = Object.entries(headers).sort(([a], [b]) => a.localeCompare(b));
    payload = payload + "&" + hItems.map(([k, v]) => k + "=" + v).join("&");
  }}
  timestamp = timestamp || String(Math.floor(Date.now() / 1000));
  const data = ({expression});
  const key = String(secret);
  params["{verification.signature_param}"] = {hashcall};
  return [{json.dumps(method)}, {json.dumps(base_url)}, params, headers || {{}}];
}}
"""


def generate_python_replay(recipe: SignatureRecipe | dict[str, Any]) -> str:
    """Generate a dependency-free Python implementation from a recipe."""
    if isinstance(recipe, dict):
        recipe = SignatureRecipe(
            function_name=str(recipe.get("function_name", "build_signature")),
            algorithm=str(recipe.get("algorithm", "custom")),
            parameter_order=list(recipe.get("parameter_order", []) or []),
            secret_keys=list(recipe.get("secret_keys", []) or []),
            encoding=str(recipe.get("encoding", "plain")),
            snippet=str(recipe.get("snippet", "")),
            line=int(recipe.get("line", 0)),
            confidence=float(recipe.get("confidence", 0.5)),
        )
    secret = recipe.secret_keys[0] if recipe.secret_keys else '""'
    algorithm = recipe.algorithm.lower()
    digest = "md5"
    hmac_mode = False
    if "hmac" in algorithm:
        hmac_mode = True
        digest = "sha1" if "sha1" in algorithm else "sha256" if "sha256" in algorithm else "md5"
    elif "sha" in algorithm:
        digest = (
            "sha512" if "sha512" in algorithm else "sha256" if "sha256" in algorithm else "sha1"
        )
    return f"""\
def build_signature(params, secret={json.dumps(secret, ensure_ascii=False)}):
    import hashlib, hmac, urllib.parse
    items = sorted((str(k), str(v)) for k, v in params.items())
    payload = "&".join(f"{{k}}={{v}}" for k, v in items)
    data = payload.encode("utf-8")
    key = str(secret).encode("utf-8")
    {"return hmac.new(key, data, hashlib." + digest + ").hexdigest()" if hmac_mode else "return hashlib." + digest + "(data).hexdigest()"}
"""


def generate_node_replay(recipe: SignatureRecipe | dict[str, Any]) -> str:
    """Generate a Node.js replay stub from a recipe."""
    if isinstance(recipe, dict):
        recipe = SignatureRecipe(
            function_name=str(recipe.get("function_name", "build_signature")),
            algorithm=str(recipe.get("algorithm", "custom")),
            parameter_order=list(recipe.get("parameter_order", []) or []),
            secret_keys=list(recipe.get("secret_keys", []) or []),
            encoding=str(recipe.get("encoding", "plain")),
            snippet=str(recipe.get("snippet", "")),
            line=int(recipe.get("line", 0)),
            confidence=float(recipe.get("confidence", 0.5)),
        )
    secret = recipe.secret_keys[0] if recipe.secret_keys else ""
    algorithm = recipe.algorithm.lower()
    hmac_mode = "hmac" in algorithm
    if hmac_mode:
        digest = "sha1" if "sha1" in algorithm else "sha256" if "sha256" in algorithm else "md5"
    elif "sha" in algorithm:
        digest = (
            "sha512" if "sha512" in algorithm else "sha256" if "sha256" in algorithm else "sha1"
        )
    else:
        digest = "md5"
    body = (
        f'return crypto.createHmac("{digest}", key).update(payload).digest("hex");'
        if hmac_mode
        else f'return crypto.createHash("{digest}").update(payload + key).digest("hex");'
    )
    return f"""\
const crypto = require("crypto");
function buildSignature(params, secret = {json.dumps(secret, ensure_ascii=False)}) {{
  const items = Object.entries(params).sort(([a], [b]) => a.localeCompare(b));
  const payload = items.map(([k, v]) => k + "=" + v).join("&");
  const key = String(secret);
  {body}
}}
"""


def generate_device_fingerprint_python() -> str:
    """Generate a Python device-fingerprint hasher from a flattened snapshot."""
    return """\
def build_fingerprint(snapshot):
    import hashlib
    def flatten(value, prefix=""):
        out = {}
        if isinstance(value, dict):
            for key, child in value.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                out.update(flatten(child, path))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                path = f"{prefix}[{index}]"
                out.update(flatten(child, path))
        else:
            out[prefix] = str(value)
        return out
    items = sorted(flatten(snapshot).items())
    raw = "&".join(f"{k}={v}" for k, v in items)
    return hashlib.sha256(raw.encode()).hexdigest()
"""


def verify_device_params(captures: list[dict[str, Any]]) -> list[DeviceParamMatch]:
    """Check whether device params match hashes of the captured fingerprint."""
    matches: list[DeviceParamMatch] = []
    for capture in captures:
        for request in _iter_requests(capture):
            device = request.get("device")
            if not isinstance(device, dict):
                continue
            _tokens, fingerprint_hash = tokenize_device_snapshot(device)
            if not fingerprint_hash:
                continue
            params, _headers = _request_params(request)
            url = str(request.get("url", "") or "")
            for name, value in params.items():
                if not DEVICE_PARAM_RE.search(str(name)):
                    continue
                candidates = {
                    "sha256": fingerprint_hash,
                    "md5": hashlib.md5(fingerprint_hash.encode()).hexdigest(),
                    "sha1": hashlib.sha1(fingerprint_hash.encode()).hexdigest(),
                }
                for algorithm, candidate in candidates.items():
                    matches.append(
                        DeviceParamMatch(
                            url=url,
                            param=str(name),
                            value=str(value),
                            fingerprint_sha256=fingerprint_hash,
                            candidate=candidate,
                            algorithm=algorithm,
                            matched=str(value).lower() == candidate.lower(),
                        )
                    )
    return matches


def storage_diff(captures: list[dict[str, Any]]) -> list[StorageDiff]:
    """Diff hook storage snapshots to find rotating tokens / device IDs."""
    grouped: dict[tuple[str, str], list[str]] = {}
    for capture in captures:
        for request in (capture.get("hook") or {}).get("requests", []) or []:
            if not isinstance(request, dict):
                continue
            storage = request.get("storage") or {}
            if not isinstance(storage, dict):
                continue
            for bucket, values in storage.items():
                if not isinstance(values, dict):
                    continue
                for key, value in values.items():
                    grouped.setdefault((str(bucket), str(key)), []).append(str(value))
    diffs: list[StorageDiff] = []
    for (bucket, key), values in sorted(grouped.items()):
        unique = list(dict.fromkeys(values))
        diffs.append(
            StorageDiff(
                bucket=bucket,
                key=key,
                values=unique,
                changed=len(unique) > 1,
            )
        )
    return diffs


_SIGN_FN_RE = re.compile(
    r"sign|encrypt|decrypt|token|hash|md5|sha1|sha256|sha512|hmac|aes|rsa",
    re.IGNORECASE,
)
_DEVICE_FN_RE = re.compile(
    r"device|fingerprint|fp|did|ua|useragent|canvas|webgl|screen|platform|hardware",
    re.IGNORECASE,
)
_TIME_FN_RE = re.compile(r"time|ts|nonce|stamp|expire|deadline", re.IGNORECASE)


def _arg_shapes(params: dict[str, Any]) -> list[list[Any]]:
    flat = _flatten_params(params)
    return [
        [params],
        [flat],
        [json.dumps(flat, ensure_ascii=False, sort_keys=True)],
        list(flat.values()),
    ]


def _call_function(js: str, name: str, args: list[Any], timeout: float) -> dict[str, Any] | None:
    if run_signature_function is None:
        return None
    try:
        return run_signature_function(js, name, args, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def verify_js_against_captures(
    js: str,
    captures: list[dict[str, Any]],
    max_functions: int = 15,
    timeout: float = 10.0,
) -> list[JsReplayVerification]:
    """Run extracted JS functions and compare outputs with captured values."""
    if not node_available():
        return [JsReplayVerification("", "node", "", "", False, error="node is not available")]
    names = find_function_names(js)[:max_functions]
    rows: list[JsReplayVerification] = []
    seen: set[tuple[str, str, str, str]] = set()
    for capture in captures:
        for request in _iter_requests(capture):
            params, _headers = _request_params(request)
            flat = _flatten_params(params)
            signature_names = [name for name in flat if SIGNATURE_PARAM_RE.search(str(name))]
            if signature_names:
                expected = str(flat[signature_names[0]])
                for name in names:
                    if not _SIGN_FN_RE.search(name):
                        continue
                    for args in _arg_shapes(params):
                        result = _call_function(js, name, args, timeout)
                        if result and result.get("ok"):
                            value = str(result.get("value", "") or "")
                            if value.lower() == expected.lower():
                                key = (name, "signature", expected, value)
                                if key not in seen:
                                    seen.add(key)
                                    rows.append(
                                        JsReplayVerification(
                                            function_name=name,
                                            kind="signature",
                                            captured_value=expected,
                                            computed_value=value,
                                            matched=True,
                                            duration_ms=result.get("duration_ms"),
                                        )
                                    )
                                break
            device_names = [name for name in flat if DEVICE_PARAM_RE.search(str(name))]
            if device_names:
                snapshot = request.get("device")
                snapshot = snapshot if isinstance(snapshot, dict) else None
                expected = str(flat[device_names[0]])
                for name in names:
                    if not _DEVICE_FN_RE.search(name):
                        continue
                    for args in ([], [params], [snapshot] if snapshot else []):
                        result = _call_function(js, name, args, timeout)
                        if result and result.get("ok"):
                            value = str(result.get("value", "") or "")
                            if value.lower() == expected.lower():
                                key = (name, "device", expected, value)
                                if key not in seen:
                                    seen.add(key)
                                    rows.append(
                                        JsReplayVerification(
                                            function_name=name,
                                            kind="device",
                                            captured_value=expected,
                                            computed_value=value,
                                            matched=True,
                                            duration_ms=result.get("duration_ms"),
                                        )
                                    )
                                break
            time_names = [name for name in flat if TIMESTAMP_PARAM_RE.search(str(name))]
            if time_names:
                expected = str(flat[time_names[0]])
                for name in names:
                    if not _TIME_FN_RE.search(name):
                        continue
                    for args in ([], [params]):
                        result = _call_function(js, name, args, timeout)
                        if result and result.get("ok"):
                            value = str(result.get("value", "") or "")
                            matched = value.lower() == expected.lower()
                            if not matched:
                                with suppress(TypeError, ValueError):
                                    matched = abs(int(value) - int(expected)) <= 2
                            if matched:
                                key = (name, "timestamp", expected, value)
                                if key not in seen:
                                    seen.add(key)
                                    rows.append(
                                        JsReplayVerification(
                                            function_name=name,
                                            kind="timestamp",
                                            captured_value=expected,
                                            computed_value=value,
                                            matched=True,
                                            duration_ms=result.get("duration_ms"),
                                        )
                                    )
                                break
    return rows


def analyze_capture_set(
    captures: list[dict[str, Any]],
    secrets: list[str] | None = None,
    algorithms: list[str] | None = None,
    brute_force: bool = False,
    brute_max_length: int = 3,
    brute_charset: str = "abcdefghijklmnopqrstuvwxyz0123456789",
    js_bundle: str | None = None,
    max_functions: int = 15,
    exclude_params: list[str] | None = None,
    active_diff: bool | dict[str, Any] | None = None,
    active_diff_sender: Any = None,
    knowledge_store: str | Path | None = None,
) -> ReverseLabReport:
    """Run the full reverse lab over a set of captures."""
    diffs = diff_captured_requests(captures)
    timestamps = correlate_timestamps(captures)
    server_offsets = server_clock_offsets(captures)
    offset_by_url = {offset.url: offset for offset in server_offsets}
    for timestamp in timestamps:
        offset = offset_by_url.get(timestamp.url)
        if offset is not None:
            timestamp.server_delta_ms = offset.delta_ms
            timestamp.server_synced = abs(timestamp.delta_ms - offset.delta_ms) < 5000
    tokens: list[FingerprintToken] = []
    fingerprint_hash = ""
    for capture in captures:
        hook = capture.get("hook") or {}
        for request in hook.get("requests", []) or []:
            if isinstance(request, dict) and request.get("device"):
                item_tokens, item_hash = tokenize_device_snapshot(request["device"])
                tokens.extend(item_tokens)
                fingerprint_hash = item_hash or fingerprint_hash
    resolved_secrets = secrets if secrets is not None else _auto_candidate_secrets(captures)
    if js_bundle:
        resolved_secrets = list(
            dict.fromkeys([*resolved_secrets, *extract_secret_hints(js_bundle)])
        )
    secret_inference = infer_secret_candidates(captures, js_bundle)
    knowledge_summary: dict[str, Any] = {"entries": 0, "secrets": 0, "algorithms": 0}
    if knowledge_store:
        try:
            from signature_knowledge import knowledge_hints, load_knowledge, prune_knowledge

            if Path(knowledge_store).exists():
                prune_knowledge(knowledge_store)

            knowledge_entries = load_knowledge(knowledge_store)
            hints = knowledge_hints(knowledge_entries)
            resolved_secrets = list(
                dict.fromkeys([*hints["secrets"], *resolved_secrets])
            )
            algorithms = list(
                dict.fromkeys([*(algorithms or []), *hints["algorithms"]])
            ) or None
            knowledge_summary = {
                "entries": len(knowledge_entries),
                "secrets": len(hints["secrets"]),
                "algorithms": len(hints["algorithms"]),
            }
        except Exception as exc:
            knowledge_summary = {"error": str(exc)}
    constrained_secrets: list[str] = []
    if brute_force and secrets is None:
        constrained = constrained_secret_search(
            captures,
            hints=secret_inference.get("candidates", []) or [],
            algorithms=algorithms,
        )
        constrained_secrets = list(constrained.get("found", []) or [])
        secret_inference["constrained_search"] = constrained
    verifications = verify_signature_candidates(
        captures,
        resolved_secrets,
        algorithms,
        exclude_params=exclude_params,
    )
    coverages = signature_coverage(captures, verifications)
    consistency = signature_consistency(
        captures,
        resolved_secrets,
        algorithms,
        exclude_params=exclude_params,
    )
    device_matches = verify_device_params(captures)
    storage_diffs = storage_diff(captures)
    error_signals = response_error_signals(captures)
    recipes: list[Any] = []
    for capture in captures:
        recipes.extend((capture.get("analysis") or {}).get("signature_recipes", []) or [])
    generated_python = [generate_python_replay(recipe) for recipe in recipes[:5]]
    generated_node = [generate_node_replay(recipe) for recipe in recipes[:5]]
    all_requests = [request for capture in captures for request in _iter_requests(capture)]
    sample_request = all_requests[0] if all_requests else {}
    generated_request_builders = [
        generate_python_request_builder(
            sample_request,
            verification,
        )
        for verification in verifications[:3]
        if verification.verified and sample_request
    ]
    generated_node_request_builders = [
        generate_node_request_builder(
            sample_request,
            verification,
        )
        for verification in verifications[:3]
        if verification.verified and sample_request
    ]
    generated_device_python = [generate_device_fingerprint_python()] if tokens else []
    js_replay = (
        verify_js_against_captures(js_bundle, captures, max_functions=max_functions)
        if js_bundle
        else []
    )
    brute_force_secrets: list[str] = []
    if brute_force:
        brute_force_secrets = brute_force_secret(
            captures,
            max_length=brute_max_length,
            charset=brute_charset,
            algorithms=algorithms,
        )
    active_diff_report: dict[str, Any] = {}
    active_diff_config = active_diff if isinstance(active_diff, dict) else {}
    if (active_diff is True or active_diff_config.get("enabled", False)) and active_diff_sender is not None:
        try:
            from active_diff import (
                run_active_diff_oracle,
                run_active_diff_tree,
                run_active_differential,
            )

            if active_diff_config.get("oracle"):
                active_diff_report = run_active_diff_oracle(
                    captures,
                    active_diff_sender,
                    max_rounds=int(active_diff_config.get("max_rounds", 5)),
                    max_requests=int(active_diff_config.get("max_requests", 20)),
                    min_interval=float(active_diff_config.get("min_interval", 0.0)),
                ).to_dict()
            elif active_diff_config.get("decision_tree"):
                active_diff_report = run_active_diff_tree(
                    captures,
                    active_diff_sender,
                    max_rounds=int(active_diff_config.get("max_rounds", 3)),
                    max_requests=int(active_diff_config.get("max_requests", 12)),
                    min_interval=float(active_diff_config.get("min_interval", 0.0)),
                ).to_dict()
            else:
                active_diff_report = run_active_differential(
                    captures,
                    active_diff_sender,
                    max_requests=int(active_diff_config.get("max_requests", 8)),
                    min_interval=float(active_diff_config.get("min_interval", 0.0)),
                    exclude_params=exclude_params,
                ).to_dict()
        except Exception as exc:
            active_diff_report = {"summary": {"error": str(exc), "requests": 0, "changed": 0}}
    if knowledge_store and verifications:
        try:
            from signature_knowledge import merge_verified_into_knowledge

            merged = merge_verified_into_knowledge(
                captures,
                verifications,
                knowledge_store,
            )
            knowledge_summary["persisted"] = len(merged)
        except Exception as exc:
            knowledge_summary["persist_error"] = str(exc)
    return ReverseLabReport(
        request_diffs=diffs,
        timestamp_correlations=timestamps,
        server_clock_offsets=server_offsets,
        fingerprint_tokens=tokens,
        fingerprint_sha256=fingerprint_hash,
        signature_verifications=verifications,
        signature_consistency=consistency,
        device_param_matches=device_matches,
        brute_force_secrets=brute_force_secrets,
        storage_diffs=storage_diffs,
        generated_python=generated_python,
        generated_node=generated_node,
        generated_request_builders=generated_request_builders,
        generated_node_request_builders=generated_node_request_builders,
        generated_device_python=generated_device_python,
        js_replay_verifications=js_replay,
        signature_coverages=coverages,
        response_error_signals=error_signals,
        active_diff=active_diff_report,
        secret_inference=secret_inference,
        knowledge=knowledge_summary,
        summary={
            "captures": len(captures),
            "request_diffs": len(diffs),
            "timestamp_correlations": len(timestamps),
            "server_clock_offsets": len(server_offsets),
            "fingerprint_tokens": len(tokens),
            "signature_verifications": len(verifications),
            "verified_signatures": sum(1 for item in verifications if item.verified),
            "signature_consistency": len(consistency),
            "consistent_signatures": sum(
                1 for item in consistency if item.verified_samples == item.total_samples
            ),
            "device_param_matches": len(device_matches),
            "matched_device_params": sum(1 for item in device_matches if item.matched),
            "brute_force_secrets": len(brute_force_secrets),
            "storage_diffs": len(storage_diffs),
            "changed_storage_keys": sum(1 for item in storage_diffs if item.changed),
            "generated_python": len(generated_python),
            "generated_node": len(generated_node),
            "generated_request_builders": len(generated_request_builders),
            "generated_node_request_builders": len(generated_node_request_builders),
            "generated_device_python": len(generated_device_python),
            "js_replay_verifications": len(js_replay),
            "js_replay_matched": sum(1 for item in js_replay if item.matched),
            "signature_coverages": len(coverages),
            "response_error_signals": len(error_signals),
            "active_diff": active_diff_report.get("summary", {}).get("requests", 0),
            "active_diff_changed": active_diff_report.get("summary", {}).get("changed", 0),
            "secret_candidates": secret_inference.get("summary", {}).get("candidates", 0),
            "constrained_secret_found": len(constrained_secrets),
            "knowledge_entries": knowledge_summary.get("entries", 0),
        },
    )


def _fresh_param_value(name: str) -> str:
    lower = str(name).lower()
    if "nonce" in lower or "rand" in lower or lower in {"_", "r"}:
        return str(random.SystemRandom().randrange(10**15, 10**16))
    if "ms" in lower or "millis" in lower:
        return str(int(time.time() * 1000))
    return str(int(time.time()))


def _recipe_algorithm(recipe: dict[str, Any]) -> str:
    value = str(recipe.get("algorithm") or "").lower().replace("-", "").replace("_", "")
    if "aes" in value and "cbc" in value:
        return "aes-256-cbc" if "256" in value else "aes-128-cbc"
    if "rsa" in value and "oaep" in value:
        return "rsa-oaep"
    if "rsa" in value:
        return "rsa-pkcs1v15"
    if "sha512" in value and "hmac" in value:
        return "hmac-sha512"
    if "hmacsha256" in value:
        return "hmac-sha256"
    if "hmacsha1" in value:
        return "hmac-sha1"
    if "hmac" in value:
        return "hmac-md5"
    if "sha512" in value:
        return "sha512"
    if "sha256" in value:
        return "sha256"
    if "sha1" in value:
        return "sha1"
    return "md5"


def _retry_request_payload(
    *,
    method: str,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    body: Any,
    sig_param: str,
    signature_source: str,
    confidence: float,
) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(url)
    if method in {"GET", "HEAD", "DELETE", "OPTIONS"}:
        target = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(params)))
        json_body: Any = None
        data: Any = None
    else:
        target = url
        json_body = None
        data = urllib.parse.urlencode(params)
        if isinstance(body, dict):
            json_body = {**body, **params}
            data = None
        elif isinstance(body, str):
            stripped = body.lstrip()
            if stripped.startswith("{"):
                try:
                    json_body = {**json.loads(body), **params}
                    data = None
                except json.JSONDecodeError:
                    pass
    return {
        "method": method,
        "url": target,
        "headers": dict(headers or {}),
        "params": dict(params),
        "json_body": json_body,
        "data": data,
        "signature_param": sig_param,
        "signature_source": signature_source,
        "confidence": confidence,
    }


def _retry_request_variants(
    *,
    method: str,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    body: Any,
    sig_param: str,
    secret: str,
    algorithm: str,
    pattern: str | None = None,
    signature_source: str = "verified",
    confidence: float = 0.9,
) -> list[dict[str, Any]]:
    remaining = {key: value for key, value in _flatten_params(params).items() if key != sig_param}
    for key in list(remaining):
        if TIMESTAMP_PARAM_RE.search(str(key)):
            remaining[key] = _fresh_param_value(str(key))
        elif str(key).lower() in {"nonce", "rand", "random", "r"}:
            remaining[key] = str(random.SystemRandom().randrange(10**15, 10**16))
    timestamp = next(
        (str(value) for key, value in remaining.items() if TIMESTAMP_PARAM_RE.search(str(key))),
        None,
    )
    variants: list[dict[str, Any]] = []
    for payload in _payload_serializations(remaining):
        combined_payloads = list(
            dict.fromkeys(
                [payload]
                + _payload_with_headers(payload, headers)
                + _payload_with_url(payload, url)
            )
        )
        for combined in combined_payloads:
            for data, candidate_pattern in _signature_candidates(secret, combined, timestamp):
                if pattern and candidate_pattern != pattern:
                    continue
                for raw_bytes in _payload_bytes(data):
                    for digest, _encoding in _digest_variants(
                        algorithm,
                        raw_bytes,
                        secret.encode("utf-8"),
                    ):
                        fresh_params = {**remaining, sig_param: digest}
                        variants.append(
                            _retry_request_payload(
                                method=method,
                                url=url,
                                params=fresh_params,
                                headers=headers,
                                body=body,
                                sig_param=sig_param,
                                signature_source=signature_source,
                                confidence=confidence,
                            )
                        )
    return variants


def _add_retry_candidate(
    candidates: list[dict[str, Any]],
    seen: set[tuple[str, str, str, str]],
    variant: dict[str, Any],
    source_url: str,
    max_requests: int,
) -> bool:
    key = (
        str(variant["method"]),
        str(variant["url"]),
        json.dumps(
            variant["params"],
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ),
        str(variant["signature_param"]),
    )
    if key in seen:
        return False
    seen.add(key)
    variant["source_url"] = source_url
    candidates.append(variant)
    return len(candidates) >= max_requests


def build_reverse_retry_requests(
    captures: list[dict[str, Any]],
    max_requests: int = 8,
    *,
    brute_force: bool = False,
    brute_max_length: int = 2,
) -> list[dict[str, Any]]:
    """Build fresh signed API requests for blocked captures that need a retry."""
    verified_by_key: dict[tuple[str, str], list[SignatureVerification]] = {}
    for verification in verify_signature_candidates(captures):
        if verification.verified:
            verified_by_key.setdefault((verification.url, verification.signature_param), []).append(
                verification
            )

    brute_secrets: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for capture in captures:
        source_url = str(capture.get("url") or "")
        requests = list(_iter_requests(capture))
        for site in (capture.get("analysis") or {}).get("request_sites", []) or []:
            requests.append(
                {
                    "method": site.get("method") or "GET",
                    "url": site.get("url") or "",
                    "headers": site.get("headers") or {},
                    "params": site.get("params") or {},
                    "body": site.get("body"),
                }
            )
        for request in requests:
            method = str(request.get("method") or "GET").upper()
            raw_url = str(request.get("url") or "")
            url = urllib.parse.urljoin(source_url, raw_url) if raw_url else source_url
            params, headers = _request_params(request)
            site_params = request.get("params")
            if isinstance(site_params, dict):
                params = {**params, **site_params}
            flat = _flatten_params(params)
            signature_names = [name for name in flat if SIGNATURE_PARAM_RE.search(str(name))]
            if not signature_names:
                continue
            sig_param = str(signature_names[0])
            body = (
                request.get("body") if request.get("body") is not None else request.get("post_data")
            )
            verified = (
                verified_by_key.get((raw_url, sig_param))
                or verified_by_key.get((url, sig_param))
                or []
            )
            for verification in verified:
                variants = _retry_request_variants(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    body=body,
                    sig_param=sig_param,
                    secret=verification.secret,
                    algorithm=verification.algorithm,
                    pattern=verification.pattern,
                    signature_source="verified",
                    confidence=0.95,
                )
                for variant in variants:
                    if _add_retry_candidate(candidates, seen, variant, source_url, max_requests):
                        return candidates
            if verified:
                continue
            recipe_used = False
            for recipe in (capture.get("analysis") or {}).get("signature_recipes", []) or []:
                secret_keys = recipe.get("secret_keys") or []
                if not secret_keys:
                    continue
                recipe_used = True
                confidence = min(
                    0.9,
                    0.5 + float(recipe.get("confidence") or 0.5) * 0.4,
                )
                variants = _retry_request_variants(
                    method=method,
                    url=url,
                    params=params,
                    headers=headers,
                    body=body,
                    sig_param=sig_param,
                    secret=str(secret_keys[0]),
                    algorithm=_recipe_algorithm(recipe),
                    signature_source="recipe",
                    confidence=confidence,
                )
                for variant in variants[:3]:
                    if _add_retry_candidate(candidates, seen, variant, source_url, max_requests):
                        return candidates
                if candidates:
                    break
            if recipe_used or not brute_force:
                continue
            if not brute_secrets:
                brute_secrets.extend(
                    brute_force_secret(
                        captures,
                        max_length=brute_max_length,
                        max_combos=20_000,
                    )
                )
            for secret in brute_secrets:
                for algorithm in ("md5", "sha1", "sha256"):
                    variants = _retry_request_variants(
                        method=method,
                        url=url,
                        params=params,
                        headers=headers,
                        body=body,
                        sig_param=sig_param,
                        secret=secret,
                        algorithm=algorithm,
                        signature_source="brute_force",
                        confidence=0.7,
                    )
                    for variant in variants[:1]:
                        if _add_retry_candidate(
                            candidates, seen, variant, source_url, max_requests
                        ):
                            return candidates
    return candidates


def _self_test() -> None:
    secret = "s3cret"
    ts = 1786000000
    captured_at = ts * 1000 + 500
    payload = "a=1&b=2&ts=1786000000"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = {
        "url": "https://example.com/",
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": f"https://example.com/api?sign={expected}&ts={ts}&a=1&b=2",
                    "captured_at_ms": captured_at,
                    "device": {
                        "navigator": {"userAgent": "Mozilla/5.0", "platform": "Win32"},
                        "screen": {"width": 1920, "height": 1080},
                    },
                }
            ]
        },
        "network": [],
    }
    report = analyze_capture_set([capture], secrets=[secret], algorithms=["md5"])
    assert report.summary["request_diffs"] == 1
    assert report.summary["timestamp_correlations"] == 1
    assert report.summary["fingerprint_tokens"] >= 3
    assert report.summary["verified_signatures"] >= 1
    assert report.summary["device_param_matches"] >= 0
    assert report.summary["generated_node"] >= 0
    print("reverse_lab self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-request reverse engineering lab")
    parser.add_argument("--input", action="append", default=[], help="capture JSON file")
    parser.add_argument("--js", default=None, help="JS bundle to execute against captures")
    parser.add_argument(
        "--max-functions",
        type=int,
        default=15,
        help="maximum extracted functions to try in JS replay",
    )
    parser.add_argument("--output", default=None, help="write lab report JSON")
    parser.add_argument("--secrets", default="", help="comma-separated candidate secrets")
    parser.add_argument(
        "--algorithms",
        default="md5,sha1,sha256,hmac-md5,hmac-sha1,hmac-sha256",
        help="signature algorithms to try",
    )
    parser.add_argument(
        "--brute-secret",
        action="store_true",
        help="brute-force short signature secrets from captured requests",
    )
    parser.add_argument(
        "--brute-max",
        type=int,
        default=3,
        help="maximum secret length for --brute-secret",
    )
    parser.add_argument(
        "--brute-charset",
        default="abcdefghijklmnopqrstuvwxyz0123456789",
        help="character set for --brute-secret",
    )
    parser.add_argument(
        "--exclude-params",
        default="",
        help="comma-separated params excluded from signature payloads",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.input:
        parser.error("--input is required unless --self-test is used")
    captures = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.input]
    js_bundle = Path(args.js).read_text(encoding="utf-8") if args.js else None
    secrets = (
        [item.strip() for item in args.secrets.split(",") if item.strip()] if args.secrets else None
    )
    algorithms = [item.strip() for item in args.algorithms.split(",") if item.strip()]
    exclude_params = [item.strip() for item in args.exclude_params.split(",") if item.strip()]
    report = analyze_capture_set(
        captures,
        secrets=secrets,
        algorithms=algorithms,
        brute_force=args.brute_secret,
        brute_max_length=args.brute_max,
        brute_charset=args.brute_charset,
        js_bundle=js_bundle,
        max_functions=args.max_functions,
        exclude_params=exclude_params or None,
    )
    text = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
