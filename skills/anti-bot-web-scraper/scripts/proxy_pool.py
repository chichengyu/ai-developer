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
import os
import random
import socket
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CURRENT_IP_PROXY = "current_ip"
_STUN_SERVERS = (
    ("stun.l.google.com", 19302),
    ("stun.cloudflare.com", 3478),
    ("stun1.l.google.com", 19302),
    ("stun.services.mozilla.com", 3478),
)
_HTTP_IP_ENDPOINTS = ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com")


def is_current_ip_proxy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"current_ip", "direct", "local"}


def normalize_proxy(value: Any) -> str | None:
    """Return None for the current-IP sentinel so callers use a direct connection."""
    if is_current_ip_proxy(value):
        return None
    value = str(value or "").strip()
    return value or None


def _stun_public_ip(timeout: float = 3.0) -> str | None:
    """Return the public reflexive IP seen by a STUN server."""
    for host, port in _STUN_SERVERS:
        sock: socket.socket | None = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            transaction_id = os.urandom(12)
            header = struct.pack(">HHI", 0x0001, 0, 0x2112A442) + transaction_id
            sock.sendto(header, (host, port))
            data, _ = sock.recvfrom(2048)
            if len(data) < 20:
                continue
            offset = 20
            while offset + 4 <= len(data):
                attr_type, attr_len = struct.unpack_from(">HH", data, offset)
                value_offset = offset + 4
                if attr_type in {0x0001, 0x0020} and value_offset + 8 <= len(data):
                    family = data[value_offset + 1]
                    if family == 0x01:
                        raw_ip = data[value_offset + 4 : value_offset + 8]
                        if attr_type == 0x0020:
                            packed = struct.unpack(">I", raw_ip)[0] ^ 0x2112A442
                            return socket.inet_ntoa(struct.pack(">I", packed))
                        return socket.inet_ntoa(raw_ip)
                offset += 4 + ((attr_len + 3) // 4) * 4
        except Exception:
            continue
        finally:
            if sock is not None:
                with suppress(Exception):
                    sock.close()
    return None


@dataclass
class ProxySourceConfig:
    """Declarative source used to pull a fresh proxy list from an API."""

    url: str
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    body: str | None = None
    format: str = "text"
    json_path: str | None = None
    proxy_field: str = "proxy"
    country_field: str = "country"
    city_field: str = "city"
    auth: str | None = None
    provider: str = "residential"
    timeout: float = 15.0
    sync: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProxySourceConfig:
        return cls(
            url=str(data.get("url") or ""),
            method=str(data.get("method") or "GET").upper(),
            headers=dict(data.get("headers") or {}),
            body=data.get("body"),
            format=str(data.get("format") or "text").lower(),
            json_path=data.get("json_path"),
            proxy_field=str(data.get("proxy_field") or "proxy"),
            country_field=str(data.get("country_field") or "country"),
            city_field=str(data.get("city_field") or "city"),
            auth=data.get("auth"),
            provider=str(data.get("provider") or "residential"),
            timeout=float(data.get("timeout") or 15.0),
            sync=bool(data.get("sync", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "method": self.method,
            "headers": dict(self.headers),
            "body": self.body,
            "format": self.format,
            "json_path": self.json_path,
            "proxy_field": self.proxy_field,
            "country_field": self.country_field,
            "city_field": self.city_field,
            "auth": self.auth,
            "provider": self.provider,
            "timeout": self.timeout,
            "sync": self.sync,
        }


@dataclass
class ProxyState:
    proxy: str
    failures: int = 0
    cooldown_until: float = 0.0
    use_count: int = 0
    last_used_at: float = 0.0
    latency_ms: float | None = None
    healthy: bool = True
    last_checked_at: float | None = None
    region: str | None = None
    protocol: str | None = None
    country: str | None = None
    city: str | None = None
    auth: str | None = None
    provider: str | None = None
    source: str | None = None
    added_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "proxy": self.proxy,
            "failures": self.failures,
            "cooldown_until": self.cooldown_until,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at,
            "latency_ms": self.latency_ms,
            "healthy": self.healthy,
            "last_checked_at": self.last_checked_at,
            "region": self.region,
            "protocol": self.protocol,
            "country": self.country,
            "city": self.city,
            "auth": self.auth,
            "provider": self.provider,
            "source": self.source,
            "added_at": self.added_at,
        }


class ProxyPool:
    """Thread-safe rotating proxy pool with per-proxy failure cooldown."""

    def __init__(
        self,
        proxies: list[str] | None = None,
        strategy: str = "round_robin",
        max_failures: int = 3,
        cooldown_seconds: float = 60.0,
        default_auth: str | None = None,
        source: ProxySourceConfig | dict[str, Any] | None = None,
        min_pool_size: int = 0,
        refill_threshold: int | None = None,
        auto_remove_on_fail: bool = True,
        preferred_region: str | None = None,
        preferred_country: str | None = None,
        preferred_city: str | None = None,
        use_current_ip: bool = True,
    ) -> None:
        self.strategy = strategy if strategy in {"round_robin", "random"} else "round_robin"
        self.max_failures = max(1, int(max_failures))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.default_auth = default_auth
        self.source = (
            source
            if isinstance(source, ProxySourceConfig)
            else ProxySourceConfig.from_dict(source)
            if isinstance(source, dict)
            else None
        )
        self.min_pool_size = max(0, int(min_pool_size))
        self.refill_threshold = (
            max(0, int(refill_threshold)) if refill_threshold is not None else self.min_pool_size
        )
        self.auto_remove_on_fail = bool(auto_remove_on_fail)
        self.preferred_region = preferred_region
        self.preferred_country = preferred_country
        self.preferred_city = preferred_city
        self.use_current_ip = bool(use_current_ip)
        self._lock = threading.RLock()
        self._states: list[ProxyState] = []
        self._retired_until: dict[str, float] = {}
        self._last_refill: float = 0.0
        self._last_refill_attempt: float = 0.0
        self._refill_errors: list[dict[str, Any]] = []
        self._refill_lock = threading.Lock()
        for proxy in proxies or []:
            proxy = str(proxy).strip()
            if proxy:
                self._states.append(self._make_state(proxy))
        self._index = 0
        self._sticky: dict[str, tuple[str, float]] = {}
        self._current_ip: str | None = None
        self._current_ip_at: float = 0.0
        self._current_ip_source: str | None = None
        self._http_egress_cache: str | None = None
        self._http_egress_cached_at: float = 0.0

    @staticmethod
    def _make_state(
        proxy: str,
        *,
        country: str | None = None,
        city: str | None = None,
        provider: str | None = None,
        auth: str | None = None,
        source: str | None = None,
    ) -> ProxyState:
        state = ProxyState(proxy=proxy)
        state.added_at = time.time()
        state.country = (country or "").upper() or None
        state.city = city
        state.provider = provider
        state.auth = auth
        state.source = source
        scheme, _, rest = proxy.partition("://")
        if scheme and "://" in proxy:
            state.protocol = scheme.lower()
            if any(keyword in scheme.lower() for keyword in ("socks", "socks5", "socks5h", "socks4")):
                state.protocol = scheme.lower()
        parsed = urllib.parse.urlsplit(proxy if "://" in proxy else f"http://{proxy}")
        host = parsed.hostname or ""
        if host:
            if state.country:
                if state.country.upper() in {"CN", "HK", "SG", "JP", "TW", "KR"}:
                    state.region = "asia"
                elif state.country.upper() in {"US", "CA"}:
                    state.region = "us"
                elif state.country.upper() in {"DE", "FR", "NL", "GB", "IE", "PL"}:
                    state.region = "eu"
            elif any(part in host.lower() for part in ("cn", "hongkong", "hk", "singapore", "sg", "jp")):
                state.region = "asia"
            elif any(part in host.lower() for part in ("us", "california", "la", "newyork", "dallas")):
                state.region = "us"
            elif any(part in host.lower() for part in ("de", "fra", "germany", "frankfurt", "amsterdam")):
                state.region = "eu"
        return state

    @classmethod
    def from_text(cls, text: str) -> ProxyPool:
        proxies = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        return cls(proxies)

    @classmethod
    def from_file(cls, path: str | Path) -> ProxyPool:
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def from_env(cls) -> ProxyPool:
        proxies: list[str] = []
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
            value = os.environ.get(key) or os.environ.get(key.lower())
            if value:
                proxies.append(value)
        return cls(proxies)

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
            source_config = config.get("source")
            if source_config is None:
                provider_value = config.get("provider")
                if isinstance(provider_value, dict):
                    source_config = provider_value
                elif isinstance(provider_value, str) and provider_value.startswith(
                    ("http://", "https://")
                ):
                    source_config = {"url": provider_value}
            if isinstance(source_config, str):
                source_config = {"url": source_config}
            return cls(
                [str(item) for item in proxies if str(item).strip()],
                strategy=str(config.get("strategy", "round_robin")),
                max_failures=int(config.get("max_failures", 3)),
                cooldown_seconds=float(config.get("cooldown_seconds", 60.0)),
                default_auth=config.get("default_auth"),
                source=source_config,
                min_pool_size=int(config.get("min_pool_size", 0)),
                refill_threshold=config.get("refill_threshold"),
                auto_remove_on_fail=bool(config.get("auto_remove_on_fail", True)),
                preferred_region=config.get("region") or config.get("regions"),
                preferred_country=config.get("country") or config.get("countries"),
                preferred_city=config.get("city") or config.get("cities"),
                use_current_ip=bool(config.get("use_current_ip", True)),
            )
        return None

    def add(
        self,
        proxy: str,
        *,
        country: str | None = None,
        city: str | None = None,
        provider: str | None = None,
        auth: str | None = None,
    ) -> bool:
        proxy = str(proxy).strip()
        if not proxy:
            return False
        proxy = _apply_proxy_auth(proxy, auth or self.default_auth)
        with self._lock:
            if any(state.proxy == proxy for state in self._states):
                return False
            if proxy in self._retired_until and self._retired_until[proxy] > time.time():
                return False
            self._states.append(
                self._make_state(
                    proxy,
                    country=country,
                    city=city,
                    provider=provider,
                    auth=auth or self.default_auth,
                    source=self.source.url if self.source is not None else None,
                )
            )
            return True

    def remove(self, proxy: str) -> bool:
        with self._lock:
            before = len(self._states)
            self._states = [state for state in self._states if state.proxy != proxy]
            self._index = min(self._index, max(0, len(self._states) - 1))
            return len(self._states) < before

    def get_proxy(self) -> str | None:
        """Return the next available proxy, or None when all are cooling down."""
        self.refill_if_needed()
        now = time.time()
        with self._lock:
            available = [
                state
                for state in self._states
                if state.cooldown_until <= now and state.healthy
            ]
            if not available:
                return CURRENT_IP_PROXY if self.use_current_ip else None
            if self.strategy == "random":
                state = random.choice(available)
            else:
                state = available[self._index % len(available)]
                self._index += 1
            state.use_count += 1
            state.last_used_at = now
            return state.proxy

    def get_proxy_for(
        self,
        *,
        region: str | None = None,
        country: str | None = None,
        city: str | None = None,
        provider: str | None = None,
    ) -> str | None:
        """Select a proxy matching region/country/city/provider requirements.

        When filters are provided, never fall back to the current IP because
        that would silently violate the geographic/provider constraint. The
        unconstrained ``get_proxy`` path keeps the current-IP fallback.
        """
        self.refill_if_needed()
        region = region or self.preferred_region
        country = (country or self.preferred_country or "").upper() or None
        city = city or self.preferred_city
        has_filters = any(
            value is not None
            for value in (region, country, city, provider)
        )
        now = time.time()
        with self._lock:
            available = [
                state
                for state in self._states
                if state.cooldown_until <= now
                and state.healthy
                and (region is None or (state.region or "").lower() == str(region).lower())
                and (country is None or (state.country or "").upper() == country.upper())
                and (city is None or (state.city or "").lower() == str(city).lower())
                and (provider is None or (state.provider or "") == str(provider))
            ]
            if not available:
                if has_filters or not self.use_current_ip:
                    return None
                return CURRENT_IP_PROXY
            if self.strategy == "random":
                state = random.choice(available)
            else:
                state = available[self._index % len(available)]
                self._index += 1
            state.use_count += 1
            state.last_used_at = now
            return state.proxy

    def get_weighted_proxy(self) -> str | None:
        now = time.time()
        with self._lock:
            available = [
                state
                for state in self._states
                if state.cooldown_until <= now and state.healthy
            ]
            if not available:
                return CURRENT_IP_PROXY if self.use_current_ip else None
            weights = [
                1.0 / (1.0 + (state.latency_ms or 0.0))
                for state in available
            ]
            state = random.choices(available, weights=weights, k=1)[0]
            state.use_count += 1
            state.last_used_at = now
            return state.proxy

    def best_proxy(self) -> str | None:
        now = time.time()
        with self._lock:
            available = [
                state
                for state in self._states
                if state.cooldown_until <= now and state.healthy
            ]
            if not available:
                return CURRENT_IP_PROXY if self.use_current_ip else None
            state = min(
                available,
                key=lambda item: (
                    item.latency_ms if item.latency_ms is not None else float("inf"),
                    item.use_count,
                ),
            )
            state.use_count += 1
            state.last_used_at = now
            return state.proxy

    def get_sticky_proxy(
        self,
        key: str,
        ttl: float = 300.0,
        **filters: Any,
    ) -> str | None:
        """Return the same proxy for a logical session until TTL expires."""
        now = time.time()
        entry = self._sticky.get(key)
        if entry is not None and entry[1] > now:
            return entry[0]
        proxy = self.get_proxy_for(**filters) if filters else self.get_proxy()
        if proxy is not None:
            self._sticky[key] = (proxy, now + max(0.0, ttl))
        return proxy

    def release_sticky_proxy(self, key: str) -> None:
        with self._lock:
            self._sticky.pop(key, None)

    def sticky_status(self) -> dict[str, dict[str, Any]]:
        now = time.time()
        with self._lock:
            return {
                key: {
                    "proxy": proxy,
                    "expires_in": max(0.0, expires - now),
                }
                for key, (proxy, expires) in self._sticky.items()
            }

    def report_success(self, proxy: str | None) -> None:
        if not proxy or is_current_ip_proxy(proxy):
            return
        with self._lock:
            for state in self._states:
                if state.proxy == proxy:
                    state.failures = 0
                    state.cooldown_until = 0.0
                    state.healthy = True
                    return

    def report_failure(self, proxy: str | None) -> None:
        if not proxy or is_current_ip_proxy(proxy):
            return
        now = time.time()
        removed = False
        with self._lock:
            for state in self._states:
                if state.proxy == proxy:
                    state.failures += 1
                    if state.failures >= self.max_failures:
                        if self.auto_remove_on_fail:
                            self._states = [
                                item for item in self._states if item.proxy != proxy
                            ]
                            self._index = min(
                                self._index,
                                max(0, len(self._states) - 1),
                            )
                            self._retired_until[proxy] = now + max(
                                10.0,
                                self.cooldown_seconds * 2,
                            )
                            removed = True
                        else:
                            state.cooldown_until = now + self.cooldown_seconds
                        state.failures = 0
                    return
        if removed:
            self.refill_if_needed()

    def set_health(
        self,
        proxy: str | None,
        healthy: bool,
        *,
        latency_ms: float | None = None,
        region: str | None = None,
    ) -> None:
        if not proxy:
            return
        now = time.time()
        with self._lock:
            for state in self._states:
                if state.proxy == proxy:
                    state.healthy = bool(healthy)
                    state.last_checked_at = now
                    if latency_ms is not None:
                        state.latency_ms = float(latency_ms)
                    if region:
                        state.region = str(region)
                    return

    def healthy_proxies(self) -> list[str]:
        now = time.time()
        with self._lock:
            available = [
                state.proxy
                for state in self._states
                if state.healthy and state.cooldown_until <= now
            ]
            if not available and self.use_current_ip:
                return [CURRENT_IP_PROXY]
            return available

    def refill_if_needed(self, *, force: bool = False) -> bool:
        """Pull a fresh proxy list when the active pool is below threshold."""
        if self.source is None:
            return False
        now = time.time()
        with self._lock:
            available = sum(
                1
                for state in self._states
                if state.healthy and state.cooldown_until <= now
            )
            if not force and available >= self.refill_threshold:
                return False
            if now - self._last_refill_attempt < 10.0:
                return False
            self._last_refill_attempt = now
        return self.refresh_from_source() > 0

    def refresh_from_source(self) -> int:
        """Fetch and sync proxies from the configured residential API source."""
        if self.source is None:
            return 0
        if not self._refill_lock.acquire(blocking=False):
            return 0
        try:
            entries = _fetch_proxy_source(self.source)
        except Exception as exc:
            with self._lock:
                self._refill_errors.append(
                    {
                        "at": time.time(),
                        "error": str(exc),
                    }
                )
            return 0
        finally:
            self._refill_lock.release()
        added = 0
        fresh: set[str] = set()
        now = time.time()
        with self._lock:
            existing = {state.proxy for state in self._states}
            for entry in entries:
                proxy = str(entry.get("proxy") or "").strip()
                if not proxy:
                    continue
                proxy = _apply_proxy_auth(proxy, entry.get("auth") or self.default_auth)
                fresh.add(proxy)
                if proxy in existing:
                    continue
                if proxy in self._retired_until and self._retired_until[proxy] > now:
                    continue
                self._states.append(
                    self._make_state(
                        proxy,
                        country=entry.get("country"),
                        city=entry.get("city"),
                        provider=entry.get("provider") or self.source.provider,
                        auth=entry.get("auth") or self.default_auth,
                        source=self.source.url,
                    )
                )
                existing.add(proxy)
                added += 1
            if self.source.sync:
                self._states = [
                    state
                    for state in self._states
                    if state.source != self.source.url or state.proxy in fresh
                ]
            self._last_refill = now
            if added:
                self._refill_errors = []
        return added

    def check_all(
        self,
        url: str = "https://example.com",
        *,
        timeout: float = 5.0,
        max_workers: int = 4,
    ) -> list[dict[str, Any]]:
        """Check every proxy with a real HTTP request and record latency."""
        results: list[dict[str, Any]] = []
        proxies = [
            state.proxy
            for state in self._states
            if not is_current_ip_proxy(state.proxy)
        ]
        with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
            futures = {
                pool.submit(_check_proxy, proxy, url, timeout): proxy for proxy in proxies
            }
            for future in as_completed(futures):
                proxy = futures[future]
                try:
                    latency, ok = future.result()
                except Exception:
                    latency, ok = None, False
                self.set_health(proxy, ok, latency_ms=latency)
                results.append(
                    {
                        "proxy": proxy,
                        "healthy": ok,
                        "latency_ms": latency,
                    }
                )
        return results

    def current_ip(self, timeout: float = 4.0) -> str | None:
        """Return the real public reflexive IP, preferring STUN over HTTP egress."""
        now = time.time()
        if self._current_ip is not None and now - self._current_ip_at < 60.0:
            return self._current_ip
        detected: str | None = None
        source: str | None = None
        detected = os.environ.get("CURRENT_PUBLIC_IP") or os.environ.get("REAL_PUBLIC_IP")
        if detected:
            source = "env"
        else:
            detected = _stun_public_ip(timeout=timeout)
            source = "stun" if detected else None
        if not detected:
            detected = self._http_egress_ip(timeout=timeout)
            source = "http" if detected else None
        if detected is None:
            try:
                detected = socket.gethostbyname(socket.gethostname())
                source = "local"
            except Exception:
                detected = None
        self._current_ip = detected
        self._current_ip_source = source
        self._current_ip_at = now
        return detected

    def _http_egress_ip(self, timeout: float = 4.0) -> str | None:
        """Return the public IP seen by HTTP echo services (Codex/cloud egress)."""
        now = time.time()
        if self._http_egress_cache is not None and now - self._http_egress_cached_at < 60.0:
            return self._http_egress_cache
        detected: str | None = None
        for endpoint in _HTTP_IP_ENDPOINTS:
            try:
                req = urllib.request.Request(
                    endpoint,
                    headers={"User-Agent": "anti-bot-web-scraper/1.0"},
                )
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    value = response.read().decode("utf-8", "replace").strip()
                if value:
                    detected = value
                    break
            except Exception:
                continue
        self._http_egress_cache = detected
        self._http_egress_cached_at = now
        return detected

    def status(self) -> list[dict[str, Any]]:
        with self._lock:
            return [state.to_dict() for state in self._states]

    def pool_status(self) -> dict[str, Any]:
        states = self.status()
        available = self.healthy_proxies()
        current_ip_value = self.current_ip()
        return {
            "strategy": self.strategy,
            "max_failures": self.max_failures,
            "cooldown_seconds": self.cooldown_seconds,
            "min_pool_size": self.min_pool_size,
            "refill_threshold": self.refill_threshold,
            "auto_remove_on_fail": self.auto_remove_on_fail,
            "preferred_region": self.preferred_region,
            "preferred_country": self.preferred_country,
            "preferred_city": self.preferred_city,
            "source": self.source.to_dict() if self.source is not None else None,
            "total": len(states),
            "available": len(available),
            "use_current_ip": self.use_current_ip,
            "current_ip": current_ip_value if self.use_current_ip else None,
            "current_ip_source": self._current_ip_source if self.use_current_ip else None,
            "http_egress_ip": (
                self._http_egress_ip(timeout=3.0) if self.use_current_ip else None
            ),
            "last_refill": self._last_refill,
            "refill_errors": list(self._refill_errors[-10:]),
            "proxies": states,
        }

    def start_health_monitor(
        self,
        url: str = "https://example.com",
        *,
        interval: float = 300.0,
        max_workers: int = 4,
        refill_interval: float = 60.0,
    ) -> None:
        self._health_stop = threading.Event()

        def loop() -> None:
            while not self._health_stop.is_set():
                try:
                    self.refill_if_needed(force=False)
                    self.check_all(url, max_workers=max_workers)
                except Exception:
                    pass
                self._health_stop.wait(interval)

        self._health_thread = threading.Thread(target=loop, daemon=True)
        self._health_thread.start()

    def stop_health_monitor(self) -> None:
        if hasattr(self, "_health_stop"):
            self._health_stop.set()
        if hasattr(self, "_health_thread") and self._health_thread.is_alive():
            self._health_thread.join(timeout=2.0)

    def close(self) -> None:
        self.stop_health_monitor()

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)


def _check_proxy(proxy: str, url: str, timeout: float) -> tuple[float | None, bool]:
    started = time.monotonic()
    scheme = proxy.partition("://")[0].lower()
    if scheme in {"socks", "socks4", "socks5", "socks5h"}:
        return _check_socks_proxy(proxy, url, timeout, started)
    handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    opener = urllib.request.build_opener(handler)
    try:
        with opener.open(url, timeout=timeout) as response:
            status = int(getattr(response, "status", response.code))
            latency = (time.monotonic() - started) * 1000
            return latency, status < 400
    except Exception:
        return None, False


def _check_socks_proxy(
    proxy: str,
    url: str,
    timeout: float,
    started: float,
) -> tuple[float | None, bool]:
    try:
        import httpx

        with httpx.Client(proxy=proxy, timeout=timeout, follow_redirects=True) as client:
            response = client.get(url)
            return (time.monotonic() - started) * 1000, response.status_code < 400
    except Exception:
        pass
    try:
        from curl_cffi.requests import Session

        with Session() as session:
            response = session.get(
                url,
                proxies={"http": proxy, "https": proxy},
                timeout=timeout,
                impersonate="chrome",
            )
            return (time.monotonic() - started) * 1000, int(response.status_code) < 400
    except Exception:
        return None, False


def _apply_proxy_auth(proxy: str, auth: str | None) -> str:
    if not auth or "@" in proxy:
        return proxy
    scheme, _, rest = proxy.partition("://")
    if not scheme or not rest:
        return proxy
    return f"{scheme}://{auth}@{rest}"


def _json_get(data: Any, path: str | None) -> Any:
    if not path:
        return data
    current = data
    for part in path.strip(".").split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _parse_source_entry(item: Any, source: ProxySourceConfig) -> dict[str, Any]:
    if isinstance(item, str):
        text = item.strip()
        parts = [part.strip() for part in text.split("|")]
        proxy = parts[0]
        country = parts[1] if len(parts) > 1 else None
        city = parts[2] if len(parts) > 2 else None
        return {
            "proxy": proxy,
            "country": country,
            "city": city,
            "provider": source.provider,
            "auth": source.auth,
        }
    if isinstance(item, dict):
        proxy = str(
            item.get(source.proxy_field)
            or item.get("proxy")
            or item.get("url")
            or item.get("host")
            or ""
        )
        if proxy and "://" not in proxy and item.get("port"):
            proxy = f"http://{proxy}:{item['port']}"
        return {
            "proxy": proxy,
            "country": str(item.get(source.country_field) or item.get("country") or ""),
            "city": str(item.get(source.city_field) or item.get("city") or ""),
            "provider": source.provider,
            "auth": source.auth or item.get("auth"),
        }
    return {"proxy": "", "provider": source.provider}


def _fetch_proxy_source(source: ProxySourceConfig) -> list[dict[str, Any]]:
    if not source.url:
        return []
    headers = dict(source.headers or {})
    headers.setdefault("Accept", "application/json,text/plain,*/*")
    request = urllib.request.Request(
        source.url,
        data=source.body.encode("utf-8") if source.body else None,
        headers=headers,
        method=source.method,
    )
    with urllib.request.urlopen(request, timeout=source.timeout) as response:
        raw = response.read().decode("utf-8", "replace")
    if source.format == "json":
        data = json.loads(raw)
        items = _json_get(data, source.json_path)
        if not isinstance(items, list):
            items = [items] if isinstance(items, dict) else []
        return [_parse_source_entry(item, source) for item in items]
    entries: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        entries.append(_parse_source_entry(line, source))
    return entries


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
            **pool.pool_status(),
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


class ProxyManager:
    """Manage multiple named proxy pools and fail over between them."""

    def __init__(
        self,
        pools: dict[str, ProxyPool] | None = None,
        *,
        default_pool: str = "default",
    ) -> None:
        self.pools = dict(pools or {})
        self.default_pool = default_pool
        if default_pool not in self.pools:
            self.pools[default_pool] = ProxyPool()

    def add_pool(self, name: str, pool: ProxyPool) -> None:
        self.pools[name] = pool

    def get_pool(self, name: str | None = None) -> ProxyPool:
        return self.pools.get(name or self.default_pool, self.pools[self.default_pool])

    def get_proxy(self, pool: str | None = None) -> str | None:
        return self.get_pool(pool).get_proxy()

    def get_weighted_proxy(self, pool: str | None = None) -> str | None:
        return self.get_pool(pool).get_weighted_proxy()

    def get_proxy_for(
        self,
        *,
        pool: str | None = None,
        region: str | None = None,
        country: str | None = None,
        city: str | None = None,
        provider: str | None = None,
    ) -> str | None:
        return self.get_pool(pool).get_proxy_for(
            region=region,
            country=country,
            city=city,
            provider=provider,
        )

    def get_sticky_proxy(
        self,
        key: str,
        *,
        pool: str | None = None,
        ttl: float = 300.0,
        **filters: Any,
    ) -> str | None:
        return self.get_pool(pool).get_sticky_proxy(key, ttl=ttl, **filters)

    def check_all(
        self,
        url: str = "https://example.com",
        *,
        timeout: float = 5.0,
        max_workers: int = 4,
    ) -> dict[str, list[dict[str, Any]]]:
        return {
            name: pool.check_all(url, timeout=timeout, max_workers=max_workers)
            for name, pool in self.pools.items()
        }

    def status(self) -> dict[str, list[dict[str, Any]]]:
        return {
            name: pool.status()
            for name, pool in self.pools.items()
        }

    def pool_status(self) -> dict[str, dict[str, Any]]:
        return {
            name: pool.pool_status()
            for name, pool in self.pools.items()
        }

    def refresh_all(self) -> dict[str, int]:
        return {
            name: pool.refresh_from_source()
            for name, pool in self.pools.items()
        }


def create_proxy_pool(config: Any) -> ProxyPool | None:
    """Build a ProxyPool from a config object, list, or existing pool."""
    if config is None:
        return ProxyPool(use_current_ip=True)
    if isinstance(config, ProxyPool):
        return config
    return ProxyPool.from_config(config)


if __name__ == "__main__":
    print(
        "desktop-app-dev proxy_pool: import ProxyPool / ProxyPoolStore / create_proxy_pool "
        "for production proxy rotation and refill."
    )
