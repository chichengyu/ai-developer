"""Tests for cross-site signature knowledge reuse."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from reverse_lab import analyze_capture_set, verify_signature_candidates  # noqa: E402
from signature_knowledge import (  # noqa: E402
    KnowledgeEntry,
    deprecate_entry,
    expired_entries,
    knowledge_hints,
    load_knowledge,
    lookup_knowledge,
    merge_verified_into_knowledge,
    migrate_knowledge,
    prune_knowledge,
    save_knowledge,
)


def test_knowledge_round_trip_and_lookup(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.json"
    entry = KnowledgeEntry(
        host="example.com",
        algorithm="md5",
        pattern="payload+secret",
        secret="known-secret",
    )
    save_knowledge(store, [entry])
    assert load_knowledge(store)
    assert lookup_knowledge("example.com", path=store)
    hints = knowledge_hints([entry])
    assert "known-secret" in hints["secrets"]


def test_merge_verified_persists_and_analyze_reuses(tmp_path: Path) -> None:
    import hashlib

    secret = "knowledge-secret"
    payload = "a=1&b=2"
    expected = hashlib.md5((payload + secret).encode()).hexdigest()
    capture = {
        "url": "https://example.com/",
        "hook": {
            "requests": [
                {
                    "method": "GET",
                    "url": f"https://example.com/api?sign={expected}&a=1&b=2",
                }
            ]
        },
        "network": [],
    }
    verifications = verify_signature_candidates([capture], secrets=[secret], algorithms=["md5"])
    store = tmp_path / "knowledge.json"
    merge_verified_into_knowledge([capture], verifications, store)
    assert load_knowledge(store)

    report = analyze_capture_set(
        [capture],
        secrets=[],
        algorithms=[],
        knowledge_store=store,
    )
    assert report.summary["knowledge_entries"] >= 1
    assert report.knowledge["entries"] >= 1
    assert report.summary["verified_signatures"] >= 1


def test_knowledge_auto_evolution(tmp_path: Path) -> None:
    store = tmp_path / "knowledge.json"
    entry = KnowledgeEntry(
        host="example.com",
        algorithm="md5",
        pattern="payload+secret",
        secret="old-secret",
        verified_at=0.0,
        expires_at=1.0,
    )
    save_knowledge(store, [entry])
    assert expired_entries(path=store)
    assert lookup_knowledge("example.com", path=store) == []
    assert prune_knowledge(store)["removed"] == 1
    assert load_knowledge(store) == []

    active = KnowledgeEntry(
        host="example.com",
        algorithm="md5",
        pattern="payload+secret",
        secret="new-secret",
        verified_at=time.time(),
        expires_at=time.time() + 3600,
    )
    save_knowledge(store, [active])
    migrated = tmp_path / "migrated.json"
    assert migrate_knowledge(store, migrated)["migrated"] == 1
    deprecate_entry(store, "example.com", reason="new variant")
    assert lookup_knowledge("example.com", path=store) == []
    assert load_knowledge(store)[0].status == "deprecated"
