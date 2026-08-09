"""Persistent challenge-cookie bank for cross-run anti-bot reuse.

Solved challenge cookies such as ``cf_clearance``, ``datadome``, ``_abck``,
and ``_px3`` are normally tied to the IP, user agent, and TLS profile that
created them. Keeping them in a per-host bank lets a later run reuse a still
valid clearance without launching a browser or paying for another CAPTCHA.

The bank is intentionally small and dependency-free: a JSON file with one
entry per host, atomic writes, expiry-aware reads, and a ``prune`` method
for long-running crawlers.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
import time
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from waf_vendor import anti_bot_cookie_present

DEFAULT_TTL_SECONDS = 6 * 60 * 60


def _cookie_field(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


class ChallengeCookieBank:
    """Thread-safe, JSON-backed store of host challenge cookies."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
    ) -> None:
        self.path = Path(path) if path else None
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Any]] = {}
        if self.path is not None and self.path.exists():
            self._load()

    @staticmethod
    def _host(value: str) -> str:
        value = str(value or "").strip()
        if "://" in value:
            value = urlsplit(value).hostname or value
        return value.lower().rstrip(".")

    @classmethod
    def _normalize_cookies(
        cls,
        cookies: Iterable[Any] | None,
        host: str,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in cookies or []:
            name = str(_cookie_field(item, "name") or "")
            value = str(_cookie_field(item, "value") or "")
            if not name or not value:
                continue
            domain = str(_cookie_field(item, "domain") or host)
            result.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": str(_cookie_field(item, "path") or "/"),
                    "secure": bool(_cookie_field(item, "secure", False)),
                    "httpOnly": bool(_cookie_field(item, "httpOnly", False)),
                    "sameSite": _cookie_field(item, "sameSite"),
                    "expires": _cookie_field(item, "expires"),
                    "session": bool(_cookie_field(item, "session", False)),
                    "partitioned": bool(_cookie_field(item, "partitioned", False)),
                }
            )
        return result

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        entries = payload.get("entries") if isinstance(payload, dict) else None
        if not isinstance(entries, dict):
            return
        for host, entry in entries.items():
            if isinstance(entry, dict) and isinstance(entry.get("cookies"), list):
                self._entries[str(host)] = entry

    def _save_locked(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "ttl_seconds": self.ttl_seconds,
            "entries": self._entries,
        }
        fd, temp_name = tempfile.mkstemp(
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.path)
        except Exception:
            with suppress(Exception):
                os.unlink(temp_name)
            raise

    def save(
        self,
        host: str,
        cookies: Iterable[Any] | None,
        *,
        vendor: str | None = None,
        source: str | None = None,
    ) -> int:
        """Store cookies for a host, replacing same-name/domain/path entries."""
        host_key = self._host(host)
        items = self._normalize_cookies(cookies, host_key)
        if not items:
            return 0
        now = time.time()
        expires_at: float | None = None
        for item in items:
            expires = item.get("expires")
            if isinstance(expires, int | float) and expires > 0:
                expires_at = max(expires_at or 0.0, float(expires))
        if expires_at is None:
            expires_at = now + self.ttl_seconds
        with self._lock:
            existing = self._entries.get(host_key) or {}
            merged = list(existing.get("cookies") or [])
            for item in items:
                key = (
                    str(item["name"]).lower(),
                    str(item["domain"]).lower(),
                    str(item["path"]),
                )
                merged = [
                    old
                    for old in merged
                    if (
                        str(old.get("name") or "").lower(),
                        str(old.get("domain") or "").lower(),
                        str(old.get("path") or "/"),
                    )
                    != key
                ]
                merged.append(item)
            self._entries[host_key] = {
                "updated_at": now,
                "expires_at": expires_at,
                "vendor": vendor or existing.get("vendor"),
                "source": source or existing.get("source"),
                "cookies": merged,
            }
            self._save_locked()
        return len(items)

    def cookies_for(self, host: str) -> list[dict[str, Any]]:
        """Return unexpired cookies that match the requested host."""
        host_key = self._host(host)
        now = time.time()
        with self._lock:
            entry = self._entries.get(host_key)
            if entry is None:
                return []
            entry_expires = entry.get("expires_at")
            if isinstance(entry_expires, int | float) and entry_expires < now:
                return []
            result: list[dict[str, Any]] = []
            for item in entry.get("cookies") or []:
                domain = str(item.get("domain") or host_key).lower().lstrip(".")
                if domain != host_key and not host_key.endswith("." + domain):
                    continue
                expires = item.get("expires")
                if isinstance(expires, int | float) and expires > 0 and expires < now:
                    continue
                result.append(dict(item))
            return result

    def has_challenge_cookies(self, host: str) -> bool:
        """True when the host bank contains a known anti-bot cookie."""
        return anti_bot_cookie_present(self.cookies_for(host))

    def remove(self, host: str) -> bool:
        host_key = self._host(host)
        with self._lock:
            if host_key not in self._entries:
                return False
            del self._entries[host_key]
            self._save_locked()
            return True

    def prune(self, ttl_seconds: float | None = None) -> int:
        """Remove entries older than the TTL or past their cookie expiry."""
        ttl = self.ttl_seconds if ttl_seconds is None else max(0.0, float(ttl_seconds))
        now = time.time()
        with self._lock:
            before = len(self._entries)
            stale = [
                host
                for host, entry in self._entries.items()
                if (now - float(entry.get("updated_at") or 0.0)) > ttl
                or (
                    isinstance(entry.get("expires_at"), int | float)
                    and entry["expires_at"] < now
                )
            ]
            for host in stale:
                del self._entries[host]
            if stale:
                self._save_locked()
            return before - len(self._entries)

    def status(self) -> dict[str, Any]:
        with self._lock:
            challenge_hosts = sum(
                1
                for host in self._entries
                if anti_bot_cookie_present(self.cookies_for(host))
            )
            return {
                "path": str(self.path) if self.path is not None else None,
                "hosts": len(self._entries),
                "challenge_hosts": challenge_hosts,
                "ttl_seconds": self.ttl_seconds,
            }

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self.status(),
                "entries": {
                    host: {
                        "updated_at": entry.get("updated_at"),
                        "expires_at": entry.get("expires_at"),
                        "vendor": entry.get("vendor"),
                        "source": entry.get("source"),
                        "cookies": list(entry.get("cookies") or []),
                    }
                    for host, entry in self._entries.items()
                },
            }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage a challenge-cookie bank")
    parser.add_argument("--path", required=True, help="JSON cookie bank path")
    parser.add_argument("--host", help="Host to inspect")
    parser.add_argument("--ttl", type=float, default=DEFAULT_TTL_SECONDS)
    parser.add_argument("--prune", action="store_true", help="Prune expired entries")
    parser.add_argument("--status", action="store_true", help="Print bank status")
    args = parser.parse_args(argv)
    bank = ChallengeCookieBank(args.path, ttl_seconds=args.ttl)
    if args.prune:
        bank.prune()
    if args.status:
        print(json.dumps(bank.status(), ensure_ascii=False, indent=2))
    if args.host:
        cookies = bank.cookies_for(args.host)
        print(
            json.dumps(
                {
                    "host": ChallengeCookieBank._host(args.host),
                    "challenge_cookies": bank.has_challenge_cookies(args.host),
                    "cookies": cookies,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
