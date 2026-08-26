"""Replay generated signatures through the existing API session stack.

The reverse lab produces replay recipes; this module turns them into
``ApiSpec.prepare_request`` hooks and sends them through ``ApiClient`` /
``SmartFetchSession`` so cookies, UA, TLS fingerprint, proxy, and rate limits
stay on the same session.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path
from typing import Any

try:
    from api_client import ApiClient, ApiSpec  # type: ignore
    from reverse_lab import (  # type: ignore
        _flatten_params,
        _hash_digest,
        _iter_requests,
        _pattern_expression,
        _payload_serializations,
        _payload_with_headers,
    )
except Exception:  # pragma: no cover - scripts directory is normally on sys.path
    ApiClient = object  # type: ignore[assignment]
    ApiSpec = object  # type: ignore[assignment]

    def _flatten_params(params: dict[str, Any]) -> dict[str, Any]:
        return params

    def _iter_requests(capture: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    _hash_digest = None  # type: ignore[assignment]

    def _pattern_expression(pattern: str) -> str:
        return "payload + secret"

    def _payload_serializations(params: dict[str, Any]) -> list[str]:
        return []

    def _payload_with_headers(payload: str, headers: dict[str, str]) -> list[str]:
        return []


_TIMESTAMP_KEY_RE = re.compile(r"ts|timestamp|time|nonce|expire|deadline", re.IGNORECASE)
_HEADER_PAYLOAD_KEYS = ("X-Token=", "Authorization=", "Cookie=", "X-Nonce=", "X-Timestamp=")


def _serialization_kind(payload: str) -> str:
    text = payload.strip()
    if text.startswith("{"):
        return "compact-json"
    if ";" in text and "=" in text:
        return "semicolon"
    if "&" in text and "=" in text:
        return "urlencoded"
    if "=" in text:
        return "key-value-concat"
    return "values-concat"


def _build_payload(
    params: dict[str, Any],
    headers: dict[str, str],
    kind: str,
    include_headers: bool,
) -> str:
    flat = _flatten_params(params)
    items = sorted((str(key), str(value)) for key, value in flat.items())
    if kind == "compact-json":
        base = json.dumps(dict(items), ensure_ascii=False, separators=(",", ":"))
    elif kind == "semicolon":
        base = ";".join(f"{key}={value}" for key, value in items)
    elif kind == "key-value-concat":
        base = "".join(f"{key}={value}" for key, value in items)
    elif kind == "values-concat":
        base = "".join(value for _key, value in items)
    else:
        base = urllib.parse.urlencode(items)
    if include_headers and headers:
        selected = {
            key: value
            for key, value in headers.items()
            if re.search(r"token|auth|cookie|sign|nonce|timestamp|device|fingerprint", key, re.I)
        }
        header_items = sorted((str(key), str(value)) for key, value in selected.items())
        if header_items:
            base = base + "&" + "&".join(f"{key}={value}" for key, value in header_items)
    return base


class SignatureReplay:
    """Compute a verified signature before each request through the session."""

    def __init__(self, verification: dict[str, Any], secret: str | None = None) -> None:
        self.verification = verification
        self.secret = secret or str(verification.get("secret", "") or "")
        self.algorithm = str(verification.get("algorithm", "md5") or "md5")
        self.pattern = str(verification.get("pattern", "payload+secret") or "payload+secret")
        self.signature_param = str(verification.get("signature_param", "sign") or "sign")
        self.serialization = _serialization_kind(str(verification.get("payload", "") or ""))
        self.include_headers = any(
            key in str(verification.get("payload", "") or "") for key in _HEADER_PAYLOAD_KEYS
        )

    def __call__(self, context: dict[str, Any]) -> dict[str, Any]:
        params = dict(context.get("params") or {})
        headers = dict(context.get("headers") or {})
        payload_params = {
            key: value for key, value in params.items() if key != self.signature_param
        }
        payload = _build_payload(
            payload_params,
            headers,
            self.serialization,
            self.include_headers,
        )
        timestamp = next(
            (str(value) for key, value in params.items() if _TIMESTAMP_KEY_RE.search(str(key))),
            None,
        )
        if timestamp is None:
            timestamp = next(
                (
                    str(value)
                    for key, value in headers.items()
                    if _TIMESTAMP_KEY_RE.search(str(key))
                ),
                None,
            )
        timestamp = timestamp or str(int(time.time()))
        expression = _pattern_expression(self.pattern)
        data = eval(expression, {"payload": payload, "secret": self.secret, "timestamp": timestamp})
        digest = _hash_digest(
            self.algorithm,
            str(data).encode("utf-8"),
            str(self.secret).encode("utf-8"),
        )
        params[self.signature_param] = digest
        return {**context, "params": params}


def _sample_request(report: dict[str, Any]) -> dict[str, Any]:
    capture = report.get("capture") or {}
    hook = capture.get("hook") or {}
    for request in hook.get("requests", []) or []:
        if isinstance(request, dict):
            return request
    for request in capture.get("network", []) or []:
        if isinstance(request, dict):
            return request
    return {}


def _find_request(captures: list[dict[str, Any]] | None, url: str) -> dict[str, Any]:
    for capture in captures or []:
        for request in _iter_requests(capture):
            if str(request.get("url", "") or "") == url:
                return request
    for capture in captures or []:
        for request in _iter_requests(capture):
            left = urllib.parse.urlsplit(str(request.get("url", "") or ""))
            right = urllib.parse.urlsplit(url)
            if (left.scheme, left.netloc, left.path) == (right.scheme, right.netloc, right.path):
                return request
    return {}


def _spec_from_verification(
    verification: dict[str, Any],
    sample: dict[str, Any],
) -> ApiSpec:
    full_url = str(verification.get("url") or sample.get("url") or "")
    parts = urllib.parse.urlsplit(full_url)
    base_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    params = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    headers = dict(sample.get("headers") or sample.get("request_headers") or {})
    body = sample.get("body") or sample.get("post_data")
    method = str(sample.get("method") or "GET").upper()
    return ApiSpec(
        method=method,
        url=base_url,
        name="replay",
        headers=headers or None,
        params=params or None,
        body=body,
        source="reverse-replay",
        prepare_request=SignatureReplay(verification),
    )


def build_replay_spec(report: dict[str, Any]) -> ApiSpec:
    """Build an ApiSpec that signs itself through the session."""
    lab = report.get("reverse_lab") or report
    verifications = lab.get("signature_verifications", []) or []
    verification = next(
        (item for item in verifications if item.get("verified")),
        (verifications[0] if verifications else {}),
    )
    if not verification:
        raise ValueError("report contains no verified signature")
    sample = _sample_request(report)
    return _spec_from_verification(verification, sample)


def build_replay_specs(
    report: dict[str, Any],
    captures: list[dict[str, Any]] | None = None,
) -> list[ApiSpec]:
    """Build all replayable specs from a reverse report."""
    lab = report.get("reverse_lab") or report
    verifications = lab.get("signature_verifications", []) or []
    specs: list[ApiSpec] = []
    seen: set[tuple[str, str, str]] = set()
    for verification in verifications:
        if not verification.get("verified"):
            continue
        url = str(verification.get("url") or "")
        sample = _find_request(captures, url) if captures else {}
        spec = _spec_from_verification(verification, sample)
        key = (spec.method, spec.url, str(verification.get("signature_param") or "sign"))
        if key not in seen:
            seen.add(key)
            specs.append(spec)
    return specs


def _self_test() -> None:
    payload = "a=1&b=2"
    secret = "replay-secret"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    report = {
        "url": f"https://example.com/api?sign={expected}&a=1&b=2",
        "capture": {
            "url": f"https://example.com/api?sign={expected}&a=1&b=2",
            "hook": {
                "requests": [
                    {
                        "method": "GET",
                        "url": f"https://example.com/api?sign={expected}&a=1&b=2",
                    }
                ]
            },
            "network": [],
        },
        "reverse_lab": {
            "signature_verifications": [
                {
                    "url": f"https://example.com/api?sign={expected}&a=1&b=2",
                    "signature_param": "sign",
                    "pattern": "payload+secret",
                    "secret": secret,
                    "algorithm": "md5",
                    "payload": payload,
                    "verified": True,
                }
            ]
        },
    }
    spec = build_replay_spec(report)
    assert spec.method == "GET"
    context = spec.prepare_request(
        {
            "url": spec.url,
            "params": dict(spec.params or {}),
            "headers": dict(spec.headers or {}),
            "body": spec.body,
        }
    )
    assert context["params"]["sign"] == expected
    print("replay_client self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay reverse-lab signatures via ApiClient")
    parser.add_argument("--report", default=None, help="deep_reverse_auto / reverse_lab JSON")
    parser.add_argument("--output", default=None, help="write response JSON")
    parser.add_argument("--cookie-file", default=None, help="Playwright-style cookies JSON")
    parser.add_argument("--backend", default="auto", help="standard/auto/curl_cffi/...")
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--min-interval", type=float, default=0.5)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--dry-run", action="store_true", help="prepare spec and print it")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.report:
        parser.error("--report is required unless --self-test is used")
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    spec = build_replay_spec(report)
    if args.dry_run:
        print(json.dumps(spec.to_dict(), ensure_ascii=False, indent=2))
        return 0
    client = ApiClient(
        backend=args.backend,
        proxy=args.proxy,
        min_interval=args.min_interval,
        max_retries=args.max_retries,
        timeout=args.timeout,
    )
    try:
        if args.cookie_file:
            cookies = json.loads(Path(args.cookie_file).read_text(encoding="utf-8"))
            client.add_cookies(cookies)
        data = client.fetch_spec(spec)
    finally:
        client.close()
    result = {"spec": spec.to_dict(), "data": data}
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
