"""Metrics registry, Prometheus text export, and alert rules.

The registry is thread-safe and stores counters, gauges, and histograms.
`prometheus_text()` emits a Prometheus-compatible exposition. `AlertManager`
checks rules on demand or in a background thread and calls alert callbacks.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any


class MetricsRegistry:
    """Thread-safe counter / gauge / histogram registry."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._gauges: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
        self._histograms: dict[str, dict[tuple[tuple[str, str], ...], list[float]]] = defaultdict(
            dict
        )

    @staticmethod
    def _labels_key(labels: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((str(key), str(value)) for key, value in (labels or {}).items()))

    @staticmethod
    def _labels_key_name(key: tuple[tuple[str, str], ...]) -> str:
        return ";".join(f"{label}={value}" for label, value in key)

    def inc(self, name: str, labels: dict[str, Any] | None = None, delta: float = 1.0) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._counters[name][key] = self._counters[name].get(key, 0.0) + float(delta)

    def set(self, name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._gauges[name][key] = float(value)

    def observe(self, name: str, value: float, labels: dict[str, Any] | None = None) -> None:
        key = self._labels_key(labels)
        with self._lock:
            self._histograms[name].setdefault(key, []).append(float(value))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": {
                    name: {
                        self._labels_key_name(key): value
                        for key, value in series.items()
                    }
                    for name, series in self._counters.items()
                },
                "gauges": {
                    name: {
                        self._labels_key_name(key): value
                        for key, value in series.items()
                    }
                    for name, series in self._gauges.items()
                },
                "histograms": {
                    name: {
                        self._labels_key_name(key): {
                            "count": len(values),
                            "sum": sum(values),
                            "avg": sum(values) / len(values) if values else 0.0,
                            "max": max(values) if values else 0.0,
                        }
                        for key, values in series.items()
                    }
                    for name, series in self._histograms.items()
                },
            }

    def prometheus_text(self) -> str:
        lines: list[str] = []
        with self._lock:
            for name, series in self._counters.items():
                for key, value in series.items():
                    lines.append(_metric_line(name, "counter", key, value))
            for name, series in self._gauges.items():
                for key, value in series.items():
                    lines.append(_metric_line(name, "gauge", key, value))
            for name, series in self._histograms.items():
                for key, values in series.items():
                    for bucket, count in _histogram_buckets(values):
                        lines.append(
                            _metric_line(
                                f"{name}_bucket",
                                "histogram",
                                (*key, ("le", str(bucket))),
                                count,
                            )
                        )
                    lines.append(_metric_line(f"{name}_count", "histogram", key, len(values)))
                    lines.append(_metric_line(f"{name}_sum", "histogram", key, sum(values)))
        return "\n".join(lines)


def _metric_line(
    name: str,
    kind: str,
    labels: tuple[tuple[str, str], ...],
    value: float,
) -> str:
    label_text = ",".join(f'{k}="{v}"' for k, v in labels)
    return f"# TYPE {name} {kind}\n{name}{{{label_text}}} {value}"


def _histogram_buckets(values: list[float]) -> list[tuple[float, int]]:
    buckets = [0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
    return [(bucket, sum(1 for value in values if value <= bucket)) for bucket in buckets]


@dataclass
class AlertRule:
    name: str
    condition: Callable[[dict[str, Any]], bool]
    message: str
    cooldown_seconds: float = 300.0
    last_fired: float = 0.0


class AlertManager:
    """Evaluate alert rules against a metrics snapshot and fire callbacks."""

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        registry: MetricsRegistry | None = None,
    ) -> None:
        self.rules = list(rules or [])
        self.registry = registry
        self.callbacks: list[Callable[[AlertRule, dict[str, Any]], None]] = []
        self._lock = threading.RLock()

    def bind(self, registry: MetricsRegistry) -> None:
        self.registry = registry

    def add_rule(self, rule: AlertRule) -> None:
        self.rules.append(rule)

    def on_alert(self, callback: Callable[[AlertRule, dict[str, Any]], None]) -> None:
        self.callbacks.append(callback)

    def evaluate(self, snapshot: dict[str, Any]) -> list[AlertRule]:
        now = time.time()
        fired: list[AlertRule] = []
        with self._lock:
            for rule in self.rules:
                try:
                    triggered = rule.condition(snapshot)
                except Exception:
                    triggered = False
                if not triggered:
                    continue
                if now - rule.last_fired < rule.cooldown_seconds:
                    continue
                rule.last_fired = now
                fired.append(rule)
        for rule in fired:
            for callback in self.callbacks:
                with suppress(Exception):
                    callback(rule, snapshot)
        return fired

    def start(self, interval: float = 30.0, registry: MetricsRegistry | None = None) -> None:
        if registry is not None:
            self.registry = registry
        self._stop = threading.Event()

        def loop() -> None:
            while not self._stop.is_set():
                with suppress(Exception):
                    self.evaluate(self.registry.snapshot() if self.registry is not None else {})
                self._stop.wait(interval)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if hasattr(self, "_stop"):
            self._stop.set()
        if hasattr(self, "_thread") and self._thread.is_alive():
            self._thread.join(timeout=2.0)


def default_alert_rules() -> list[AlertRule]:
    def failure_rate(snapshot: dict[str, Any]) -> bool:
        counters = snapshot.get("counters", {})
        failed = sum(counters.get("task_failed", {}).values())
        total = sum(counters.get("task_total", {}).values())
        return total > 0 and failed / total > 0.6

    def proxy_depleted(snapshot: dict[str, Any]) -> bool:
        gauges = snapshot.get("gauges", {})
        available = sum(gauges.get("proxy_available", {}).values())
        return available <= 0.0

    def new_challenge_variant(snapshot: dict[str, Any]) -> bool:
        counters = snapshot.get("counters", {})
        return sum(counters.get("variant_new", {}).values()) > 0

    return [
        AlertRule(
            "high_failure_rate",
            failure_rate,
            "task failure rate exceeded 60%",
        ),
        AlertRule(
            "proxy_pool_depleted",
            proxy_depleted,
            "proxy pool has no available proxies",
        ),
        AlertRule(
            "new_challenge_variant",
            new_challenge_variant,
            "a new challenge variant was detected",
            cooldown_seconds=600.0,
        ),
    ]


if __name__ == "__main__":
    print("metrics: import MetricsRegistry / AlertManager for production metrics.")
