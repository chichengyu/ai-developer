"""Multi-account session manager for desktop automation tasks.

An account profile carries everything a task needs to use one login
session: Playwright storage state, cookie file, browser profile dir,
proxy, request headers, and login selectors. AccountManager leases one
account at a time so concurrent workers never share the same session,
and failed accounts can be cooled down before being reused.

Profile example:

    {
        "name": "account-a",
        "storage_state": "profiles/a/storage.json",
        "cookies_path": "profiles/a/cookies.json",
        "user_data_dir": "profiles/a/profile",
        "proxy": "http://user:pass@127.0.0.1:8080",
        "headers": {"X-CSRF": "abc"},
        "login": {
            "url": "https://example.com/login",
            "username": "user-a",
            "password": "secret",
            "username_selector": "#username",
            "password_selector": "#password",
            "submit_selector": "button[type=submit]"
        },
        "cooldown_seconds": 60
    }
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _in_cooldown(profile: AccountProfile) -> bool:
    if not profile.cooldown_until:
        return False
    try:
        return datetime.fromisoformat(profile.cooldown_until) > datetime.now(timezone.utc)
    except ValueError:
        return False


@dataclass
class AccountProfile:
    name: str
    enabled: bool = True
    storage_state: str | None = None
    cookies_path: str | None = None
    cookies: list[dict[str, Any]] | None = None
    user_data_dir: str | None = None
    proxy: str | None = None
    headers: dict[str, str] | None = None
    login: dict[str, Any] | None = None
    cooldown_seconds: float = 0.0
    in_use: bool = False
    last_used_at: str | None = None
    last_error: str | None = None
    use_count: int = 0
    cooldown_until: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AccountProfile:
        return cls(
            name=str(data["name"]),
            enabled=bool(data.get("enabled", True)),
            storage_state=data.get("storage_state"),
            cookies_path=data.get("cookies_path"),
            cookies=data.get("cookies"),
            user_data_dir=data.get("user_data_dir"),
            proxy=data.get("proxy"),
            headers=data.get("headers"),
            login=data.get("login"),
            cooldown_seconds=float(data.get("cooldown_seconds", 0.0)),
            in_use=bool(data.get("in_use", False)),
            last_used_at=data.get("last_used_at"),
            last_error=data.get("last_error"),
            use_count=int(data.get("use_count", 0)),
            cooldown_until=data.get("cooldown_until"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AccountManager:
    """Thread-safe leases over named account profiles."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        self._profiles: dict[str, AccountProfile] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for name, item in data.items():
            item = dict(item)
            item["name"] = str(name)
            self._profiles[str(name)] = AccountProfile.from_dict(item)

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {name: profile.to_dict() for name, profile in self._profiles.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def upsert(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("name"):
            raise ValueError("account name is required")
        with self._lock:
            existing = self._profiles.get(str(data["name"]))
            use_count = existing.use_count if existing else 0
            profile = AccountProfile.from_dict(data)
            profile.use_count = use_count
            self._profiles[profile.name] = profile
            self._save()
            return profile.to_dict()

    def acquire(self, name: str | None = None) -> dict[str, Any] | None:
        """Lease one idle account. Returns a copy, or None when unavailable."""
        now = datetime.now(timezone.utc)
        with self._lock:
            candidates = [
                profile
                for profile in self._profiles.values()
                if profile.enabled and not profile.in_use and not _in_cooldown(profile)
            ]
            if name is not None:
                candidates = [profile for profile in candidates if profile.name == name]
            if not candidates:
                return None
            profile = min(candidates, key=lambda item: (item.use_count, item.last_used_at or ""))
            profile.in_use = True
            profile.last_used_at = now.isoformat()
            profile.use_count += 1
            self._save()
            return profile.to_dict()

    def release(
        self,
        name: str,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        with self._lock:
            profile = self._profiles.get(name)
            if profile is None:
                return
            profile.in_use = False
            if success:
                profile.cooldown_until = None
                profile.last_error = None
            else:
                profile.last_error = error or "task failed"
                if profile.cooldown_seconds > 0:
                    profile.cooldown_until = (
                        datetime.now(timezone.utc) + timedelta(seconds=profile.cooldown_seconds)
                    ).isoformat()
            self._save()

    def remove(self, name: str) -> bool:
        with self._lock:
            existed = name in self._profiles
            self._profiles.pop(name, None)
            if existed:
                self._save()
            return existed

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                profile.to_dict()
                for profile in sorted(
                    self._profiles.values(),
                    key=lambda item: item.name,
                )
            ]

    def get(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            profile = self._profiles.get(name)
            return profile.to_dict() if profile else None

    def close(self) -> None:
        """Compatibility hook for service shutdown."""


if __name__ == "__main__":
    print(
        "desktop-app-dev account_manager: import AccountManager / AccountProfile for multi-account leases."
    )
