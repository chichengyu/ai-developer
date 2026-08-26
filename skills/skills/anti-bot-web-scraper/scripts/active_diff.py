"""Oracle-guided active differential verification.

Passive reverse engineering only sees the requests a page already made.
Active differential verification mutates one request field at a time and
replays it against the server.  When the response changes (status, error
message, or body), the mutated field is likely part of the signature; when
the server still accepts the request, the field is likely unsigned.
"""

from __future__ import annotations

import copy
import json
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

Sender = Callable[
    [str, str, dict[str, str] | None, Any, Any],
    tuple[int, str, dict[str, str]],
]


@dataclass
class ActiveDiffResult:
    url: str
    field: str
    kind: str
    baseline_status: int
    mutated_status: int
    changed: bool
    error_hint: str
    confidence: float
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "field": self.field,
            "kind": self.kind,
            "baseline_status": self.baseline_status,
            "mutated_status": self.mutated_status,
            "changed": self.changed,
            "error_hint": self.error_hint,
            "confidence": round(self.confidence, 2),
            "note": self.note,
        }


@dataclass
class ActiveDiffReport:
    results: list[ActiveDiffResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "results": [item.to_dict() for item in self.results],
            "summary": self.summary,
        }


def run_active_differential(
    captures: list[dict[str, Any]],
    sender: Sender,
    *,
    max_requests: int = 8,
    min_interval: float = 0.0,
    exclude_params: list[str] | None = None,
) -> ActiveDiffReport:
    """Mutate one field at a time and classify signature membership."""
    try:
        from reverse_lab import (
            SIGNATURE_PARAM_RE,
            TIMESTAMP_PARAM_RE,
            _flatten_params,
            _fresh_param_value,
            _iter_requests,
            _request_params,
        )
    except Exception:
        return ActiveDiffReport(
            summary={"error": "reverse_lab unavailable", "requests": 0, "changed": 0}
        )

    excluded = set(exclude_params or [])
    requests: list[dict[str, Any]] = []
    for capture in captures:
        for request in _iter_requests(capture):
            params, headers = _request_params(request)
            flat = _flatten_params(params)
            if any(SIGNATURE_PARAM_RE.search(str(name)) for name in flat):
                requests.append(request)
                break
        if requests:
            break
    if not requests:
        return ActiveDiffReport(
            summary={"requests": 0, "changed": 0, "note": "no signature request found"}
        )

    request = requests[0]
    method = str(request.get("method", "GET") or "GET").upper()
    raw_url = str(request.get("url", "") or "")
    params, headers = _request_params(request)
    body = request.get("body") if request.get("body") is not None else request.get("post_data")
    if isinstance(body, str):
        with suppress(json.JSONDecodeError):
            body = json.loads(body)
    base_url = raw_url
    baseline_status, baseline_text, _headers = _send_safe(
        sender,
        method,
        base_url,
        headers,
        body,
    )
    flat = _flatten_params(params)
    candidates: list[tuple[str, str, Any]] = []
    for name, value in flat.items():
        if name in excluded or SIGNATURE_PARAM_RE.search(str(name)):
            continue
        candidates.append((name, "param", value))
    if isinstance(body, dict):
        for name, value in body.items():
            if name not in excluded and not SIGNATURE_PARAM_RE.search(str(name)):
                candidates.append((name, "body", value))
    for name in headers:
        if name.lower() not in excluded and not SIGNATURE_PARAM_RE.search(name):
            candidates.append((name, "header", headers[name]))
    if len(candidates) > max_requests:
        candidates = candidates[:max_requests]

    results: list[ActiveDiffResult] = []
    for name, kind, _original in candidates:
        mparams = copy.deepcopy(flat)
        mheaders = dict(headers)
        mbody = copy.deepcopy(body)
        if kind == "param":
            if TIMESTAMP_PARAM_RE.search(str(name)) or str(name).lower() in {
                "nonce",
                "rand",
                "random",
                "r",
            }:
                mparams[name] = _fresh_param_value(str(name))
            else:
                mparams[name] = "__active_diff__"
            murl = _replace_query(raw_url, mparams)
        elif kind == "header":
            mheaders[name] = "__active_diff__"
            murl = raw_url
        else:
            mbody[name] = "__active_diff__"
            murl = raw_url
        if min_interval > 0:
            time.sleep(min_interval)
        mutated_status, mutated_text, _mheaders = _send_safe(
            sender,
            method,
            murl,
            mheaders,
            mbody,
        )
        changed = mutated_status != baseline_status or _body_changed(
            baseline_text,
            mutated_text,
        )
        hint = _error_hint(mutated_text)
        confidence = 0.88 if changed else 0.62
        note = (
            "field appears signed"
            if changed
            else "field appears unsigned"
        )
        results.append(
            ActiveDiffResult(
                url=raw_url,
                field=name,
                kind=kind,
                baseline_status=baseline_status,
                mutated_status=mutated_status,
                changed=changed,
                error_hint=hint,
                confidence=confidence,
                note=note,
            )
        )

    changed = sum(1 for item in results if item.changed)
    return ActiveDiffReport(
        results=results,
        summary={
            "requests": len(results),
            "changed": changed,
            "unsigned": len(results) - changed,
            "baseline_status": baseline_status,
            "fields": [item.field for item in results],
        },
    )


def run_active_diff_tree(
    captures: list[dict[str, Any]],
    sender: Sender,
    *,
    max_rounds: int = 3,
    max_requests: int = 12,
    min_interval: float = 0.0,
) -> ActiveDiffReport:
    """Run a bounded decision tree over signed-field combinations."""
    first = run_active_differential(
        captures,
        sender,
        max_requests=max_requests,
        min_interval=min_interval,
    )
    signed = [item.field for item in first.results if item.changed]
    if not signed:
        first.summary["decision_tree"] = {
            "rounds": 1,
            "note": "no signed fields detected",
        }
        return first

    try:
        from reverse_lab import (
            TIMESTAMP_PARAM_RE,
            _flatten_params,
            _fresh_param_value,
            _iter_requests,
            _request_params,
        )
    except Exception:
        first.summary["decision_tree"] = {"rounds": 1, "error": "reverse_lab unavailable"}
        return first

    request = next(
        (
            item
            for capture in captures
            for item in _iter_requests(capture)
        ),
        {},
    )
    if not request:
        return first
    method = str(request.get("method", "GET") or "GET").upper()
    raw_url = str(request.get("url", "") or "")
    params, headers = _request_params(request)
    flat = _flatten_params(params)
    body = request.get("body") if request.get("body") is not None else request.get("post_data")
    if isinstance(body, str):
        with suppress(json.JSONDecodeError):
            body = json.loads(body)
    baseline_status, baseline_text, _headers = _send_safe(
        sender,
        method,
        raw_url,
        headers,
        body,
    )
    extra: list[ActiveDiffResult] = []
    round_index = 2
    combined = dict(flat)
    for field_name in signed:
        if field_name in combined:
            combined[field_name] = (
                _fresh_param_value(field_name)
                if TIMESTAMP_PARAM_RE.search(field_name)
                else "__active_diff_tree__"
            )
    variants: list[tuple[str, str, dict[str, Any]]] = [
        ("combined-signed", "params", combined),
        ("reversed-order", "params", dict(reversed(list(combined.items())))),
        ("header-order", "headers", dict(reversed(list(headers.items())))),
    ]
    timestamp_fields = [
        name for name in flat if TIMESTAMP_PARAM_RE.search(str(name))
    ]
    for name in timestamp_fields[:2]:
        for offset in (-1, 1, 60):
            try:
                value = int(flat[name])
                variants.append(
                    (
                        f"{name}-offset-{offset}",
                        "params",
                        {**combined, name: str(max(0, value + offset))},
                    )
                )
            except (TypeError, ValueError):
                continue
    for used, (label, kind, mutated_params) in enumerate(variants):
        if used >= max_requests:
            break
        murl = _replace_query(raw_url, mutated_params) if kind == "params" else raw_url
        mheaders = dict(reversed(list(headers.items()))) if kind == "headers" else headers
        if min_interval > 0:
            time.sleep(min_interval)
        status, text, _mheaders = _send_safe(sender, method, murl, mheaders, body)
        changed = status != baseline_status or _body_changed(baseline_text, text)
        extra.append(
            ActiveDiffResult(
                url=raw_url,
                field=label,
                kind=f"tree:{kind}",
                baseline_status=baseline_status,
                mutated_status=status,
                changed=changed,
                error_hint=_error_hint(text),
                confidence=0.9 if changed else 0.7,
                note=f"decision-tree round {round_index}",
            )
        )
        round_index = 3 if used + 1 > len(variants) // 2 else 2
    first.results.extend(extra)
    first.summary["requests"] = len(first.results)
    first.summary["changed"] = sum(1 for item in first.results if item.changed)
    first.summary["unsigned"] = sum(1 for item in first.results if not item.changed)
    first.summary["decision_tree"] = {
        "rounds": min(max_rounds, round_index),
        "signed_fields": signed,
        "tree_requests": len(extra),
    }
    return first


def run_active_diff_oracle(
    captures: list[dict[str, Any]],
    sender: Sender,
    *,
    max_rounds: int = 5,
    max_requests: int = 20,
    min_interval: float = 0.0,
) -> ActiveDiffReport:
    """Iteratively mutate toward an accepted request using server errors."""
    try:
        from reverse_lab import (
            TIMESTAMP_PARAM_RE,
            _flatten_params,
            _fresh_param_value,
            _iter_requests,
            _request_params,
        )
    except Exception:
        return ActiveDiffReport(
            summary={"oracle": {"error": "reverse_lab unavailable"}, "requests": 0, "changed": 0}
        )
    request = next(
        (
            item
            for capture in captures
            for item in _iter_requests(capture)
        ),
        {},
    )
    if not request:
        return ActiveDiffReport(summary={"oracle": {"note": "no request"}, "requests": 0})
    method = str(request.get("method", "GET") or "GET").upper()
    raw_url = str(request.get("url", "") or "")
    params, headers = _request_params(request)
    flat = _flatten_params(params)
    body = request.get("body") if request.get("body") is not None else request.get("post_data")
    if isinstance(body, str):
        with suppress(json.JSONDecodeError):
            body = json.loads(body)
    baseline_status, baseline_text, _headers = _send_safe(
        sender,
        method,
        raw_url,
        headers,
        body,
    )
    results: list[ActiveDiffResult] = []
    attempts = 0
    accepted_status = 0
    converged = False
    current_params = dict(flat)
    current_headers = dict(headers)
    for _round in range(max_rounds):
        if attempts >= max_requests:
            break
        last_hint = _error_hint(results[-1].error_hint) if results else _error_hint(baseline_text)
        variants: list[tuple[str, str, dict[str, Any], dict[str, str]]] = []
        if "timestamp" in last_hint or "expired" in last_hint:
            for name in [key for key in flat if TIMESTAMP_PARAM_RE.search(str(key))][:2]:
                for offset in (-1, 1, 60):
                    try:
                        value = int(flat[name])
                        variants.append(
                            (
                                f"{name}-offset-{offset}",
                                "params",
                                {**current_params, name: str(max(0, value + offset))},
                                current_headers,
                            )
                        )
                    except (TypeError, ValueError):
                        continue
        elif "signature" in last_hint or "token" in last_hint or not last_hint:
            variants.append(("combined-signed", "params", current_params, current_headers))
            variants.append(("reversed-order", "params", dict(reversed(list(current_params.items()))), current_headers))
            variants.append(
                (
                    "oracle-header",
                    "headers",
                    current_params,
                    {**current_headers, "X-Oracle-Ok": "1"},
                )
            )
        else:
            for name in list(flat)[:5]:
                variants.append(
                    (
                        f"param-{name}",
                        "params",
                        {**current_params, name: _fresh_param_value(name)},
                        current_headers,
                    )
                )
        for label, kind, mutated_params, mutated_headers in variants:
            if attempts >= max_requests:
                break
            murl = _replace_query(raw_url, mutated_params) if kind == "params" else raw_url
            if min_interval > 0:
                time.sleep(min_interval)
            status, text, _mheaders = _send_safe(
                sender,
                method,
                murl,
                mutated_headers,
                body,
            )
            attempts += 1
            changed = status != baseline_status or _body_changed(baseline_text, text)
            results.append(
                ActiveDiffResult(
                    url=raw_url,
                    field=label,
                    kind=f"oracle:{kind}",
                    baseline_status=baseline_status,
                    mutated_status=status,
                    changed=changed,
                    error_hint=_error_hint(text),
                    confidence=0.95 if status < 400 else 0.7,
                    note=f"oracle round {_round + 1}",
                )
            )
            if status < 400:
                accepted_status = int(status)
                converged = True
                current_params = mutated_params
                break
        if converged:
            break
    return ActiveDiffReport(
        results=results,
        summary={
            "requests": len(results),
            "changed": sum(1 for item in results if item.changed),
            "baseline_status": baseline_status,
            "accepted_status": accepted_status,
            "oracle": {
                "converged": converged,
                "rounds": min(max_rounds, _round + 1),
                "attempts": attempts,
            },
        },
    )


def _send_safe(
    sender: Sender,
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any,
) -> tuple[int, str, dict[str, str]]:
    try:
        status, text, response_headers = sender(method, url, headers, None, body)
        return int(status or 0), str(text or ""), dict(response_headers or {})
    except Exception as exc:
        return 0, str(exc), {}


def _replace_query(url: str, params: dict[str, Any]) -> str:
    import urllib.parse

    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        parsed._replace(query=urllib.parse.urlencode(params, doseq=True))
    )


def _body_changed(baseline: str, mutated: str) -> bool:
    if baseline == mutated:
        return False
    if not baseline and mutated:
        return True
    if len(baseline) < 400 or len(mutated) < 400:
        return True
    return baseline[:200] != mutated[:200] or baseline[-200:] != mutated[-200:]


def _error_hint(text: str) -> str:
    lowered = text.lower()
    for hint in ("signature", "sign", "timestamp", "expired", "token", "device", "fingerprint"):
        if hint in lowered:
            return hint
    return ""


def _self_test() -> None:
    def sender(
        method: str,
        url: str,
        headers: dict[str, str] | None,
        data: Any,
        body: Any,
    ) -> tuple[int, str, dict[str, str]]:
        if "ts=" in url and "ts=1786000000" not in url:
            return 403, '{"error":"signature expired"}', {}
        if "a=__active_diff__" in url:
            return 200, '{"ok":true}', {}
        return 200, '{"ok":true}', {}

    capture = {
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": "https://example.com/api?sign=x&a=1&ts=1786000000",
                }
            ]
        },
        "network": [],
    }
    report = run_active_differential([capture], sender)
    assert report.summary["requests"] >= 2
    assert any(item.field == "ts" and item.changed for item in report.results)
    assert any(item.field == "a" and not item.changed for item in report.results)
    print("active_diff self-test OK")


if __name__ == "__main__":
    _self_test()
