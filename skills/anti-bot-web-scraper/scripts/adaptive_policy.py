"""Dynamic anti-bot strategy memory.

Anti-bot is a moving target. This module records per-host, per-stage,
per-engine outcomes and re-orders browser strategy on later runs, so the
stack automatically learns which engine/binding works best for a target
instead of always trying the same hardcoded order.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from math import exp
from pathlib import Path
from typing import Any


class AdaptivePolicyStore:
    """Thread-safe JSONL-backed store of strategy outcomes."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None
        self._lock = threading.RLock()
        self._rows: list[dict[str, Any]] = []
        if self.path is not None and self.path.exists():
            self._load()

    def _load(self) -> None:
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                self._rows.append(record)

    def record(
        self,
        *,
        host: str,
        stage: str,
        engine: str,
        success: bool,
        duration_ms: float = 0.0,
        attempts: int = 1,
        error: str | None = None,
        vendor: str | None = None,
        signature: str | None = None,
        proxy_region: str | None = None,
        cookie_ttl: float | None = None,
    ) -> None:
        row = {
            "ts": time.time(),
            "host": str(host),
            "stage": str(stage),
            "engine": str(engine),
            "success": bool(success),
            "duration_ms": round(float(duration_ms), 3),
            "attempts": int(attempts),
            "error": error,
            "vendor": vendor,
            "signature": signature,
            "proxy_region": proxy_region,
            "cookie_ttl": cookie_ttl,
        }
        with self._lock:
            self._rows.append(row)
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def recommend(
        self,
        host: str,
        stage: str,
        available: list[str],
        *,
        vendor: str | None = None,
        signature: str | None = None,
        proxy_region: str | None = None,
    ) -> list[str]:
        """Return engines ordered by historical success rate, then latency."""
        with self._lock:
            relevant = [
                row
                for row in self._rows
                if row.get("host") == host
                and row.get("stage") == stage
                and (vendor is None or row.get("vendor") == vendor)
                and (signature is None or row.get("signature") == signature)
                and (proxy_region is None or row.get("proxy_region") == proxy_region)
                and row.get("engine") in set(available)
            ]
        if not relevant:
            return list(available)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in relevant:
            grouped[str(row["engine"])].append(row)

        now = time.time()

        def _row_weight(row: dict[str, Any]) -> float:
            age = max(0.0, now - float(row.get("ts") or 0))
            return 0.5 + 0.5 * exp(-age / 86400.0)

        def score(engine: str) -> tuple[float, float, int, float]:
            rows = grouped[engine]
            weights = [_row_weight(row) for row in rows]
            weight_total = sum(weights) or 1.0
            weighted_success = sum(
                weight for row, weight in zip(rows, weights, strict=False) if row.get("success")
            )
            rate = weighted_success / weight_total
            weighted_duration = sum(
                float(row.get("duration_ms") or 0) * weight
                for row, weight in zip(rows, weights, strict=False)
            ) / weight_total
            return (rate, -weighted_duration, -len(rows), weight_total)

        ordered = sorted(available, key=score, reverse=True)
        return ordered

    def stats(self, host: str, stage: str) -> dict[str, Any]:
        with self._lock:
            rows = [
                row
                for row in self._rows
                if row.get("host") == host and row.get("stage") == stage
            ]
        total = len(rows)
        success = sum(1 for row in rows if row.get("success"))
        return {
            "host": host,
            "stage": stage,
            "samples": total,
            "success": success,
            "success_rate": round(success / total, 4) if total else 0.0,
            "engines": {
                engine: {
                    "samples": sum(1 for row in rows if row.get("engine") == engine),
                    "success": sum(
                        1 for row in rows if row.get("engine") == engine and row.get("success")
                    ),
                }
                for engine in sorted({str(row.get("engine")) for row in rows})
            },
        }

    def record_variant(
        self,
        *,
        host: str,
        vendor: str,
        signature: str,
        stage: str,
        success: bool,
        engine: str = "browser",
        duration_ms: float = 0.0,
        attempts: int = 1,
        error: str | None = None,
        proxy_region: str | None = None,
        cookie_ttl: float | None = None,
    ) -> None:
        """Record one outcome for a specific challenge variant."""
        self.record(
            host=host,
            stage=stage,
            engine=engine,
            success=success,
            duration_ms=duration_ms,
            attempts=attempts,
            error=error,
            vendor=vendor,
            signature=signature,
            proxy_region=proxy_region,
            cookie_ttl=cookie_ttl,
        )

    def should_skip(
        self,
        host: str,
        stage: str,
        engine: str,
        *,
        vendor: str | None = None,
        signature: str | None = None,
        proxy_region: str | None = None,
        min_samples: int = 2,
        max_success_rate: float = 0.0,
    ) -> bool:
        """Skip an engine when the same combination has never succeeded."""
        with self._lock:
            rows = [
                row
                for row in self._rows
                if row.get("host") == host
                and row.get("stage") == stage
                and row.get("engine") == engine
                and (vendor is None or row.get("vendor") == vendor)
                and (signature is None or row.get("signature") == signature)
                and (proxy_region is None or row.get("proxy_region") == proxy_region)
            ]
        if len(rows) < min_samples:
            return False
        success_rate = sum(1 for row in rows if row.get("success")) / len(rows)
        return success_rate <= max_success_rate

    def variant_stats(
        self,
        host: str,
        *,
        vendor: str | None = None,
        signature: str | None = None,
    ) -> dict[str, Any]:
        """Return per-variant success counts for a host."""
        with self._lock:
            rows = [
                row
                for row in self._rows
                if row.get("host") == host
                and (vendor is None or row.get("vendor") == vendor)
                and (signature is None or row.get("signature") == signature)
                and row.get("signature")
            ]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[str(row["signature"])].append(row)
        variants = {
            signature: {
                "samples": len(items),
                "success": sum(1 for row in items if row.get("success")),
                "vendor": str(items[0].get("vendor") or "generic"),
                "stage": str(items[0].get("stage") or "unknown"),
                "last_seen": max(float(row.get("ts") or 0) for row in items),
            }
            for signature, items in grouped.items()
        }
        return {
            "host": host,
            "vendor": vendor,
            "signature": signature,
            "variants": variants,
            "total_variants": len(variants),
        }

    def known_signatures(
        self,
        host: str,
        *,
        vendor: str | None = None,
    ) -> set[str]:
        """Return challenge signatures already seen for this host."""
        with self._lock:
            return {
                str(row["signature"])
                for row in self._rows
                if row.get("host") == host
                and row.get("signature")
                and (vendor is None or row.get("vendor") == vendor)
            }

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {"rows": list(self._rows)}


if __name__ == "__main__":
    print("adaptive_policy: import AdaptivePolicyStore for dynamic strategy memory.")
