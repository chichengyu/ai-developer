"""Tests for enhanced secret inference, algorithms, and active diff."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from reverse_lab import (  # noqa: E402
    analyze_capture_set,
    constrained_secret_search,
    infer_secret_candidates,
    verify_signature_candidates,
)


def _capture(url: str) -> dict:
    return {"url": url, "hook": {"requests": [{"method": "GET", "url": url}]}, "network": []}


def test_infer_secret_candidates_collects_storage_response_and_js() -> None:
    capture = _capture("https://example.com/api?appkey=abc123")
    capture["hook"]["requests"][0]["storage"] = {
        "local": {"signSecret": "storage-secret"},
        "session": {},
    }
    capture["network"] = [
        {
            "method": "GET",
            "url": "https://example.com/api",
            "response_body": {"accessToken": "response-token"},
        }
    ]
    report = infer_secret_candidates([capture], js_bundle='var appKey="js-secret";')
    candidates = report["candidates"]
    assert "storage-secret" in candidates
    assert "response-token" in candidates
    assert "js-secret" in candidates
    assert report["summary"]["candidates"] >= 4


def test_signature_verification_supports_sha512_and_hmac() -> None:
    secret = "s3cret"
    payload = "a=1&b=2"
    expected = hashlib.sha512((payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    rows = verify_signature_candidates([capture], secrets=[secret], algorithms=["sha512"])
    assert any(row.verified and row.algorithm == "sha512" for row in rows)

    expected_hmac = hmac.new(secret.encode(), payload.encode(), hashlib.sha512).hexdigest()
    capture_hmac = _capture(f"https://example.com/api?sign={expected_hmac}&a=1&b=2")
    rows_hmac = verify_signature_candidates(
        [capture_hmac],
        secrets=[secret],
        algorithms=["hmac-sha512"],
    )
    assert any(row.verified and row.algorithm == "hmac-sha512" for row in rows_hmac)


def test_signature_verification_includes_url_path() -> None:
    secret = "url-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + "/api" + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    rows = verify_signature_candidates([capture], secrets=[secret], algorithms=["md5"])
    assert any(row.verified and "/api" in row.payload for row in rows)


@pytest.mark.skipif(
    importlib.util.find_spec("cryptography") is None,
    reason="cryptography is not installed",
)
def test_signature_verification_supports_aes_cbc() -> None:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    secret = "key-material"
    payload = b"a=1&b=2"
    key = hashlib.sha256(secret.encode()).digest()[:16]
    iv = hashlib.sha256(payload).digest()[:16]
    padder = padding.PKCS7(128).padder()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padder.update(payload) + padder.finalize()) + encryptor.finalize()
    expected = base64.b64encode(ciphertext).decode()
    capture = _capture(f"https://example.com/api?encrypted={expected}&a=1&b=2")
    rows = verify_signature_candidates(
        [capture],
        secrets=[secret],
        algorithms=["aes-128-cbc"],
    )
    assert any(row.verified and row.algorithm == "aes-128-cbc" for row in rows)


@pytest.mark.skipif(
    importlib.util.find_spec("cryptography") is None,
    reason="cryptography is not installed",
)
def test_signature_verification_supports_aes_gcm() -> None:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    secret = "gcm-secret"
    payload = b"a=1&b=2"
    key = hashlib.sha256(secret.encode()).digest()[:16]
    nonce = hashlib.sha256(payload).digest()[:12]
    expected = base64.b64encode(AESGCM(key).encrypt(nonce, payload, None)).decode()
    capture = _capture(f"https://example.com/api?encrypted={expected}&a=1&b=2")
    rows = verify_signature_candidates(
        [capture],
        secrets=[secret],
        algorithms=["aes-128-gcm"],
    )
    assert any(row.verified and row.algorithm == "aes-128-gcm" for row in rows)


def test_signature_verification_supports_pbkdf2_and_base64url() -> None:
    secret = "pbkdf2-secret"
    payload = "a=1&b=2"
    derived = hashlib.pbkdf2_hmac("sha256", secret.encode(), payload.encode(), 10_000)[:32]
    expected = derived.hex()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    rows = verify_signature_candidates(
        [capture],
        secrets=[secret],
        algorithms=["pbkdf2-sha256"],
    )
    assert any(row.verified and row.algorithm == "pbkdf2-sha256" for row in rows)

    digest = hashlib.md5((payload + secret).encode()).digest()
    expected_url = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    capture_url = _capture(f"https://example.com/api?sign={expected_url}&a=1&b=2")
    rows_url = verify_signature_candidates(
        [capture_url],
        secrets=[secret],
        algorithms=["md5"],
    )
    assert any(row.verified for row in rows_url)


def test_analyze_capture_set_runs_active_diff_and_secret_inference() -> None:
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

    def sender(
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        data: object = None,
        body: object = None,
    ) -> tuple[int, str, dict[str, str]]:
        if "ts=" in url and "ts=1786000000" not in url:
            return 403, '{"error":"signature expired"}', {}
        return 200, '{"ok":true}', {}

    report = analyze_capture_set(
        [capture],
        active_diff=True,
        active_diff_sender=sender,
    )
    assert report.summary["active_diff"] >= 1
    assert report.summary["secret_candidates"] >= 1
    assert "active_diff" in report.to_dict()
    assert "secret_inference" in report.to_dict()


def test_constrained_secret_search_uses_hints() -> None:
    secret = "ab"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = _capture(f"https://example.com/api?sign={expected}&a=1&b=2")
    report = constrained_secret_search([capture], hints=["ab"], algorithms=["md5"])
    assert "ab" in report["found"]
    assert report["summary"]["found"] >= 1
