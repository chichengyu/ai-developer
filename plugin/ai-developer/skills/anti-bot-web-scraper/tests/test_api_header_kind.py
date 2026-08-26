"""Tests for API-request header fingerprinting."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api_client import ApiClient, ApiSpec  # noqa: E402
from fingerprint_bank import HeaderFingerprint  # noqa: E402
from smart_fetch import SmartFetchSession  # noqa: E402


def test_header_fingerprint_api_variant() -> None:
    api = HeaderFingerprint.chrome().api()
    assert api.headers["Sec-Fetch-Dest"] == "empty"
    assert api.headers["Sec-Fetch-Mode"] == "cors"
    assert api.headers["Sec-Fetch-Site"] == "same-origin"
    assert "application/json" in api.headers["Accept"]
    assert "Sec-Fetch-User" not in api.headers
    assert "Upgrade-Insecure-Requests" not in api.headers


def test_smart_fetch_uses_api_header_kind() -> None:
    session = SmartFetchSession(
        header_kind="api",
        auto_install_dependencies=False,
    )
    headers = session._fingerprinted_headers({})
    assert headers["Sec-Fetch-Dest"] == "empty"
    assert headers["Sec-Fetch-Mode"] == "cors"
    assert headers["Sec-Fetch-Site"] == "same-origin"
    assert "application/json" in headers["Accept"]
    assert "Sec-Fetch-User" not in headers
    assert "Upgrade-Insecure-Requests" not in headers


def test_smart_fetch_binding_api_headers() -> None:
    session = SmartFetchSession(
        header_kind="api",
        fingerprint_binding="chrome126",
        auto_install_dependencies=False,
    )
    headers = session._fingerprinted_headers({})
    assert headers["Sec-Fetch-Dest"] == "empty"
    assert headers["Sec-Fetch-Mode"] == "cors"
    assert "application/json" in headers["Accept"]
    assert "Sec-Fetch-User" not in headers
    assert "Upgrade-Insecure-Requests" not in headers


def test_api_client_standard_fetch_uses_api_headers() -> None:
    client = ApiClient(backend="standard")
    client.session = mock.Mock()
    client.session.request_json_with_meta.return_value = ({}, 200, {})
    client._fetch_one(
        ApiSpec(
            method="GET",
            url="https://example.com/api/items",
        )
    )
    kwargs = client.session.request_json_with_meta.call_args.kwargs
    headers = kwargs["headers"]
    assert headers["Sec-Fetch-Dest"] == "empty"
    assert headers["Sec-Fetch-Mode"] == "cors"
    assert "Sec-Fetch-User" not in headers
