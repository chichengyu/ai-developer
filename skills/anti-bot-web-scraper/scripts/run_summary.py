"""Unified end-of-run summary: save paths and per-resource crawl status.

Every entry point that collects pages, media, API records, or HLS streams
should finish by emitting a `run_summary` report. The report always lists:

- every output/save path and whether it exists
- every resource with its status: success / failed / blocked / skipped
- size, SHA-256, saved path, and error where available
- aggregate counters
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def _path_info(path: str | Path | None, role: str) -> dict[str, Any]:
    if not path:
        return {"role": role, "path": None, "exists": False, "bytes": None}
    target = Path(str(path))
    try:
        exists = target.exists()
        size = target.stat().st_size if exists else None
    except OSError:
        exists = False
        size = None
    return {
        "role": role,
        "path": str(target.resolve()) if exists else str(target),
        "exists": exists,
        "bytes": size,
    }


def resource_status(record: dict[str, Any]) -> str:
    """Normalize one page/media record into a stable status string."""
    if record.get("downloaded"):
        return "success"
    if record.get("error"):
        return "failed"
    if record.get("blocked"):
        return "blocked"
    if record.get("skipped_reason"):
        return "skipped"
    if record.get("kind") in {"media", "image", "video", "audio", "hls"}:
        return "discovered"
    if record.get("kind") == "page" and record.get("status") in {
        200,
        201,
        202,
        204,
    }:
        return "success"
    return "skipped"


def _resource_from_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": record.get("kind") or record.get("media_type") or "resource",
        "url": record.get("url"),
        "source_page": record.get("source_page"),
        "status": resource_status(record),
        "path": record.get("path"),
        "size": record.get("size"),
        "sha256": record.get("sha256"),
        "status_code": record.get("status"),
        "content_type": record.get("content_type"),
        "error": record.get("error"),
        "blocked": bool(record.get("blocked")),
        "details": record.get("details"),
    }


def final_report(
    *,
    save_paths: Iterable[dict[str, Any]] = (),
    resources: Iterable[dict[str, Any]] = (),
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard end-of-run report object."""
    paths = list(save_paths)
    items = list(resources)
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return {
        "generated_at": time.time(),
        "save_paths": paths,
        "resources": items,
        "resource_counts": counts,
        "summary": summary or {},
    }


def media_result_report(result: Any) -> dict[str, Any]:
    """Build a report from a MediaCrawlResult."""
    resources = [
        _resource_from_record(page.to_dict())
        for page in getattr(result, "pages", [])
    ]
    resources.extend(
        _resource_from_record(asset.to_dict())
        for asset in getattr(result, "media", [])
    )
    config = getattr(result, "config", {}) or {}
    save_paths = [
        _path_info(config.get("output_dir"), "media_output"),
        _path_info(config.get("jsonl_path"), "crawl_jsonl"),
        _path_info(config.get("resource_db_path"), "resource_db"),
    ]
    return final_report(
        save_paths=save_paths,
        resources=resources,
        summary=result.summary() if hasattr(result, "summary") else {},
    )


def jsonl_report(path: str | Path) -> dict[str, Any]:
    """Build a report by replaying a crawl JSONL file."""
    target = Path(path)
    resources: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict) or not record.get("url"):
                continue
            kind = record.get("kind")
            if kind in {"page", "image", "video", "audio", "hls", "media"}:
                resources.append(_resource_from_record(record))
            counts[kind or "unknown"] = counts.get(kind or "unknown", 0) + 1
    return final_report(
        save_paths=[_path_info(target, "crawl_jsonl")],
        resources=resources,
        summary={"jsonl_lines": sum(counts.values()), "kinds": counts},
    )


def pipeline_report(
    *,
    output: str | Path,
    manifest_output: str | Path | None = None,
    media_output: str | Path | None = None,
    resources: Iterable[dict[str, Any]] = (),
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a report for the web data pipeline entry point."""
    save_paths = [
        _path_info(output, "records_output"),
        _path_info(manifest_output, "api_manifest"),
        _path_info(media_output, "media_output"),
    ]
    return final_report(
        save_paths=save_paths,
        resources=resources,
        summary=summary,
    )


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    """Persist a run-summary report to JSON and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return target


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    print_report(final_report(save_paths=[], resources=[]))
