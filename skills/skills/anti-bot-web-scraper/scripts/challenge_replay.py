"""Failure snapshots and offline replay diagnostics for challenge variants.

When a real site rotates its anti-bot challenge, the pipeline saves the
blocked HTML, cookies, headers, and the variant fingerprint. Later runs can
load those snapshots, compare the current variant with a known one, and
choose a strategy without hitting the site again.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from challenge_evolution import ChallengeVariant, fingerprint_challenge


def _safe_host(host: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", host) or "unknown"


def save_challenge_snapshot(
    url: str,
    *,
    variant: ChallengeVariant,
    html: str = "",
    headers: dict[str, str] | None = None,
    cookies: list[dict[str, Any]] | None = None,
    status: int | None = None,
    snapshot_dir: str | Path = "reports/challenges",
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """Save one challenge failure as HTML plus machine-readable metadata."""
    if not snapshot_dir:
        return None
    root = Path(snapshot_dir)
    host = _safe_host(urlsplit(url).hostname or "unknown")
    target_dir = root / host
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    signature = variant.signature or "unknown"
    base = f"{stamp}-{signature}"
    html_path = target_dir / f"{base}.html"
    meta_path = target_dir / f"{base}.json"
    try:
        if html:
            html_path.write_text(html, encoding="utf-8")
        meta = {
            "url": url,
            "status": status,
            "saved_at": time.time(),
            "variant": variant.to_dict(),
            "headers": {str(key): str(value) for key, value in (headers or {}).items()},
            "cookies": [
                {
                    "name": str(item.get("name") or ""),
                    "value": str(item.get("value") or ""),
                    "domain": str(item.get("domain") or ""),
                    "path": str(item.get("path") or ""),
                    "expires": item.get("expires"),
                }
                for item in (cookies or [])
                if isinstance(item, dict)
            ],
            "html_path": str(html_path.relative_to(root)) if html_path.exists() else None,
            "extra": dict(extra or {}),
        }
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return meta_path
    except OSError:
        return None


def load_challenge_snapshot(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_snapshots(
    snapshot_dir: str | Path = "reports/challenges",
    *,
    host: str | None = None,
    signature: str | None = None,
) -> list[Path]:
    root = Path(snapshot_dir)
    if not root.exists():
        return []
    pattern = "*.json"
    paths = [
        item
        for item in root.rglob(pattern)
        if host is None or _safe_host(host) in str(item.parent.name)
    ]
    if signature:
        paths = [item for item in paths if signature in item.stem]
    return sorted(paths, key=lambda item: item.stat().st_mtime, reverse=True)


@dataclass
class ReplayDiagnosis:
    signature: str
    vendor: str
    stage: str
    known: bool = False
    markers: list[str] = field(default_factory=list)
    recommended_engines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signature": self.signature,
            "vendor": self.vendor,
            "stage": self.stage,
            "known": self.known,
            "markers": self.markers or [],
            "recommended_engines": self.recommended_engines or [],
        }


def diagnose_snapshot(
    meta: dict[str, Any],
    *,
    known_signatures: set[str] | None = None,
    available_engines: list[str] | None = None,
) -> ReplayDiagnosis:
    variant = ChallengeVariant.from_dict(meta.get("variant") or {})
    recommended: list[str] = []
    try:
        from waf_vendor import recommended_engine_order

        recommended = recommended_engine_order(
            variant.vendor,
            available_engines,
        )
    except Exception:
        pass
    return ReplayDiagnosis(
        signature=variant.signature,
        vendor=variant.vendor,
        stage=variant.stage,
        known=bool(known_signatures and variant.signature in known_signatures),
        markers=variant.markers,
        recommended_engines=recommended,
    )


def fingerprint_from_snapshot(meta: dict[str, Any]) -> ChallengeVariant:
    return ChallengeVariant.from_dict(meta.get("variant") or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fingerprint and diagnose challenge snapshots")
    parser.add_argument("--html", help="blocked challenge HTML file")
    parser.add_argument("--meta", help="existing snapshot JSON")
    parser.add_argument("--vendor", default="generic")
    parser.add_argument("--stage", default="unknown")
    parser.add_argument("--snapshot-dir", default="reports/challenges")
    parser.add_argument("--list", action="store_true", help="list saved snapshots")
    args = parser.parse_args(argv)
    if args.list:
        for path in find_snapshots(args.snapshot_dir):
            print(path)
        return 0
    if args.meta:
        meta = load_challenge_snapshot(args.meta)
    elif args.html:
        html = Path(args.html).read_text(encoding="utf-8")
        variant = fingerprint_challenge(
            vendor=args.vendor,
            stage=args.stage,
            html=html,
        )
        meta = {"variant": variant.to_dict()}
    else:
        parser.error("--html or --meta is required unless --list is used")
    diagnosis = diagnose_snapshot(meta)
    print(json.dumps(diagnosis.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
