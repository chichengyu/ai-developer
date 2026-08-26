"""Cross-site signature knowledge reuse.

Verified signature recipes are expensive to rediscover on every new host or
vendor variant.  This module persists them in a small JSON store and feeds
them back into ``reverse_lab`` as candidate secrets, algorithms, and payload
patterns before the next verification pass runs.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_KNOWLEDGE_TTL_SECONDS = 30 * 24 * 60 * 60


@dataclass
class KnowledgeEntry:
    host: str
    algorithm: str
    pattern: str
    secret: str
    url_pattern: str = ""
    vendor: str = ""
    framework: str = ""
    payload_example: str = ""
    challenge_signature: str = ""
    verified_at: float = 0.0
    source: str = "reverse_lab"
    hits: int = 1
    status: str = "active"
    expires_at: float = 0.0
    deprecated_reason: str = ""

    def key(self) -> tuple[str, str, str, str, str]:
        return (
            self.host,
            self.url_pattern,
            self.algorithm,
            self.pattern,
            self.secret,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_knowledge(path: str | Path) -> list[KnowledgeEntry]:
    """Load persisted signature knowledge entries."""
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries: list[KnowledgeEntry] = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, dict):
            try:
                entries.append(KnowledgeEntry(**{k: v for k, v in item.items() if k in KnowledgeEntry.__dataclass_fields__}))
            except TypeError:
                continue
    return entries


def save_knowledge(path: str | Path, entries: list[KnowledgeEntry]) -> None:
    """Persist knowledge entries atomically."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        [entry.to_dict() for entry in entries],
        ensure_ascii=False,
        indent=2,
    )
    fd, tmp = tempfile.mkstemp(prefix="knowledge-", suffix=".json", dir=str(file_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp, file_path)
    finally:
        if os.path.exists(tmp):
            with suppress(OSError):
                os.unlink(tmp)


def lookup_knowledge(
    host: str,
    entries: list[KnowledgeEntry] | None = None,
    path: str | Path | None = None,
) -> list[KnowledgeEntry]:
    """Return active, non-expired knowledge entries matching a host."""
    if entries is None:
        entries = load_knowledge(path) if path else []
    normalized = host.lower()
    now = time.time()
    return [
        entry
        for entry in entries
        if (entry.host.lower() == normalized or not entry.host)
        and entry.status != "deprecated"
        and (
            (entry.expires_at > 0 and entry.expires_at > now)
            or (
                entry.expires_at <= 0
                and (
                    entry.verified_at <= 0
                    or now - entry.verified_at <= DEFAULT_KNOWLEDGE_TTL_SECONDS
                )
            )
        )
    ]


def expired_entries(
    entries: list[KnowledgeEntry] | None = None,
    path: str | Path | None = None,
    *,
    now: float | None = None,
    max_age_seconds: float = DEFAULT_KNOWLEDGE_TTL_SECONDS,
) -> list[KnowledgeEntry]:
    """Return entries that are deprecated or older than the TTL."""
    if entries is None:
        entries = load_knowledge(path) if path else []
    current = now if now is not None else time.time()
    return [
        entry
        for entry in entries
        if entry.status == "deprecated"
        or (current - (entry.verified_at or 0) > max_age_seconds)
    ]


def prune_knowledge(
    path: str | Path,
    *,
    max_age_seconds: float = DEFAULT_KNOWLEDGE_TTL_SECONDS,
) -> dict[str, Any]:
    """Remove expired/deprecated entries and persist the active set."""
    entries = load_knowledge(path)
    removed = expired_entries(entries, max_age_seconds=max_age_seconds)
    removed_keys = {entry.key() for entry in removed}
    active = [entry for entry in entries if entry.key() not in removed_keys]
    save_knowledge(path, active)
    return {"removed": len(removed), "remaining": len(active)}


def deprecate_entry(
    path: str | Path,
    host: str,
    *,
    url_pattern: str | None = None,
    reason: str = "challenge variant changed",
) -> dict[str, Any]:
    """Mark matching knowledge entries deprecated."""
    entries = load_knowledge(path)
    changed = 0
    for entry in entries:
        if entry.host != host or (url_pattern and entry.url_pattern != url_pattern):
            continue
        if entry.status != "deprecated":
            entry.status = "deprecated"
            entry.deprecated_reason = reason
            changed += 1
    if changed:
        save_knowledge(path, entries)
    return {"changed": changed}


def migrate_knowledge(path: str | Path, target_path: str | Path) -> dict[str, Any]:
    """Copy active, non-expired entries to a new knowledge store."""
    entries = load_knowledge(path)
    active = [
        entry for entry in entries
        if entry.status != "deprecated"
        and (entry.expires_at <= 0 or entry.expires_at > time.time())
    ]
    save_knowledge(target_path, active)
    return {"migrated": len(active)}


def merge_verified_into_knowledge(
    captures: list[dict[str, Any]],
    verifications: list[Any],
    path: str | Path,
    *,
    host: str | None = None,
) -> list[KnowledgeEntry]:
    """Persist newly verified signature constructions."""
    existing = load_knowledge(path)
    by_key = {entry.key(): entry for entry in existing}
    default_host = host or ""
    for capture in captures:
        if not default_host:
            url = str(capture.get("url", "") or "")
            default_host = _host_of(url)
    now = time.time()
    for verification in verifications:
        if not getattr(verification, "verified", False):
            continue
        url = str(getattr(verification, "url", "") or "")
        entry = KnowledgeEntry(
            host=default_host or _host_of(url),
            algorithm=str(getattr(verification, "algorithm", "") or ""),
            pattern=str(getattr(verification, "pattern", "") or ""),
            secret=str(getattr(verification, "secret", "") or ""),
            url_pattern=url,
            payload_example=str(getattr(verification, "payload", "") or "")[:400],
            verified_at=now,
            source="reverse_lab",
            status="active",
            expires_at=now + DEFAULT_KNOWLEDGE_TTL_SECONDS,
            deprecated_reason="",
        )
        key = entry.key()
        if key in by_key:
            by_key[key].hits += 1
            by_key[key].verified_at = now
            by_key[key].status = "active"
            by_key[key].expires_at = now + DEFAULT_KNOWLEDGE_TTL_SECONDS
            by_key[key].deprecated_reason = ""
        else:
            by_key[key] = entry
    merged = sorted(by_key.values(), key=lambda item: item.host)
    save_knowledge(path, merged)
    return merged


def knowledge_hints(entries: list[KnowledgeEntry]) -> dict[str, list[str]]:
    """Return candidate secrets and algorithms from knowledge entries."""
    secrets: list[str] = []
    algorithms: list[str] = []
    for entry in entries:
        if entry.secret and entry.secret not in secrets:
            secrets.append(entry.secret)
        if entry.algorithm and entry.algorithm not in algorithms:
            algorithms.append(entry.algorithm)
    return {"secrets": secrets[:200], "algorithms": algorithms[:100]}


def _host_of(url: str) -> str:
    try:
        from urllib.parse import urlsplit

        return (urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "knowledge.json"
        entries = merge_verified_into_knowledge(
            [{"url": "https://example.com/"}],
            [
                type(
                    "V",
                    (),
                    {
                        "verified": True,
                        "url": "https://example.com/api?sign=x",
                        "algorithm": "md5",
                        "pattern": "payload+secret",
                        "secret": "abc",
                        "payload": "a=1",
                    },
                )()
            ],
            path,
        )
        assert entries
        assert load_knowledge(path)
        hints = knowledge_hints(entries)
        assert "abc" in hints["secrets"]
        assert "md5" in hints["algorithms"]
    print("signature_knowledge self-test OK")


if __name__ == "__main__":
    _self_test()
