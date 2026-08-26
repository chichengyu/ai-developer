"""Deep API analysis manifest for captured page/network data.

Builds a human- and machine-readable manifest from one or more PageCapture
objects: discovered endpoints, auth header names, candidate pagination
configuration, list data paths inside JSON responses, and endpoint scores.
The manifest can be replayed by api_client.ApiClient or saved for review.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api_client import ApiSpec, build_api_specs

AUTH_HEADER_HINTS = {
    "authorization",
    "x-api-key",
    "x-token",
    "token",
    "cookie",
    "x-csrf-token",
    "x-xsrf-token",
    "api-key",
    "apikey",
    "access-token",
}
PAGE_QUERY_HINTS = (
    "page",
    "pagenum",
    "pagenumber",
    "current",
    "currentpage",
    "offset",
    "limit",
    "pagesize",
    "page_size",
    "cursor",
    "next",
)
TOTAL_HINTS = ("total", "totalcount", "totalpages", "count")
HAS_MORE_HINTS = ("hasmore", "has_next", "hasnext")
NEXT_HINTS = ("nextcursor", "next", "nextpage")


@dataclass
class ApiManifest:
    sources: list[str] = field(default_factory=list)
    auth_headers: dict[str, str] = field(default_factory=dict)
    endpoints: list[dict[str, Any]] = field(default_factory=list)
    pagination: dict[str, Any] | None = None
    data_paths: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "auth_headers": self.auth_headers,
            "endpoints": self.endpoints,
            "pagination": self.pagination,
            "data_paths": self.data_paths,
            "summary": self.summary,
        }


def _get(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _collect_query_keys(captures: list[Any]) -> list[str]:
    keys: list[str] = []
    for capture in captures:
        for entry in _get(capture, "network", []) or []:
            url = str(_get(entry, "url", "") or "")
            if "?" not in url:
                continue
            query = url.split("?", 1)[1]
            for part in query.split("&"):
                key = part.split("=", 1)[0]
                if key:
                    keys.append(key.lower())
    return keys


def _collect_response_keys(captures: list[Any]) -> list[str]:
    keys: list[str] = []
    for capture in captures:
        for entry in _get(capture, "network", []) or []:
            data = _get(entry, "json_data", None)
            if isinstance(data, dict):
                keys.extend(str(key).lower() for key in data)
    return keys


def _infer_pagination(captures: list[Any]) -> dict[str, Any] | None:
    query_keys = _collect_query_keys(captures)
    response_keys = _collect_response_keys(captures)
    page_param = next((key for key in query_keys if key in PAGE_QUERY_HINTS), None)
    page_size_param = next(
        (key for key in query_keys if key in {"pagesize", "page_size", "limit"}),
        None,
    )
    total_path = next((key for key in response_keys if key in TOTAL_HINTS), None)
    has_more_path = next((key for key in response_keys if key in HAS_MORE_HINTS), None)
    next_path = next((key for key in response_keys if key in NEXT_HINTS), None)
    if not page_param and not (has_more_path or next_path):
        return None
    if page_param in {"cursor", "next"}:
        pagination: dict[str, Any] = {"type": "cursor", "param": page_param}
    elif page_param == "offset":
        pagination = {"type": "offset", "param": page_param}
        if page_size_param:
            pagination["page_size_param"] = page_size_param
    else:
        pagination = {"type": "page", "param": page_param or "page"}
        if page_size_param:
            pagination["page_size_param"] = page_size_param
    if total_path:
        pagination["total_path"] = total_path
    if has_more_path:
        pagination["has_more_path"] = has_more_path
    if next_path:
        pagination["next_path"] = next_path
    return pagination


def _extract_auth_headers(
    captures: list[Any],
    include_secrets: bool,
) -> dict[str, str]:
    found: dict[str, str] = {}
    for capture in captures:
        for entry in _get(capture, "network", []) or []:
            headers = _get(entry, "request_headers", {}) or {}
            if not isinstance(headers, dict):
                continue
            for key, value in headers.items():
                lower = str(key).lower()
                if lower in AUTH_HEADER_HINTS and lower not in found:
                    found[lower] = str(value) if include_secrets else "<redacted>"
    return dict(sorted(found.items()))


def _walk_list_paths(
    value: Any,
    prefix: str,
    depth: int,
    out: list[str],
) -> None:
    if depth > 30:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(child, list) and len(out) < 50:
                out.append(child_path)
            _walk_list_paths(child, child_path, depth + 1, out)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_list_paths(child, f"{prefix}[{index}]", depth + 1, out)


def _collect_data_paths(captures: list[Any]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for capture in captures:
        for entry in _get(capture, "network", []) or []:
            data = _get(entry, "json_data", None)
            if data is None:
                continue
            candidates: list[str] = []
            _walk_list_paths(data, "", 0, candidates)
            for path in candidates:
                if path not in seen:
                    seen.add(path)
                    paths.append(path)
    return paths[:50]


def _endpoint_score(spec: ApiSpec, has_json: bool) -> int:
    path = spec.url.lower()
    score = 0
    if any(marker in path for marker in ("/api/", "/v1/", "/v2/", "/graphql", ".json")):
        score += 3
    if spec.source == "captured":
        score += 2
    if has_json:
        score += 1
    return score


def _entry_has_json(captures: list[Any], method: str, url: str) -> bool:
    for capture in captures:
        for entry in _get(capture, "network", []) or []:
            if (
                str(_get(entry, "method", "") or "").upper() == method
                and str(_get(entry, "url", "") or "").split("?", 1)[0] == url.split("?", 1)[0]
            ):
                return _get(entry, "json_data", None) is not None
    return False


def analyze_captures(
    captures: list[Any],
    *,
    include_secrets: bool = False,
    max_endpoints: int = 500,
) -> ApiManifest:
    """Produce an API manifest from one or more PageCapture objects."""
    sources: list[str] = []
    specs: list[ApiSpec] = []
    seen: set[tuple[str, str]] = set()
    for capture in captures:
        url = _get(capture, "url", None)
        if url:
            sources.append(str(url))
        for spec in build_api_specs(capture, max_specs=max_endpoints):
            key = (spec.method.upper(), spec.url)
            if key not in seen:
                seen.add(key)
                specs.append(spec)

    endpoints: list[dict[str, Any]] = []
    for spec in specs:
        has_json = _entry_has_json(captures, spec.method, spec.url)
        endpoint = spec.to_dict()
        endpoint["score"] = _endpoint_score(spec, has_json)
        endpoint["api_like"] = bool(endpoint["score"] >= 3 or has_json)
        endpoints.append(endpoint)
    endpoints.sort(key=lambda item: item["score"], reverse=True)

    data_paths = _collect_data_paths(captures)
    pagination = _infer_pagination(captures)
    auth_headers = _extract_auth_headers(captures, include_secrets)
    summary = {
        "sources": len(sources),
        "endpoints": len(endpoints),
        "captured": sum(1 for item in endpoints if item["source"] == "captured"),
        "static": sum(1 for item in endpoints if item["source"] != "captured"),
        "auth_headers": len(auth_headers),
        "data_paths": len(data_paths),
        "pagination": 1 if pagination else 0,
    }
    return ApiManifest(
        sources=sources,
        auth_headers=auth_headers,
        endpoints=endpoints,
        pagination=pagination,
        data_paths=data_paths,
        summary=summary,
    )


def save_manifest(manifest: ApiManifest, path: str | Path) -> Path:
    out = Path(path)
    out.write_text(
        json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out


def load_capture(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> None:
    capture = {
        "url": "https://example.com/list",
        "network": [
            {
                "method": "GET",
                "url": "https://example.com/api/items?page=1",
                "resource_type": "fetch",
                "status": 200,
                "request_headers": {"Authorization": "Bearer secret", "X-Token": "abc"},
                "json_data": {"items": [{"id": 1}], "total": 3, "hasMore": True},
            }
        ],
        "analysis": {
            "api_endpoints": [
                {"method": "GET", "url": "https://example.com/api/config", "source": "script"}
            ],
            "pagination": {},
        },
    }
    manifest = analyze_captures([capture])
    assert manifest.auth_headers.get("authorization") == "<redacted>"
    assert manifest.pagination is not None and manifest.pagination["type"] == "page"
    assert "items" in manifest.data_paths
    assert any(item["api_like"] for item in manifest.endpoints)
    print("api_analyzer self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze captured page/API traffic")
    parser.add_argument("--input", action="append", default=[], help="PageCapture JSON file")
    parser.add_argument("--output", default=None, help="write API manifest JSON")
    parser.add_argument("--include-secrets", action="store_true", help="keep auth header values")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.input:
        parser.error("--input is required unless --self-test is used")
    captures = [load_capture(path) for path in args.input]
    manifest = analyze_captures(captures, include_secrets=args.include_secrets)
    text = json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2)
    if args.output:
        save_manifest(manifest, args.output)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
