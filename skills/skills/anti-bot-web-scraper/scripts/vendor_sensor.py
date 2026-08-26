"""Vendor sensor simulation and verified-recipe prediction.

This module does not pretend to fully emulate closed vendor sensors.  It
provides a bounded framework: vendor profiles map known sensor function
patterns, bundles are executed through the existing Node runner, and verified
recipes from samples/knowledge stores are ranked for the next host with the
same vendor/framework fingerprint.
"""

from __future__ import annotations

from typing import Any

VENDOR_PROFILES: dict[str, dict[str, Any]] = {
    "cloudflare": {
        "functions": ["cf", "turnstile", "clearance", "challenge"],
        "cookies": ["cf_clearance", "__cf_bm"],
        "scripts": ["challenge-platform", "turnstile"],
    },
    "datadome": {
        "functions": ["dd", "datadome", "sensor", "captcha"],
        "cookies": ["datadome"],
        "scripts": ["datadome", "js"],
    },
    "akamai": {
        "functions": ["_abck", "bm", "akamai", "sensor"],
        "cookies": ["_abck", "ak_bmsc", "bm_sz"],
        "scripts": ["bm", "akamai"],
    },
    "perimeterx": {
        "functions": ["px", "perimeterx", "sensor"],
        "cookies": ["_px3", "_pxhd"],
        "scripts": ["px", "perimeterx"],
    },
}


def sensor_profile(vendor: str) -> dict[str, Any]:
    """Return known patterns for a vendor sensor."""
    normalized = vendor.lower()
    return VENDOR_PROFILES.get(normalized, {"functions": [], "cookies": [], "scripts": []})


def simulate_vendor_sensor(
    vendor: str,
    js: str,
    candidate_names: list[str] | None = None,
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    """Execute a vendor bundle and trace sensor-like candidate functions."""
    try:
        from bundle_runner import run_bundle_execution
    except Exception:
        return {"ok": False, "error": "bundle_runner unavailable"}
    profile = sensor_profile(vendor)
    names = list(candidate_names or [])
    if not names:
        try:
            from deep_reverse import find_function_names

            names = find_function_names(js)[:30]
        except Exception:
            names = []
    result = run_bundle_execution(js, names, timeout=timeout)
    result["vendor"] = vendor
    result["profile"] = profile
    return result


def predict_recipes_from_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank verified recipes by vendor/framework frequency and hit count."""
    from collections import defaultdict

    scores: dict[tuple[str, str, str], dict[str, Any]] = {}
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for sample in samples:
        vendor = str(sample.get("vendor", "") or "unknown").lower()
        algorithm = str(sample.get("algorithm", "") or "")
        pattern = str(sample.get("pattern", "") or "")
        key = (vendor, algorithm, pattern)
        counts[key] += 1
        entry = scores.setdefault(
            key,
            {
                "vendor": vendor,
                "algorithm": algorithm,
                "pattern": pattern,
                "secret": str(sample.get("secret", "") or ""),
                "hits": int(sample.get("hits", 1) or 1),
                "hosts": set(),
            },
        )
        entry["hits"] += int(sample.get("hits", 1) or 1) - 1
        host = str(sample.get("host", "") or "")
        if host:
            entry["hosts"].add(host)
    ranked = []
    for (_vendor, _algorithm, _pattern), entry in sorted(
        scores.items(),
        key=lambda item: (item[1]["hits"], len(item[1]["hosts"])),
        reverse=True,
    ):
        entry["hosts"] = sorted(entry["hosts"])
        ranked.append(entry)
    return {
        "ok": True,
        "predictions": ranked[:20],
        "summary": {"samples": len(samples), "distinct_recipes": len(ranked)},
    }


def predict_for_host(
    host: str,
    knowledge_entries: list[Any],
) -> dict[str, Any]:
    """Predict recipes for a host from matching knowledge entries."""
    samples = []
    for entry in knowledge_entries:
        if getattr(entry, "host", "") == host:
            samples.append(
                {
                    "host": host,
                    "vendor": getattr(entry, "vendor", "") or "",
                    "algorithm": getattr(entry, "algorithm", "") or "",
                    "pattern": getattr(entry, "pattern", "") or "",
                    "secret": getattr(entry, "secret", "") or "",
                    "hits": getattr(entry, "hits", 1) or 1,
                }
            )
    return predict_recipes_from_samples(samples)


def _self_test() -> None:
    assert sensor_profile("datadome")["cookies"] == ["datadome"]
    report = predict_recipes_from_samples(
        [
            {"host": "a.com", "vendor": "cloudflare", "algorithm": "md5", "pattern": "payload+secret", "hits": 3},
            {"host": "b.com", "vendor": "cloudflare", "algorithm": "md5", "pattern": "payload+secret", "hits": 2},
        ]
    )
    assert report["summary"]["distinct_recipes"] == 1
    assert report["predictions"][0]["hits"] >= 5
    print("vendor_sensor self-test OK")


if __name__ == "__main__":
    _self_test()
