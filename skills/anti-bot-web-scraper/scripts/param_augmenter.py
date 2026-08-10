"""Automatic API parameter augmentation from deep-crawled subpages.

After a crawl, this module harvests candidate parameter names and values from
page URLs, links, forms, embedded JSON state, pagination fields, and the API
endpoints each page references. It then expands discovered ``ApiSpec`` objects
into concrete fetch variants, so one page tree can drive many API calls without
hand-writing parameter lists.
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api_client import ApiSpec

_PAGINATION_NAMES = frozenset(
    {
        "page",
        "pagenum",
        "pagenumber",
        "current",
        "currentpage",
        "pagesize",
        "page_size",
        "offset",
        "limit",
        "cursor",
        "next",
        "nextpage",
        "nextcursor",
        "total",
        "totalcount",
        "totalpages",
        "hasmore",
        "hasnext",
        "isend",
        "nomore",
    }
)
_SENSITIVE_EXACT = frozenset(
    {
        "token",
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "passwd",
        "secret",
        "sign",
        "signature",
        "cookie",
        "session",
        "csrf",
        "xsrf",
    }
)
_SENSITIVE_HINTS = (
    "token",
    "secret",
    "password",
    "apikey",
    "authorization",
    "cookie",
    "csrf",
    "xsrf",
    "signature",
)
_URL_ISH = re.compile(r"^https?://", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)

_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "scope": "related_then_global",
    "include_query": True,
    "include_links": True,
    "include_api_query": True,
    "include_form_fields": True,
    "include_json_fields": True,
    "include_embedded_json": True,
    "include_pagination": False,
    "include_path_placeholders": True,
    "infer_path_templates": True,
    "max_templates": 20,
    "site_index_max_endpoints": 500,
    "exclude_sensitive": True,
    "exclude_keys": [],
    "expand_existing": True,
    "max_values_per_param": 10,
    "max_param_keys": 100,
    "max_variants": 100,
    "max_specs": 500,
    "max_path_values": 50,
    "min_value_length": 1,
    "param_map": [],
}


@dataclass
class AugmentationStats:
    """Counters describing one parameter augmentation run."""

    specs_input: int = 0
    specs_output: int = 0
    variants: int = 0
    templates: int = 0
    added_keys: int = 0
    harvested_values: int = 0
    related_pages: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "specs_input": self.specs_input,
            "specs_output": self.specs_output,
            "variants": self.variants,
            "templates": self.templates,
            "added_keys": self.added_keys,
            "harvested_values": self.harvested_values,
            "related_pages": self.related_pages,
        }


def _get(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return list(value)
    return [value]


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _url_base(url: str) -> str:
    return urllib.parse.urlsplit(url)._replace(query="", fragment="").geturl()


def _query_params(url: str) -> dict[str, list[str]]:
    parts = urllib.parse.urlsplit(url)
    params: dict[str, list[str]] = {}
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        params.setdefault(key, []).append(value)
    return params


_API_URL_KEY_HINTS = (
    "url",
    "api",
    "endpoint",
    "next",
    "link",
    "href",
    "callback",
    "upload",
    "gateway",
    "server",
)
_SKIP_URL_PREFIXES = ("javascript:", "data:", "blob:", "mailto:", "tel:", "about:")
_SKIP_MEDIA_EXTS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".bmp",
    ".avif",
    ".mp4",
    ".webm",
    ".mkv",
    ".mp3",
    ".wav",
    ".flac",
    ".m3u8",
)


def extract_api_urls(data: Any, base_url: str | None = None) -> list[str]:
    """Recursively extract API-like URLs from a JSON response."""

    found: list[str] = []

    def looks_fetchable(value: str) -> bool:
        lowered = value.lower()
        if lowered.startswith(_SKIP_URL_PREFIXES):
            return False
        if not value.startswith(("http://", "https://", "//", "/")):
            return False
        path = urllib.parse.urlsplit(value).path.lower()
        return not path.endswith(_SKIP_MEDIA_EXTS)

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 8:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                norm = _normalize_key(str(key))
                if (
                    isinstance(child, str)
                    and any(hint in norm for hint in _API_URL_KEY_HINTS)
                    and looks_fetchable(child)
                ):
                    resolved = urllib.parse.urljoin(base_url or "", child)
                    if resolved.startswith(("http://", "https://")) and resolved not in found:
                        found.append(resolved)
                walk(child, depth + 1)
        elif isinstance(value, list):
            for child in value[:200]:
                walk(child, depth + 1)

    walk(data)
    return found


def _is_pagination(norm: str) -> bool:
    if norm in _PAGINATION_NAMES:
        return True
    return (
        norm.startswith(
            (
                "page",
                "total",
                "hasmore",
                "hasnext",
                "next",
                "isend",
                "nomore",
                "offset",
                "cursor",
            )
        )
        or norm.endswith(
            ("page", "pagesize", "pagenum", "page_size", "limit", "cursor", "offset")
        )
    )


def _is_excluded(norm: str, config: dict[str, Any]) -> bool:
    excluded = {_normalize_key(str(item)) for item in _as_list(config.get("exclude_keys"))}
    return (
        norm in excluded
        or (
            config.get("exclude_sensitive", True)
            and (norm in _SENSITIVE_EXACT or any(hint in norm for hint in _SENSITIVE_HINTS))
        )
        or (not config.get("include_pagination", False) and _is_pagination(norm))
    )


def _collect_scalar_pairs(
    value: Any,
    add: Any,
    *,
    depth: int = 0,
    max_items: int = 600,
) -> None:
    if depth > 7 or max_items <= 0:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(child, dict | list):
                _collect_scalar_pairs(child, add, depth=depth + 1, max_items=max_items)
            else:
                text = str(child).strip() if child is not None else ""
                if text and len(text) <= 128:
                    add(str(key), text)
                    max_items -= 1
    elif isinstance(value, list):
        for index, child in enumerate(value[:200]):
            if isinstance(child, dict | list):
                _collect_scalar_pairs(child, add, depth=depth + 1, max_items=max_items)
            else:
                text = str(child).strip() if child is not None else ""
                if text and len(text) <= 128:
                    add(f"item_{index}", text)
                    max_items -= 1


def collect_page_param_hints(
    page_url: str,
    analysis: Any = None,
    *,
    links: list[str] | None = None,
    storage: dict[str, Any] | None = None,
    network: list[Any] | None = None,
    media_urls: list[str] | None = None,
    max_values: int = 200,
    max_keys: int = 200,
) -> dict[str, list[str]]:
    """Harvest scalar parameter hints from one page and its analysis."""

    hints: dict[str, dict[str, Any]] = {}

    def add(key: Any, value: Any) -> None:
        if key is None or value is None:
            return
        text = str(value).strip()
        if not text:
            return
        norm = _normalize_key(str(key))
        bucket = hints.get(norm)
        if bucket is None:
            if len(hints) >= max_keys:
                return
            bucket = {"key": str(key), "values": []}
            hints[norm] = bucket
        if text not in bucket["values"] and len(bucket["values"]) < max_values:
            bucket["values"].append(text)

    def add_url_query(url: str) -> None:
        for key, values in _query_params(url).items():
            for value in values:
                add(key, value)

    if page_url:
        add_url_query(page_url)
    for link in links or []:
        add_url_query(str(link))
    for media_url in media_urls or []:
        add_url_query(str(media_url))

    for entry in network or []:
        entry_url = (
            entry.get("url") if isinstance(entry, dict) else getattr(entry, "url", None)
        )
        if entry_url:
            add_url_query(str(entry_url))
        frame_data = (
            entry.get("frame_data") if isinstance(entry, dict) else getattr(entry, "frame_data", None)
        )
        if isinstance(frame_data, dict):
            _collect_scalar_pairs(frame_data, add)
        json_data = (
            entry.get("json_data") if isinstance(entry, dict) else getattr(entry, "json_data", None)
        )
        if isinstance(json_data, dict):
            _collect_scalar_pairs(json_data, add)
        body_text = (
            entry.get("body_text") if isinstance(entry, dict) else getattr(entry, "body_text", None)
        )
        if isinstance(body_text, str):
            for found_url in _URL_RE.findall(body_text):
                add_url_query(found_url)

    if isinstance(storage, dict):
        origin_entries: list[dict[str, Any]] = []
        for origin in storage.get("origins") or []:
            if isinstance(origin, dict):
                origin_entries.append(origin)
        for origin in origin_entries:
            for bucket_name in ("localStorage", "sessionStorage"):
                items = origin.get(bucket_name) or []
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            add(item.get("name"), item.get("value"))
        for bucket_name in ("local", "session"):
            values = storage.get(bucket_name)
            if isinstance(values, dict):
                for key, value in values.items():
                    add(key, value)

    if analysis is None:
        return {bucket["key"]: bucket["values"] for bucket in hints.values()}

    endpoints = (
        analysis.get("api_endpoints") if isinstance(analysis, dict) else getattr(analysis, "api_endpoints", None)
    )
    for endpoint in endpoints or []:
        endpoint_url = (
            endpoint.get("url") if isinstance(endpoint, dict) else getattr(endpoint, "url", None)
        )
        if endpoint_url:
            add_url_query(str(endpoint_url))

    json_fields = (
        analysis.get("json_api_fields") if isinstance(analysis, dict) else getattr(analysis, "json_api_fields", None)
    )
    for item in json_fields or []:
        key = item.get("key") if isinstance(item, dict) else getattr(item, "key", None)
        value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
        add(key, value)
        if value and _URL_ISH.match(str(value)):
            add_url_query(str(value))

    pagination = (
        analysis.get("pagination") if isinstance(analysis, dict) else getattr(analysis, "pagination", None)
    )
    if isinstance(pagination, dict):
        for key, entries in pagination.items():
            for entry in entries or []:
                value = entry.get("value") if isinstance(entry, dict) else getattr(entry, "value", None)
                add(key, value)

    form_fields = (
        analysis.get("form_fields") if isinstance(analysis, dict) else getattr(analysis, "form_fields", None)
    )
    for item in form_fields or []:
        name = item.get("name") if isinstance(item, dict) else getattr(item, "name", None)
        value = item.get("value") if isinstance(item, dict) else getattr(item, "value", None)
        add(name, value)

    embedded = (
        analysis.get("embedded_json") if isinstance(analysis, dict) else getattr(analysis, "embedded_json", None)
    )
    for block in embedded or []:
        data = block.get("data") if isinstance(block, dict) else getattr(block, "data", None)
        if data is not None:
            _collect_scalar_pairs(data, add)

    return {bucket["key"]: bucket["values"] for bucket in hints.values()}


def _page_url(page: Any) -> str:
    url = _get(page, "url", None)
    return str(url) if url else ""


def _page_analysis(page: Any) -> Any:
    return _get(page, "analysis", None)


def _page_links(page: Any) -> list[str]:
    links = _get(page, "links", None)
    if links is None:
        analysis = _page_analysis(page)
        if isinstance(analysis, dict):
            media = analysis.get("media") or {}
            links = media.get("links") if isinstance(media, dict) else None
        else:
            media = getattr(analysis, "media", None)
            links = getattr(media, "links", None) if media is not None else None
    return [str(item) for item in links or []]


def _page_network(page: Any) -> list[Any]:
    network = _get(page, "network", None)
    if isinstance(network, list):
        return network
    return []


def _page_media_urls(page: Any) -> list[str]:
    media = _get(page, "media", None)
    urls: list[str] = []
    if isinstance(media, dict):
        for values in media.values():
            if isinstance(values, list):
                urls.extend(str(item) for item in values)
    elif media is not None and hasattr(media, "all_urls"):
        urls.extend(str(item) for item in media.all_urls())
    return urls


def _analysis_endpoints(analysis: Any) -> list[Any]:
    if not analysis:
        return []
    if isinstance(analysis, dict):
        return analysis.get("api_endpoints") or []
    return getattr(analysis, "api_endpoints", None) or []


def _build_param_bank(pages: list[Any], config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    max_keys = int(config.get("max_param_keys", 100))
    max_values = int(config.get("max_values_per_param", 50))
    min_length = int(config.get("min_value_length", 1))
    bank: dict[str, dict[str, Any]] = {}

    for page in pages:
        url = _page_url(page)
        if not url:
            continue
        hints = collect_page_param_hints(
            url,
            _page_analysis(page),
            links=_page_links(page),
            storage=_get(page, "storage", None),
            network=_page_network(page),
            media_urls=_page_media_urls(page),
            max_values=max_values,
            max_keys=max_keys,
        )
        for key, values in hints.items():
            norm = _normalize_key(key)
            if _is_excluded(norm, config):
                continue
            bucket = bank.get(norm)
            if bucket is None:
                if len(bank) >= max_keys:
                    continue
                bucket = {
                    "key": key,
                    "values": Counter(),
                    "value_sources": defaultdict(set),
                    "count": 0,
                }
                bank[norm] = bucket
            for value in values:
                text = str(value).strip()
                if len(text) < min_length:
                    continue
                bucket["values"][text] += 1
                bucket["value_sources"][text].add(url)
                bucket["count"] += 1
    return bank


def _related_urls(spec: ApiSpec, pages: list[Any]) -> set[str]:
    related: set[str] = set()
    spec_base = _url_base(spec.url)
    for page in pages:
        page_url = _page_url(page)
        if not page_url:
            continue
        for endpoint in _analysis_endpoints(_page_analysis(page)):
            endpoint_url = (
                endpoint.get("url") if isinstance(endpoint, dict) else getattr(endpoint, "url", None)
            )
            if not endpoint_url:
                continue
            resolved = urllib.parse.urljoin(page_url, str(endpoint_url))
            if _url_base(resolved) == spec_base:
                related.add(page_url)
                break
    return related


def _spec_param_key(spec: ApiSpec, norm: str) -> str | None:
    for key in (spec.params or {}):
        if _normalize_key(str(key)) == norm:
            return str(key)
    return None


def _spec_param_values(spec: ApiSpec, key: str | None) -> list[str]:
    if key is None:
        return []
    values: list[str] = []
    for value in _as_list((spec.params or {}).get(key)):
        values.append(str(value))
    return values


def _path_uses_key(spec: ApiSpec, norm: str, bucket: dict[str, Any]) -> bool:
    if "{" in spec.url:
        return False
    path_parts = urllib.parse.urlsplit(spec.url).path.split("/")
    values = set(bucket["values"])
    return any(part in values for part in path_parts)


def _candidate_values_for_spec(
    spec: ApiSpec,
    norm: str,
    bucket: dict[str, Any],
    related: set[str],
    config: dict[str, Any],
) -> list[str]:
    scope = str(config.get("scope", "related_then_global"))
    key = _spec_param_key(spec, norm)
    existing = _spec_param_values(spec, key)
    if key is not None and not config.get("expand_existing", True):
        return []

    selected: dict[str, int] = {}
    for value, count in bucket["values"].items():
        sources = bucket["value_sources"].get(value, set())
        if scope == "global" or (sources & related):
            selected[value] = count
    if not selected and scope == "related_then_global":
        selected = {value: count for value, count in bucket["values"].items()}
    if config.get("expand_existing", True):
        for value in existing:
            selected.setdefault(value, 10**9)

    ordered = sorted(selected.items(), key=lambda item: (-item[1], item[0]))
    values = [value for value, _count in ordered]
    return values[: int(config.get("max_values_per_param", 10))]


def _mapped_params(spec: ApiSpec, config: dict[str, Any]) -> dict[str, list[str]]:
    mapped: dict[str, list[str]] = {}
    for rule in config.get("param_map") or []:
        match = str(rule.get("match", "") or "")
        if not match:
            continue
        try:
            if re.search(match, spec.url) is None:
                continue
        except re.error:
            if match not in spec.url:
                continue
        for key, value in (rule.get("params") or {}).items():
            values = mapped.setdefault(str(key), [])
            for item in _as_list(value):
                text = str(item)
                if text not in values:
                    values.append(text)
    return mapped


def _path_matches(spec: ApiSpec, pages: list[Any], config: dict[str, Any]) -> list[dict[str, str]]:
    if not config.get("include_path_placeholders", True) or "{" not in spec.url:
        return []
    spec_parts = urllib.parse.urlsplit(spec.url).path.split("/")
    spec_host = urllib.parse.urlsplit(spec.url).netloc.lower()
    matches: list[dict[str, str]] = []
    for page in pages:
        page_url = _page_url(page)
        if not page_url:
            continue
        parts = urllib.parse.urlsplit(page_url)
        if parts.netloc.lower() != spec_host:
            continue
        page_parts = parts.path.split("/")
        if len(page_parts) != len(spec_parts):
            continue
        fill: dict[str, str] = {}
        for spec_part, page_part in zip(spec_parts, page_parts, strict=False):
            if spec_part.startswith("{") and spec_part.endswith("}") and page_part:
                fill[spec_part[1:-1]] = page_part
        if fill and fill not in matches:
            matches.append(fill)
    return matches[: int(config.get("max_path_values", 50))]


def _fill_template(url: str, values: dict[str, str]) -> str:
    filled = url
    for key, value in values.items():
        filled = filled.replace("{" + key + "}", value)
    return filled


def _record_endpoint(
    method: str,
    url: str,
    page_url: str,
    source: str,
) -> dict[str, Any]:
    base_url = _url_base(url)
    return {
        "method": str(method or "GET").upper(),
        "url": base_url,
        "params": _query_params(url),
        "page_url": page_url,
        "source": source,
        "body": None,
        "content_type": None,
    }


def _endpoint_records_from_pages(pages: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for page in pages:
        page_url = _page_url(page)
        if not page_url:
            continue
        analysis = _page_analysis(page)
        for endpoint in _analysis_endpoints(analysis):
            method = (
                endpoint.get("method") if isinstance(endpoint, dict) else getattr(endpoint, "method", "GET")
            )
            endpoint_url = (
                endpoint.get("url") if isinstance(endpoint, dict) else getattr(endpoint, "url", None)
            )
            source = (
                endpoint.get("source") if isinstance(endpoint, dict) else getattr(endpoint, "source", "static")
            )
            if not endpoint_url:
                continue
            resolved = urllib.parse.urljoin(page_url, str(endpoint_url))
            record = _record_endpoint(str(method), resolved, page_url, str(source or "static"))
            endpoint_params = (
                endpoint.get("params") if isinstance(endpoint, dict) else getattr(endpoint, "params", None)
            )
            if isinstance(endpoint_params, dict):
                record["params"].update(endpoint_params)
            record["body"] = (
                endpoint.get("body") if isinstance(endpoint, dict) else getattr(endpoint, "body", None)
            )
            record["content_type"] = (
                endpoint.get("content_type")
                if isinstance(endpoint, dict)
                else getattr(endpoint, "content_type", None)
            )
            key = (record["method"], record["url"], page_url)
            if key not in seen:
                seen.add(key)
                records.append(record)

        network = _get(page, "network", None)
        if not network:
            continue
        from api_client import build_api_specs

        for spec in build_api_specs(page):
            record = _record_endpoint(spec.method, spec.url, page_url, spec.source)
            record["params"] = dict(spec.params or {})
            record["body"] = spec.body
            record["content_type"] = spec.content_type
            key = (record["method"], record["url"], page_url)
            if key not in seen:
                seen.add(key)
                records.append(record)
    return records


def _spec_records(specs: list[ApiSpec]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for spec in specs:
        record = _record_endpoint(spec.method, spec.url, "", spec.source)
        record["params"] = dict(spec.params or {})
        record["body"] = spec.body
        record["content_type"] = spec.content_type
        records.append(record)
    return records


def _infer_segment_name(
    values: list[str],
    bank: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> str | None:
    value_set = set(values)
    if value_set and all(value.isdigit() for value in value_set):
        id_bucket = bank.get("id")
        if id_bucket and value_set.issubset(set(id_bucket["values"])):
            return id_bucket["key"]
    ranked = sorted(
        bank.items(),
        key=lambda item: (-item[1]["count"], item[0]),
    )
    for norm, bucket in ranked:
        if _is_excluded(norm, config) or _is_pagination(norm):
            continue
        if len(norm) >= 2 and value_set.issubset(set(bucket["values"])):
            return bucket["key"]
    return None


def _infer_templates(
    records: list[dict[str, Any]],
    bank: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    if not config.get("infer_path_templates", True):
        return []
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        parts = urllib.parse.urlsplit(record["url"])
        if parts.scheme not in {"http", "https"} or "{" in parts.path:
            continue
        groups[(record["method"], parts.netloc.lower(), len(parts.path.split("/")))].append(record)

    templates: list[dict[str, Any]] = []
    for (_method, _host, _length), items in groups.items():
        unique = {record["url"] for record in items}
        if len(unique) < 2:
            continue
        paths = [urllib.parse.urlsplit(url).path.split("/") for url in unique]
        if any(len(path) != len(paths[0]) for path in paths):
            continue
        variable_positions = [
            index
            for index in range(len(paths[0]))
            if len({path[index] for path in paths}) > 1
        ]
        if not variable_positions:
            continue

        name_by_position: dict[int, str] = {}
        used_names: set[str] = set()
        for position in variable_positions:
            values = sorted({path[position] for path in paths})
            name = _infer_segment_name(values, bank, config)
            if not name:
                name = f"path{position}"
            base_name = name
            suffix = 2
            while name in used_names:
                name = f"{base_name}{suffix}"
                suffix += 1
            used_names.add(name)
            name_by_position[position] = name

        template_segments = []
        for index, segment in enumerate(paths[0]):
            if index in name_by_position:
                template_segments.append("{" + name_by_position[index] + "}")
            else:
                template_segments.append(segment)
        sample = items[0]["url"]
        parts = urllib.parse.urlsplit(sample)
        if template_segments and template_segments[0] == "":
            template_path = "/" + "/".join(template_segments[1:])
        else:
            template_path = "/" + "/".join(template_segments)
        template_url = urllib.parse.urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                template_path,
                "",
                "",
            )
        )
        values: list[dict[str, Any]] = []
        for record in items:
            path_parts = urllib.parse.urlsplit(record["url"]).path.split("/")
            fill = {
                name_by_position[index]: path_parts[index]
                for index in name_by_position
            }
            values.append(
                {
                    "url": record["url"],
                    "params": dict(record["params"] or {}),
                    "fill": fill,
                    "body": record.get("body"),
                    "content_type": record.get("content_type"),
                }
            )
        templates.append(
            {
                "method": _method,
                "template_url": template_url,
                "placeholders": [name_by_position[index] for index in variable_positions],
                "values": values,
            }
        )
        if len(templates) >= int(config.get("max_templates", 20)):
            break
    return templates


def _template_expansion_specs(
    specs: list[ApiSpec],
    pages: list[Any],
    bank: dict[str, dict[str, Any]],
    config: dict[str, Any],
) -> list[ApiSpec]:
    records = _spec_records(specs) + _endpoint_records_from_pages(pages)
    expanded: list[ApiSpec] = []
    for template in _infer_templates(records, bank, config):
        for value in template["values"]:
            url = _fill_template(template["template_url"], value["fill"])
            expanded.append(
                ApiSpec(
                    method=template["method"],
                    url=url,
                    params=dict(value["params"] or {}) or None,
                    body=value.get("body"),
                    source="inferred-template",
                    content_type=value.get("content_type"),
                )
            )
    return expanded


def discover_specs_from_pages(
    pages: list[Any],
    config: dict[str, Any] | None = None,
) -> list[ApiSpec]:
    """Turn every page/subpage/API response endpoint into replayable specs."""

    cfg = dict(_DEFAULTS)
    cfg.update(config or {})
    specs: list[ApiSpec] = []
    seen: set[tuple[str, str, str]] = set()
    for record in _endpoint_records_from_pages(pages):
        spec = ApiSpec(
            method=record["method"],
            url=record["url"],
            params=dict(record["params"] or {}) or None,
            body=record.get("body"),
            source=record["source"],
            content_type=record.get("content_type"),
        )
        key = _spec_key(spec)
        if key in seen:
            continue
        seen.add(key)
        specs.append(spec)
        if len(specs) >= int(cfg.get("site_index_max_endpoints", 500)):
            break
    return specs


def _product_variants(candidates: dict[str, list[str]], config: dict[str, Any]) -> list[dict[str, str]]:
    if not candidates:
        return []
    ordered_keys = sorted(
        candidates,
        key=lambda key: (-len(candidates[key]), key),
    )
    value_lists = [candidates[key] for key in ordered_keys]
    variants: list[dict[str, str]] = []
    for combo in itertools.product(*value_lists):
        if len(variants) >= int(config.get("max_variants", 100)):
            break
        variants.append(dict(zip(ordered_keys, combo, strict=False)))
    return variants


def _copy_spec(spec: ApiSpec) -> ApiSpec:
    return ApiSpec(
        method=spec.method,
        url=spec.url,
        name=spec.name,
        headers=dict(spec.headers) if spec.headers else None,
        params=dict(spec.params) if spec.params else None,
        body=copy.deepcopy(spec.body),
        source=spec.source,
        pagination=dict(spec.pagination) if spec.pagination else None,
        content_type=spec.content_type,
    )


def _with_params(spec: ApiSpec, params: dict[str, Any], url: str | None = None) -> ApiSpec:
    updated = _copy_spec(spec)
    if url is not None:
        updated.url = url
    updated.params = dict(params or {})
    return updated


def _spec_key(spec: ApiSpec) -> tuple[str, str, str]:
    params = spec.params or {}
    canonical = json.dumps(
        {str(key): params[key] for key in sorted(params)},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    body = (
        json.dumps(spec.body, sort_keys=True, ensure_ascii=False, default=str)
        if spec.body is not None
        else ""
    )
    return (spec.method.upper(), spec.url, f"{canonical}|{body}")


def _expansions_for_spec(
    spec: ApiSpec,
    bank: dict[str, dict[str, Any]],
    pages: list[Any],
    related: set[str],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: dict[str, list[str]] = {}
    for norm, bucket in bank.items():
        if _is_excluded(norm, config):
            continue
        if _path_uses_key(spec, norm, bucket) and _spec_param_key(spec, norm) is None:
            continue
        values = _candidate_values_for_spec(spec, norm, bucket, related, config)
        if values and (len(values) > 1 or _spec_param_key(spec, norm) is None):
            candidates[bucket["key"]] = values
    mapped = _mapped_params(spec, config)
    for key, values in mapped.items():
        candidates[key] = values

    path_matches = _path_matches(spec, pages, config)
    variants: list[dict[str, Any]] = []
    if path_matches:
        for fill in path_matches:
            url = _fill_template(spec.url, fill)
            for combo in _product_variants(candidates, config) or [{}]:
                params = dict(spec.params or {})
                params.update(combo)
                variants.append({"url": url, "params": params})
                if len(variants) >= int(config.get("max_variants", 100)):
                    break
    else:
        for combo in _product_variants(candidates, config):
            params = dict(spec.params or {})
            params.update(combo)
            variants.append({"url": spec.url, "params": params})
    return variants


def augment_specs(
    specs: list[ApiSpec],
    pages: list[Any],
    config: dict[str, Any] | None = None,
) -> tuple[list[ApiSpec], AugmentationStats]:
    """Expand API specs with parameter values harvested from subpages."""

    cfg = dict(_DEFAULTS)
    cfg.update(config or {})
    bank = _build_param_bank(pages, cfg)
    stats = AugmentationStats(
        specs_input=len(specs),
        harvested_values=sum(bucket["count"] for bucket in bank.values()),
    )
    out: list[ApiSpec] = []
    seen: set[tuple[str, str, str]] = set()

    for spec in specs:
        if not cfg.get("enabled", True):
            key = _spec_key(spec)
            if key not in seen:
                seen.add(key)
                out.append(spec)
                stats.specs_output += 1
            continue

        original = _copy_spec(spec)
        key = _spec_key(original)
        if key in seen:
            continue
        seen.add(key)
        out.append(original)
        stats.specs_output += 1

        related = _related_urls(spec, pages)
        stats.related_pages = max(stats.related_pages, len(related))
        added_keys_this: set[str] = set()
        for variant in _expansions_for_spec(spec, bank, pages, related, cfg):
            new_spec = _with_params(spec, variant["params"], url=variant["url"])
            new_key = _spec_key(new_spec)
            if new_key in seen:
                continue
            if len(out) >= int(cfg.get("max_specs", 500)):
                break
            for param_key in variant["params"]:
                norm = _normalize_key(str(param_key))
                original_key = _spec_param_key(spec, norm)
                original_values = set(_spec_param_values(spec, original_key))
                new_values = set(_as_list(variant["params"][param_key]))
                if not new_values.issubset(original_values):
                    added_keys_this.add(str(param_key))
            seen.add(new_key)
            out.append(new_spec)
            stats.specs_output += 1
            stats.variants += 1
        stats.added_keys += len(added_keys_this)

    if cfg.get("enabled", True) and cfg.get("infer_path_templates", True):
        records = _spec_records(specs) + _endpoint_records_from_pages(pages)
        templates = _infer_templates(records, bank, cfg)
        stats.templates = len(templates)
        for template_spec in _template_expansion_specs(specs, pages, bank, cfg):
            new_key = _spec_key(template_spec)
            if new_key in seen:
                continue
            if len(out) >= int(cfg.get("max_specs", 500)):
                break
            seen.add(new_key)
            out.append(template_spec)
            stats.specs_output += 1
            stats.variants += 1
            related = _related_urls(template_spec, pages)
            for variant in _expansions_for_spec(template_spec, bank, pages, related, cfg):
                new_variant = _with_params(template_spec, variant["params"], url=variant["url"])
                variant_key = _spec_key(new_variant)
                if variant_key in seen:
                    continue
                if len(out) >= int(cfg.get("max_specs", 500)):
                    break
                for param_key in variant["params"]:
                    norm = _normalize_key(str(param_key))
                    original_key = _spec_param_key(template_spec, norm)
                    original_values = set(_spec_param_values(template_spec, original_key))
                    new_values = set(_as_list(variant["params"][param_key]))
                    if not new_values.issubset(original_values):
                        stats.added_keys += 1
                seen.add(variant_key)
                out.append(new_variant)
                stats.specs_output += 1
                stats.variants += 1

    return out, stats


def build_site_api_index(
    pages: list[Any],
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a whole-site API index from every crawled page and subpage."""

    cfg = dict(_DEFAULTS)
    cfg.update(config or {})
    bank = _build_param_bank(pages, cfg)
    records = _endpoint_records_from_pages(pages)

    aggregated: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (record["method"], record["url"])
        item = aggregated.setdefault(
            key,
            {
                "method": record["method"],
                "url": record["url"],
                "page_urls": set(),
                "params": defaultdict(set),
                "sources": set(),
                "body": record.get("body"),
                "content_type": record.get("content_type"),
            },
        )
        if record["page_url"]:
            item["page_urls"].add(record["page_url"])
        item["sources"].add(record["source"])
        for param_key, values in (record["params"] or {}).items():
            for value in _as_list(values):
                item["params"][str(param_key)].add(str(value))

    endpoints: list[dict[str, Any]] = []
    for (method, url), item in aggregated.items():
        spec = ApiSpec(
            method=method,
            url=url,
            params={key: sorted(values) for key, values in item["params"].items()},
        )
        related = _related_urls(spec, pages)
        params: dict[str, list[str]] = {
            key: sorted(values) for key, values in item["params"].items()
        }
        for norm, bucket in bank.items():
            if _is_excluded(norm, cfg):
                continue
            if _path_uses_key(spec, norm, bucket) and _spec_param_key(spec, norm) is None:
                continue
            values = _candidate_values_for_spec(spec, norm, bucket, related, cfg)
            if not values:
                continue
            existing = params.setdefault(bucket["key"], [])
            for value in values:
                if value not in existing:
                    existing.append(value)
        endpoints.append(
            {
                "method": method,
                "url": url,
                "source": sorted(item["sources"]),
                "page_urls": sorted(item["page_urls"]),
                "params": params,
                "body": item.get("body"),
                "content_type": item.get("content_type"),
            }
        )

    templates = _infer_templates(records, bank, cfg)
    page_index: list[dict[str, Any]] = []
    for page in pages:
        page_url = _page_url(page)
        if not page_url:
            continue
        hints = collect_page_param_hints(
            page_url,
            _page_analysis(page),
            links=_page_links(page),
            storage=_get(page, "storage", None),
            max_values=int(cfg.get("max_values_per_param", 10)),
            max_keys=int(cfg.get("max_param_keys", 100)),
        )
        page_index.append(
            {
                "url": page_url,
                "api_params": hints,
                "endpoint_count": sum(
                    1 for record in records if record["page_url"] == page_url
                ),
            }
        )

    param_bank: dict[str, list[str]] = {}
    for bucket in bank.values():
        param_bank[bucket["key"]] = [
            value
            for value, _count in bucket["values"].most_common(
                int(cfg.get("max_values_per_param", 10))
            )
        ]

    endpoint_variants = 0
    for endpoint in endpoints:
        endpoint_variants += (
            len(_product_variants(endpoint["params"], cfg))
            or 1
        )
    template_variants = sum(len(template["values"]) for template in templates)
    summary = {
        "pages": len(page_index),
        "endpoints": len(endpoints),
        "endpoint_pages": sum(len(endpoint["page_urls"]) for endpoint in endpoints),
        "templates": len(templates),
        "param_keys": len(param_bank),
        "param_values": sum(len(values) for values in param_bank.values()),
        "variants": endpoint_variants + template_variants,
    }
    return {
        "summary": summary,
        "pages": page_index,
        "endpoints": endpoints,
        "templates": templates,
        "param_bank": param_bank,
    }


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _self_test() -> None:
    pages = [
        {
            "url": "https://example.com/sub/item/1",
            "links": [],
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/sub-data?id=1",
                        "source": "fetch",
                    }
                ],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [],
            },
        },
        {
            "url": "https://example.com/sub/item/2",
            "links": [],
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/sub-data?id=2",
                        "source": "fetch",
                    }
                ],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [],
            },
        },
        {
            "url": "https://example.com/list?category=books",
            "links": [],
            "analysis": {
                "api_endpoints": [],
                "json_api_fields": [{"key": "author", "value": "jane"}],
                "pagination": {},
                "form_fields": [{"name": "q", "value": "fantasy"}],
                "embedded_json": [],
            },
        },
    ]
    specs = [
        ApiSpec(
            method="GET",
            url="https://example.com/api/sub-data",
            params={"id": "1"},
        )
    ]
    output, stats = augment_specs(specs, pages, {"max_variants": 20})
    ids = [spec.params.get("id") for spec in output if spec.params]
    assert "2" in ids, ids
    assert stats.variants >= 1, stats
    assert stats.added_keys >= 1, stats
    print("param_augmenter self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Augment API specs with parameters harvested from crawled subpages."
    )
    parser.add_argument("--specs", default=None, help="JSON file containing ApiSpec objects")
    parser.add_argument("--pages", action="append", default=[], help="crawl or PageCapture JSON file")
    parser.add_argument("--config", default=None, help="optional JSON augment config")
    parser.add_argument("--output", default=None, help="write augmented ApiSpec JSON")
    parser.add_argument("--site-index", default=None, help="write whole-site API index JSON")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.specs and not args.site_index:
        parser.error("--specs or --site-index is required unless --self-test is used")

    pages: list[Any] = []
    for path in args.pages:
        loaded = _load_json(path)
        if isinstance(loaded, dict) and "pages" in loaded:
            pages.extend(loaded["pages"])
        elif isinstance(loaded, list):
            pages.extend(loaded)
        else:
            pages.append(loaded)
    config = _load_json(args.config) if args.config else None
    if args.site_index:
        index = build_site_api_index(pages, config)
        Path(args.site_index).write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps(index["summary"], ensure_ascii=False, indent=2))
        return 0

    data = _load_json(args.specs)
    specs = [ApiSpec.from_dict(item) for item in (data if isinstance(data, list) else data.get("specs", []))]
    output, stats = augment_specs(specs, pages, config)
    if args.output:
        Path(args.output).write_text(
            json.dumps([spec.to_dict() for spec in output], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
