"""Proxy pool with round-robin/random rotation and failure cooldown.

The pool is used by MediaSession and ApiClient so a task can rotate
proxies on retry without changing the rest of the pipeline. A pool is
configured either as a plain list or as an object:

    ["http://p1:8080", "http://p2:8080"]

    {
        "proxies": ["http://p1:8080", "http://p2:8080"],
        "strategy": "round_robin",
        "max_failures": 3,
        "cooldown_seconds": 60
    }

ProxyPoolStore keeps named pools in one JSON file for desktop UI
management through the sidecar.
"""

from __future__ import annotations

import json
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ProxyState:
    proxy: str
    failures: int = 0
    cooldown_until: float = 0.0
    use_count: int = 0
    last_used_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "proxy": self.proxy,
            "failures": self.failures,
            "cooldown_until": self.cooldown_until,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at,
        }


class ProxyPool:
    """Thread-safe rotating proxy pool with per-proxy failure cooldown."""

    def __init__(
        self,
        proxies: list[str] | None = None,
        strategy: str = "round_robin",
        max_failures: int = 3,
        cooldown_seconds: float = 60.0,
    ) -> None:
        self.strategy = strategy if strategy in {"round_robin", "random"} else "round_robin"
        self.max_failures = max(1, int(max_failures))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._lock = threading.RLock()
        self._states = [
            ProxyState(proxy=str(proxy)) for proxy in (proxies or []) if str(proxy).strip()
        ]
        self._index = 0

    @classmethod
    def from_config(cls, config: Any) -> ProxyPool | None:
        if config is None:
            return None
        if isinstance(config, str):
            return cls([config])
        if isinstance(config, list):
            return cls([str(item) for item in config if str(item).strip()])
        if isinstance(config, dict):
            proxies = config.get("proxies") or config.get("proxy") or []
            return cls(
                [str(item) for item in proxies if str(item).strip()],
                strategy=str(config.get("strategy", "round_robin")),
                max_failures=int(config.get("max_failures", 3)),
                cooldown_seconds=float(config.get("cooldown_seconds", 60.0)),
            )
        return None

    def add(self, proxy: str) -> None:
        proxy = str(proxy).strip()
        if not proxy:
            return
        with self._lock:
            if any(state.proxy == proxy for state in self._states):
                return
            self._states.append(ProxyState(proxy=proxy))

    def remove(self, proxy: str) -> bool:
        with self._lock:
            before = len(self._states)
            self._states = [state for state in self._states if state.proxy != proxy]
            self._index = min(self._index, max(0, len(self._states) - 1))
            return len(self._states) < before

    def get_proxy(self) -> str | None:
        """Return the next available proxy, or None when all are cooling down."""
        now = time.time()
        with self._lock:
            available = [state for state in self._states if state.cooldown_until <= now]
            if not available:
                return None
            if self.strategy == "random":
                state = random.choice(available)
            else:
                state = available[self._index % len(available)]
                self._index += 1
            state.use_count += 1
            state.last_used_at = now
            return state.proxy

    def report_success(self, proxy: str | None) -> None:
        if not proxy:
            return
        with self._lock:
            for state in self._states:
                if state.proxy == proxy:
                    state.failures = 0
                    state.cooldown_until = 0.0
                    return

    def report_failure(self, proxy: str | None) -> None:
        if not proxy:
            return
        now = time.time()
        with self._lock:
            for state in self._states:
                if state.proxy == proxy:
                    state.failures += 1
                    if state.failures >= self.max_failures:
                        state.cooldown_until = now + self.cooldown_seconds
                        state.failures = 0
                    return

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [state.to_dict() for state in self._states]

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)


class ProxyPoolStore:
    """Named proxy pools persisted as one JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        self._configs: dict[str, dict[str, Any]] = {}
        self._pools: dict[str, ProxyPool] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for name, config in data.items():
            pool = ProxyPool.from_config(config)
            if pool is not None:
                self._pools[str(name)] = pool
                self._configs[str(name)] = (
                    config if isinstance(config, dict) else {"proxies": config}
                )

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._configs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def upsert(self, name: str, config: Any) -> dict[str, Any]:
        pool = ProxyPool.from_config(config)
        if pool is None:
            raise ValueError("proxy pool config must be a list or an object")
        normalized = config if isinstance(config, dict) else {"proxies": config}
        with self._lock:
            self._pools[name] = pool
            self._configs[name] = normalized
            self._save()
        return self.get_status(name)

    def get(self, name: str) -> ProxyPool | None:
        with self._lock:
            return self._pools.get(name)

    def get_status(self, name: str) -> dict[str, Any]:
        pool = self.get(name)
        if pool is None:
            raise KeyError(f"proxy pool not found: {name}")
        return {
            "name": name,
            "strategy": pool.strategy,
            "max_failures": pool.max_failures,
            "cooldown_seconds": pool.cooldown_seconds,
            "proxies": pool.status(),
        }

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [self.get_status(name) for name in sorted(self._pools)]

    def remove(self, name: str) -> bool:
        with self._lock:
            existed = name in self._pools
            self._pools.pop(name, None)
            self._configs.pop(name, None)
            if existed:
                self._save()
            return existed

    def close(self) -> None:
        """Compatibility hook for service shutdown."""


if __name__ == "__main__":
    print("desktop-app-dev proxy_pool: import ProxyPool / ProxyPoolStore for rotating proxies.")
