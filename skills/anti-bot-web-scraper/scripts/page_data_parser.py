"""Deep page parsing for the media acquisition pipeline.

Extracts page metadata, embedded JSON state (JSON-LD, Next.js, Nuxt,
application/json), API endpoints from scripts/forms/preloads, media URLs
inside embedded JSON, pagination fields, and API-like data fields.
Standard-library only; Playwright stays optional in browser_session.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from captcha_solver import CaptchaChallenge, detect_captchas
from login_detector import LoginDetection, detect_login
from media_parser import MediaExtraction, extract_media_urls, normalize_url

_MAX_SCRIPT_BYTES = 8 * 1024 * 1024
_MAX_JSON_DEPTH = 40
_MAX_ENDPOINTS = 300
_MAX_API_FIELDS = 300
_MAX_LINKS = 2000
_MAX_PAGINATION_PER_KEY = 20


@dataclass
class PageMetadata:
    title: str | None = None
    description: str | None = None
    keywords: str | None = None
    author: str | None = None
    robots: str | None = None
    generator: str | None = None
    canonical: str | None = None
    base_url: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    og_url: str | None = None
    og_type: str | None = None
    og_site_name: str | None = None
    twitter_title: str | None = None
    twitter_description: str | None = None
    twitter_image: str | None = None
    language: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "title": self.title,
            "description": self.description,
            "keywords": self.keywords,
            "author": self.author,
            "robots": self.robots,
            "generator": self.generator,
            "canonical": self.canonical,
            "base_url": self.base_url,
            "og_title": self.og_title,
            "og_description": self.og_description,
            "og_image": self.og_image,
            "og_url": self.og_url,
            "og_type": self.og_type,
            "og_site_name": self.og_site_name,
            "twitter_title": self.twitter_title,
            "twitter_description": self.twitter_description,
            "twitter_image": self.twitter_image,
            "language": self.language,
        }


@dataclass
class EmbeddedJson:
    kind: str
    name: str | None
    data: Any
    size_bytes: int
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "size_bytes": self.size_bytes,
            "data": self.data if self.parse_error is None else None,
            "parse_error": self.parse_error,
        }


@dataclass
class ApiEndpoint:
    method: str
    url: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {"method": self.method, "url": self.url, "source": self.source}


@dataclass
class ApiField:
    path: str
    key: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "key": self.key, "value": self.value}


@dataclass
class PageDataAnalysis:
    url: str | None = None
    metadata: PageMetadata = field(default_factory=PageMetadata)
    media: MediaExtraction = field(default_factory=MediaExtraction)
    embedded_json: list[EmbeddedJson] = field(default_factory=list)
    json_media: MediaExtraction = field(default_factory=MediaExtraction)
    json_api_fields: list[ApiField] = field(default_factory=list)
    api_endpoints: list[ApiEndpoint] = field(default_factory=list)
    pagination: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    captchas: list[CaptchaChallenge] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    login: LoginDetection | None = None

    def to_dict(self, include_data: bool = True) -> dict[str, Any]:
        return {
            "url": self.url,
            "metadata": self.metadata.to_dict(),
            "media": _media_lists(self.media),
            "links": list(self.links[:_MAX_LINKS]),
            "embedded_json": [
                item.to_dict() if include_data else _json_block_summary(item)
                for item in self.embedded_json
            ],
            "json_media": _media_lists(self.json_media),
            "json_api_fields": [item.to_dict() for item in self.json_api_fields],
            "api_endpoints": [item.to_dict() for item in self.api_endpoints],
            "pagination": self.pagination,
            "captchas": [item.to_dict() for item in self.captchas],
            "login": self.login.to_dict() if self.login else None,
        }

    def summary(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "metadata": self.metadata.to_dict(),
            "media": _media_counts(self.media),
            "links": list(self.links[:_MAX_LINKS]),
            "json_media": _media_counts(self.json_media),
            "embedded_json": [_json_block_summary(item) for item in self.embedded_json],
            "api_endpoints": [item.to_dict() for item in self.api_endpoints[:_MAX_ENDPOINTS]],
            "json_api_fields": [item.to_dict() for item in self.json_api_fields[:_MAX_API_FIELDS]],
            "pagination": {
                key: values[:_MAX_PAGINATION_PER_KEY] for key, values in self.pagination.items()
            },
            "captchas": [item.to_dict() for item in self.captchas],
            "login": self.login.to_dict() if self.login else None,
        }


class _PageHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.html_lang: str | None = None
        self.base_href: str | None = None
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.links: list[tuple[str, str]] = []
        self.forms: list[tuple[str, str]] = []
        self.script_srcs: list[str] = []
        self.script_blocks: list[tuple[str | None, str | None, str]] = []
        self._script_id: str | None = None
        self._script_type: str | None = None
        self._script_text: list[str] = []
        self._in_script = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "html":
            self.html_lang = attr_map.get("lang") or None
        elif tag == "base":
            href = attr_map.get("href", "").strip()
            if href:
                self.base_href = href
        elif tag == "meta":
            key = (attr_map.get("name") or attr_map.get("property") or "").strip().lower()
            content = attr_map.get("content", "").strip()
            if key and content:
                self.meta[key] = content
        elif tag == "link":
            rel = (attr_map.get("rel") or "").strip().lower()
            href = (attr_map.get("href") or "").strip()
            if rel and href:
                self.links.append((rel, href))
        elif tag == "form":
            method = (attr_map.get("method") or "GET").strip().upper() or "GET"
            action = (attr_map.get("action") or "").strip()
            if action:
                self.forms.append((method, action))
        elif tag == "script":
            src = (attr_map.get("src") or "").strip()
            if src:
                self.script_srcs.append(src)
            self._script_id = attr_map.get("id") or None
            self._script_type = attr_map.get("type") or None
            self._script_text = []
            self._in_script = True
        elif tag == "title":
            self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_text.append(data)
        elif self._in_title:
            self.title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._in_script:
            text = "".join(self._script_text)
            self.script_blocks.append((self._script_id, self._script_type, text))
            self._in_script = False
            self._script_id = None
            self._script_type = None
        elif tag == "title":
            self._in_title = False


_GLOBAL_STATE_PATTERNS = (
    (r"(?:window\.)?__NEXT_DATA__\s*=\s*", "next-data", "__NEXT_DATA__"),
    (r"(?:window\.)?__NUXT__\s*=\s*", "nuxt-data", "__NUXT__"),
    (r"(?:window\.)?__INITIAL_STATE__\s*=\s*", "global-state", "__INITIAL_STATE__"),
    (r"(?:window\.)?__PRELOADED_STATE__\s*=\s*", "global-state", "__PRELOADED_STATE__"),
    (r"(?:window\.)?__APOLLO_STATE__\s*=\s*", "global-state", "__APOLLO_STATE__"),
    (r"(?:window\.)?__APP_DATA__\s*=\s*", "global-state", "__APP_DATA__"),
    (r"(?:window\.)?__INITIAL_DATA__\s*=\s*", "global-state", "__INITIAL_DATA__"),
)

_FETCH_RE = re.compile(
    r"\bfetch\s*\(\s*(?P<quote>[\"'`])(?P<url>[^\"'`]+)(?P=quote)" r"(?P<opts>\s*,\s*\{[^}]*\})?",
    re.IGNORECASE,
)
_AXIOS_RE = re.compile(
    r"\baxios\s*\.\s*(?P<method>get|post|put|patch|delete|head|options|request)"
    r"\s*\(\s*(?P<quote>[\"'`])(?P<url>[^\"'`]+)(?P=quote)",
    re.IGNORECASE,
)
_XHR_RE = re.compile(
    r"\.open\s*\(\s*(?P<q1>[\"'])(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"
    r"(?P=q1)\s*,\s*(?P<q2>[\"'`])(?P<url>[^\"'`]+)(?P=q2)",
    re.IGNORECASE,
)
_JQUERY_RE = re.compile(
    r"\$\s*\.\s*ajax\s*\(\s*\{[^}]*?url\s*:\s*(?P<quote>[\"'`])" r"(?P<url>[^\"'`]+)(?P=quote)",
    re.IGNORECASE,
)
_HTTP_RE = re.compile(
    r"\bhttp\s*\.\s*(?P<method>get|post|put|patch|delete|head|options|request)"
    r"\s*\(\s*(?P<quote>[\"'`])(?P<url>[^\"'`]+)(?P=quote)",
    re.IGNORECASE,
)
_WEBSOCKET_RE = re.compile(
    r"new\s+WebSocket\s*\(\s*(?P<quote>[\"'`])(?P<url>[^\"'`]+)(?P=quote)",
    re.IGNORECASE,
)
_METHOD_IN_OPTIONS_RE = re.compile(
    r"method\s*:\s*(?P<quote>[\"'])(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"
    r"(?P=quote)",
    re.IGNORECASE,
)
_JQUERY_METHOD_RE = re.compile(
    r"(?:type|method)\s*:\s*(?P<quote>[\"'])"
    r"(?P<method>GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)(?P=quote)",
    re.IGNORECASE,
)
_UNDEFINED_RE = re.compile(r"(?<![\w\"'])undefined(?![\w\"'])")


def _loads_json(text: str) -> Any:
    candidate = re.sub(r";\s*$", "", text.strip()).strip()
    candidate = _UNDEFINED_RE.sub("null", candidate)
    return json.loads(candidate)


def _block_signature(block: EmbeddedJson) -> tuple[str, str | None, str]:
    if block.parse_error:
        return (block.kind, block.name, "parse-error")
    try:
        payload = json.dumps(block.data, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        payload = repr(block.data)[:2000]
    return (block.kind, block.name, payload)


def _append_unique(
    found: list[EmbeddedJson],
    seen: set[tuple[str, str | None, str]],
    block: EmbeddedJson,
) -> None:
    key = _block_signature(block)
    if key in seen:
        return
    seen.add(key)
    found.append(block)


def _make_json_block(kind: str, name: str | None, text: str) -> EmbeddedJson:
    size = len(text)
    if size > _MAX_SCRIPT_BYTES:
        return EmbeddedJson(
            kind=kind,
            name=name,
            data=None,
            size_bytes=size,
            parse_error="script exceeds max size",
        )
    try:
        data = _loads_json(text)
    except json.JSONDecodeError as exc:
        return EmbeddedJson(kind=kind, name=name, data=None, size_bytes=size, parse_error=str(exc))
    return EmbeddedJson(kind=kind, name=name, data=data, size_bytes=size)


def _extract_embedded_from_parser(parser: _PageHTMLParser) -> list[EmbeddedJson]:
    found: list[EmbeddedJson] = []
    seen: set[tuple[str, str | None, str]] = set()
    for script_id, script_type, text in parser.script_blocks:
        text = text.strip()
        if not text:
            continue
        stype = (script_type or "").strip().lower()
        if stype.startswith("application/ld+json"):
            block = _make_json_block("json-ld", script_id or None, text)
            _append_unique(found, seen, block)
            continue
        if stype.startswith("application/json"):
            block = _make_json_block("application-json", script_id or None, text)
            _append_unique(found, seen, block)
            continue
        for pattern, kind, var_name in _GLOBAL_STATE_PATTERNS:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                candidate = text[match.end() :]
                block = _make_json_block(kind, script_id or var_name, candidate)
                if block.parse_error is None:
                    _append_unique(found, seen, block)
    return found


def _effective_base(parser: _PageHTMLParser, base_url: str | None) -> str | None:
    if parser.base_href:
        return normalize_url(parser.base_href, base_url)
    return base_url


def _resolve_url(value: str | None, base: str | None) -> str | None:
    if not value:
        return None
    return normalize_url(value, base)


def _build_metadata(
    parser: _PageHTMLParser,
    base_url: str | None,
    effective_base: str | None,
) -> PageMetadata:
    meta = parser.meta
    canonical = next(
        (href for rel, href in parser.links if rel == "canonical"),
        None,
    )
    return PageMetadata(
        title=" ".join(part.strip() for part in parser.title_parts if part.strip()) or None,
        description=meta.get("description"),
        keywords=meta.get("keywords"),
        author=meta.get("author"),
        robots=meta.get("robots"),
        generator=meta.get("generator"),
        canonical=_resolve_url(canonical, effective_base),
        base_url=effective_base or base_url,
        og_title=meta.get("og:title"),
        og_description=meta.get("og:description"),
        og_image=_resolve_url(meta.get("og:image"), effective_base),
        og_url=_resolve_url(meta.get("og:url"), effective_base),
        og_type=meta.get("og:type"),
        og_site_name=meta.get("og:site_name"),
        twitter_title=meta.get("twitter:title"),
        twitter_description=meta.get("twitter:description"),
        twitter_image=_resolve_url(meta.get("twitter:image"), effective_base),
        language=parser.html_lang,
    )


def _looks_like_url(value: str) -> bool:
    value = value.strip()
    if value.startswith(("javascript:", "data:", "blob:", "mailto:", "tel:", "about:")):
        return False
    return value.startswith(("http://", "https://", "//", "/", "."))


def _normalize_endpoint_url(url: str, base: str | None) -> str | None:
    value = url.strip()
    if not value or value.startswith("#"):
        return None
    if "${" in value or "{" in value or "}" in value:
        return None
    return normalize_url(value, base)


def _method_from_options(options: str) -> str | None:
    match = _METHOD_IN_OPTIONS_RE.search(options)
    return match.group("method").upper() if match else None


def _jquery_method(block: str) -> str | None:
    match = _JQUERY_METHOD_RE.search(block)
    return match.group("method").upper() if match else None


def _add_js_endpoints(
    script_text: str,
    base: str | None,
    add: Callable[[str, str, str], None],
) -> None:
    for match in _FETCH_RE.finditer(script_text):
        options = match.group("opts") or ""
        add(_method_from_options(options) or "GET", match.group("url"), "fetch")
    for match in _AXIOS_RE.finditer(script_text):
        add(match.group("method").upper(), match.group("url"), "axios")
    for match in _XHR_RE.finditer(script_text):
        add(match.group("method").upper(), match.group("url"), "xhr")
    for match in _JQUERY_RE.finditer(script_text):
        add(_jquery_method(match.group(0)) or "GET", match.group("url"), "ajax")
    for match in _HTTP_RE.finditer(script_text):
        add(match.group("method").upper(), match.group("url"), "http-client")
    for match in _WEBSOCKET_RE.finditer(script_text):
        add("WS", match.group("url"), "websocket")


def _walk_api_fields(
    block: EmbeddedJson,
    base: str | None,
    add: Callable[[str, str, str], None],
) -> None:
    if block.parse_error is not None:
        return

    def walk(value: Any, path: str, depth: int) -> None:
        if depth > _MAX_JSON_DEPTH:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if isinstance(child, str) and _is_api_key(str(key)) and _looks_like_url(child):
                    add("GET", child, "json-data")
                elif not isinstance(child, str):
                    walk(child, child_path, depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]", depth + 1)

    walk(block.data, block.kind, 0)


def _extract_endpoints_from_parser(
    parser: _PageHTMLParser,
    base: str | None,
    embedded_json: list[EmbeddedJson],
) -> list[ApiEndpoint]:
    endpoints: list[ApiEndpoint] = []
    seen: set[tuple[str, str]] = set()

    def add(method: str, url: str, source: str) -> None:
        normalized = _normalize_endpoint_url(url, base)
        if normalized is None:
            return
        key = (method.upper(), normalized)
        if key in seen:
            return
        seen.add(key)
        endpoints.append(ApiEndpoint(method=method.upper(), url=normalized, source=source))

    for src in parser.script_srcs:
        add("GET", src, "script-src")
    for rel, href in parser.links:
        if rel in {"preload", "modulepreload", "preconnect", "dns-prefetch"}:
            add("GET", href, "link")
    for method, action in parser.forms:
        add(method, action, "form")
    for _, _, script_text in parser.script_blocks:
        _add_js_endpoints(script_text, base, add)
    for block in embedded_json:
        if (
            block.parse_error is None
            and isinstance(block.data, dict)
            and (block.kind == "next-data" or block.name == "__NEXT_DATA__")
        ):
            build_id = block.data.get("buildId")
            page = block.data.get("page")
            if build_id and page:
                page_path = page if page.startswith("/") else f"/{page}"
                add("GET", f"/_next/data/{build_id}{page_path}.json", "next-data")
        _walk_api_fields(block, base, add)
    return endpoints


_HLS_KEYS = frozenset({"hls", "m3u8", "playlist", "playlisturl", "playurl"})
_AUDIO_KEYS = frozenset({"audio", "audios", "audiourl", "mp3", "sound", "music", "track", "tracks"})
_VIDEO_KEYS = frozenset(
    {
        "video",
        "videos",
        "videourl",
        "mp4",
        "stream",
        "streams",
        "streamurl",
        "source",
        "sources",
        "src",
        "file",
        "fileurl",
        "media",
        "mediaurl",
        "contenturl",
        "embedurl",
        "downloadurl",
    }
)
_IMAGE_KEYS = frozenset(
    {
        "image",
        "images",
        "imageurl",
        "picture",
        "pictures",
        "pic",
        "thumb",
        "thumbnail",
        "thumbnailurl",
        "cover",
        "coverurl",
        "poster",
        "posterurl",
        "background",
        "backgroundurl",
        "banner",
        "logo",
        "icon",
        "avatar",
        "preview",
        "previewurl",
        "ogimage",
    }
)
_AUDIO_EXTS = (".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".opus", ".wma")
_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".flv", ".ts", ".m4v", ".wmv")
_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif", ".ico")
_API_HINTS = (
    "api",
    "endpoint",
    "baseurl",
    "server",
    "gateway",
    "webhook",
    "callback",
    "upload",
    "auth",
    "token",
    "login",
    "logout",
    "host",
    "domain",
)
_PAGINATION_NAMES = frozenset(
    {
        "page",
        "pagenum",
        "pagenumber",
        "pagesize",
        "current",
        "currentpage",
        "total",
        "totalcount",
        "totalpages",
        "hasmore",
        "hasnext",
        "next",
        "nextpage",
        "nextcursor",
        "cursor",
        "offset",
        "limit",
        "isend",
        "nomore",
        "end",
        "count",
    }
)


def _is_api_key(key: str) -> bool:
    return any(hint in key for hint in _API_HINTS)


def _is_pagination_key(key: str) -> bool:
    if key in _PAGINATION_NAMES:
        return True
    return (
        key.startswith("page")
        or key.endswith("page")
        or key.startswith("total")
        or key.startswith("hasmore")
        or key.startswith("hasnext")
        or key.startswith("next")
        or key.startswith("isend")
        or key.startswith("nomore")
    )


def _classify_json_media(key: str, value: str) -> str | None:
    lower = value.lower()
    if ".m3u8" in lower or key in _HLS_KEYS:
        return "hls"
    if lower.endswith(_AUDIO_EXTS) or key in _AUDIO_KEYS:
        return "audio"
    if lower.endswith(_VIDEO_EXTS) or key in _VIDEO_KEYS:
        return "video"
    if lower.endswith(_IMAGE_EXTS) or key in _IMAGE_KEYS:
        return "image"
    return None


def _append_pagination(
    pagination: dict[str, list[dict[str, Any]]],
    key: str,
    path: str,
    value: Any,
) -> None:
    normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
    bucket = pagination.setdefault(normalized_key, [])
    if len(bucket) >= _MAX_PAGINATION_PER_KEY:
        return
    entry = {"path": path, "key": key, "value": value}
    if entry not in bucket:
        bucket.append(entry)


def _handle_json_string(
    key: str,
    value: str,
    path: str,
    base_url: str | None,
    media: MediaExtraction,
    api_fields: list[ApiField],
    pagination: dict[str, list[dict[str, Any]]],
) -> None:
    key_norm = re.sub(r"[^a-z0-9]", "", key.lower())
    if _is_pagination_key(key_norm):
        _append_pagination(pagination, key, path, value)
    if not _looks_like_url(value):
        return
    normalized = normalize_url(value, base_url)
    category = _classify_json_media(key_norm, value)
    if category == "hls":
        media.hls.append(normalized)
    elif category == "audio":
        media.audios.append(normalized)
    elif category == "video":
        media.videos.append(normalized)
    elif category == "image":
        media.images.append(normalized)
    if _is_api_key(key_norm) and len(api_fields) < _MAX_API_FIELDS:
        api_fields.append(ApiField(path=path, key=key, value=normalized))


def _walk_json_data(
    value: Any,
    path: str,
    base_url: str | None,
    media: MediaExtraction,
    api_fields: list[ApiField],
    pagination: dict[str, list[dict[str, Any]]],
    depth: int,
) -> None:
    if depth > _MAX_JSON_DEPTH:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            key_norm = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if isinstance(child, str):
                _handle_json_string(
                    str(key),
                    child,
                    child_path,
                    base_url,
                    media,
                    api_fields,
                    pagination,
                )
            elif _is_pagination_key(key_norm) and not isinstance(child, dict | list):
                _append_pagination(pagination, str(key), child_path, child)
            elif isinstance(child, dict | list):
                _walk_json_data(
                    child,
                    child_path,
                    base_url,
                    media,
                    api_fields,
                    pagination,
                    depth + 1,
                )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"
            if isinstance(child, str):
                _handle_json_string(
                    "item",
                    child,
                    child_path,
                    base_url,
                    media,
                    api_fields,
                    pagination,
                )
            else:
                _walk_json_data(
                    child,
                    child_path,
                    base_url,
                    media,
                    api_fields,
                    pagination,
                    depth + 1,
                )


def _dedupe_media(extraction: MediaExtraction) -> None:
    seen: set[str] = set()
    for name in ("videos", "audios", "images", "hls", "links"):
        values: list[str] = []
        for url in getattr(extraction, name):
            if url not in seen:
                seen.add(url)
                values.append(url)
        setattr(extraction, name, values)


def _digest_json(
    blocks: list[EmbeddedJson],
    base_url: str | None,
) -> tuple[MediaExtraction, list[ApiField], dict[str, list[dict[str, Any]]]]:
    media = MediaExtraction()
    api_fields: list[ApiField] = []
    pagination: dict[str, list[dict[str, Any]]] = {}
    for block in blocks:
        if block.parse_error is None:
            _walk_json_data(
                block.data,
                block.kind,
                base_url,
                media,
                api_fields,
                pagination,
                0,
            )
    _dedupe_media(media)
    return media, api_fields[:_MAX_API_FIELDS], pagination


def _media_counts(extraction: MediaExtraction) -> dict[str, int]:
    return {
        "videos": len(extraction.videos),
        "audios": len(extraction.audios),
        "images": len(extraction.images),
        "hls": len(extraction.hls),
        "links": len(extraction.links),
    }


def _media_lists(extraction: MediaExtraction) -> dict[str, list[str]]:
    return {
        "videos": list(extraction.videos),
        "audios": list(extraction.audios),
        "images": list(extraction.images),
        "hls": list(extraction.hls),
        "links": list(extraction.links),
    }


def _json_block_summary(item: EmbeddedJson) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "name": item.name,
        "size_bytes": item.size_bytes,
        "parse_error": item.parse_error,
    }


def extract_metadata(html: str, base_url: str | None = None) -> PageMetadata:
    """Return title/meta/canonical/OpenGraph metadata from an HTML page."""
    parser = _PageHTMLParser()
    parser.feed(html)
    return _build_metadata(parser, base_url, _effective_base(parser, base_url))


def extract_embedded_json(html: str) -> list[EmbeddedJson]:
    """Return parsed JSON-LD, application/json, and JS global state blocks."""
    parser = _PageHTMLParser()
    parser.feed(html)
    return _extract_embedded_from_parser(parser)


def extract_api_endpoints(
    html: str,
    base_url: str | None = None,
    embedded_json: list[EmbeddedJson] | None = None,
) -> list[ApiEndpoint]:
    """Return API endpoints from scripts, forms, preloads, and JSON state."""
    parser = _PageHTMLParser()
    parser.feed(html)
    if embedded_json is None:
        embedded_json = _extract_embedded_from_parser(parser)
    return _extract_endpoints_from_parser(parser, _effective_base(parser, base_url), embedded_json)


def analyze_page(html: str, base_url: str | None = None) -> PageDataAnalysis:
    """Deep-parse one page: metadata, media, embedded JSON, APIs, and data."""
    parser = _PageHTMLParser()
    parser.feed(html)
    effective_base = _effective_base(parser, base_url)
    embedded = _extract_embedded_from_parser(parser)
    json_media, json_api_fields, pagination = _digest_json(embedded, effective_base)
    media = extract_media_urls(html, base_url)
    return PageDataAnalysis(
        url=base_url,
        metadata=_build_metadata(parser, base_url, effective_base),
        media=media,
        embedded_json=embedded,
        json_media=json_media,
        json_api_fields=json_api_fields,
        api_endpoints=_extract_endpoints_from_parser(parser, effective_base, embedded),
        pagination=pagination,
        captchas=detect_captchas(html, base_url),
        links=list(media.links),
        login=detect_login(html, base_url),
    )


def main(argv: list[str] | None = None) -> int:
    """Fetch a page and print its deep analysis as JSON."""
    parser = argparse.ArgumentParser(
        description="Analyze a page's data, API endpoints, and CAPTCHAs."
    )
    parser.add_argument("--url", required=True, help="page URL to analyze")
    parser.add_argument("--base-url", default=None, help="override URL resolution base")
    parser.add_argument(
        "--full",
        action="store_true",
        help="include embedded JSON bodies instead of block summaries",
    )
    parser.add_argument("--output", default=None, help="write JSON to a file")
    parser.add_argument("--headers", default=None, help='JSON object, e.g. {"X-Token": "..."}')
    parser.add_argument("--proxy", default=None)
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.0,
        help="minimum seconds between HTTP requests",
    )
    args = parser.parse_args(argv)

    from media_session import MediaSession

    headers = json.loads(args.headers) if args.headers else None
    session = MediaSession(
        headers=headers,
        proxy=args.proxy,
        min_interval=args.min_interval,
    )
    body, _ = session.get_bytes(args.url)
    analysis = analyze_page(
        body.decode("utf-8", "replace"),
        base_url=args.base_url or args.url,
    )
    text = json.dumps(
        analysis.to_dict(include_data=args.full),
        ensure_ascii=False,
        indent=2,
    )
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
