"""Tests for vendor sensor profiles and recipe prediction."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from vendor_sensor import (  # noqa: E402
    predict_for_host,
    predict_recipes_from_samples,
    sensor_profile,
    simulate_vendor_sensor,
)


def test_sensor_profile_contains_vendor_patterns() -> None:
    profile = sensor_profile("akamai")
    assert "_abck" in profile["cookies"]
    assert profile["functions"]


def test_predict_recipes_ranks_verified_samples() -> None:
    report = predict_recipes_from_samples(
        [
            {"host": "a.com", "vendor": "cloudflare", "algorithm": "md5", "pattern": "payload+secret", "hits": 3},
            {"host": "b.com", "vendor": "cloudflare", "algorithm": "md5", "pattern": "payload+secret", "hits": 2},
        ]
    )
    assert report["summary"]["distinct_recipes"] == 1
    assert report["predictions"][0]["hits"] >= 5


def test_predict_for_host_uses_knowledge_entries() -> None:
    entries = [
        type(
            "E",
            (),
            {
                "host": "example.com",
                "vendor": "datadome",
                "algorithm": "sha256",
                "pattern": "payload",
                "secret": "s",
                "hits": 4,
            },
        )()
    ]
    report = predict_for_host("example.com", entries)
    assert report["predictions"][0]["algorithm"] == "sha256"


def test_simulate_vendor_sensor_returns_non_fatal_without_bundle() -> None:
    result = simulate_vendor_sensor("cloudflare", "var a = 1;", timeout=2)
    assert result["vendor"] == "cloudflare"
    assert "profile" in result
