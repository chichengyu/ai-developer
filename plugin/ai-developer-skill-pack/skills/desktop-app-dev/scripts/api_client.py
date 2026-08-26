"""API discovery and data fetching for authorized web automation.

Builds replayable API specs from runtime network capture or static page
analysis, then fetches JSON responses through the rate-limited MediaSession.
Data shaping is intentionally left to data_processor.py so the pipeline can
collect raw records first and process them according to user rules later.
"""

from __future__ import annotations

import argparse
import http.server
import json
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_session import MediaSession
from proxy_pool import ProxyPool
from security_detector import detect_security_mechanisms
from smart_fetch import create_fetch_session

DEFAULT_TIMEOUT = 20.0


@dataclass
class ApiSpec:
    """One replayable API call discovered from a page."""

    method: str
    url: str
    name: str = ""
    headers: dict[str, str] | None = None
    params: dict[str, Any] | None = None
    body: Any = None
    source: str = "captured"
    pagination: dict[str, Any] | None = None
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "name": self.name,
            "headers": self.headers,
            "params": self.params,
            "body": self.body,
            "source": self.source,
            "pagination": self.pagination,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApiSpec:
        return cls(
            method=str(data.get("method", "GET")).upper(),
            url=str(data["url"]),
            name=str(data.get("name", "") or ""),
            headers=dict(data["headers"]) if data.get("headers") else None,
            params=dict(data["params"]) if data.get("params") else None,
            body=data.get("body"),
            source=str(data.get("source", "captured") or "captured"),
            pagination=dict(data["pagination"]) if data.get("pagination") else None,
            content_type=data.get("content_type"),
        )


@dataclass
class ApiFetchResult:
    spec: ApiSpec
    data: Any = None
    error: str | None = None
    pages: int = 1
    status: int | None = None
    headers: dict[str, str] | None = None
    duration_ms: float | None = None
    security: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec": self.spec.to_dict(),
            "data": self.data,
            "error": self.error,
            "pages": self.pages,
            "status": self.status,
            "headers": self.headers,
            "duration_ms": self.duration_ms,
            "security": self.security,
        }


@dataclass
class ApiResponse:
    data: Any
    status: int | None = None
    headers: dict[str, str] | None = None
    duration_ms: float = 0.0


def _get(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _is_api_entry(entry: Any) -> bool:
    if isinstance(entry, dict):
        resource_type = str(entry.get("resource_type", "") or "")
        return resource_type in {"xhr", "fetch", "websocket"} or entry.get("json_data") is not None
    is_api = getattr(entry, "is_api", None)
    if is_api is not None:
        return bool(is_api)
    resource_type = str(getattr(entry, "resource_type", "") or "")
    return (
        resource_type in {"xhr", "fetch", "websocket"}
        or getattr(entry, "json_data", None) is not None
    )


def _split_query(url: str) -> tuple[str, dict[str, Any]]:
    parts = urllib.parse.urlsplit(url)
    params: dict[str, Any] = {}
    for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
        if key not in params:
            params[key] = value
        elif isinstance(params[key], list):
            params[key].append(value)
        else:
            params[key] = [params[key], value]
    clean = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    return clean, params


def _entry_name(url: str) -> str:
    path = urllib.parse.urlsplit(url).path
    name = path.rstrip("/").rsplit("/", 1)[-1] if path.rstrip("/") else ""
    return urllib.parse.unquote(name) or "endpoint"


def _parse_body(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def _entry_to_spec(entry: Any) -> ApiSpec | None:
    if not _is_api_entry(entry):
        return None
    method = str(_get(entry, "method", "GET") or "GET").upper()
    url = str(_get(entry, "url", "") or "")
    if not url.startswith(("http://", "https://")):
        return None
    base_url, params = _split_query(url)
    headers = _get(entry, "request_headers") or None
    if isinstance(headers, dict):
        headers = {str(k): str(v) for k, v in headers.items()}
    content_type = _get(entry, "request_content_type")
    body = _parse_body(_get(entry, "post_data", None))
    return ApiSpec(
        method=method,
        url=base_url,
        name=_entry_name(url),
        headers=headers,
        params=params or None,
        body=body,
        source="captured",
        content_type=content_type,
    )


def _static_endpoint_to_spec(endpoint: Any) -> ApiSpec:
    method = str(_get(endpoint, "method", "GET") or "GET").upper()
    url = str(_get(endpoint, "url", "") or "")
    base_url, params = _split_query(url)
    return ApiSpec(
        method=method,
        url=base_url,
        name=_entry_name(url),
        params=params or None,
        source=str(_get(endpoint, "source", "static") or "static"),
    )


def build_api_specs(
    page_capture: Any,
    *,
    include_captured: bool = True,
    include_static: bool = True,
    max_specs: int = 200,
) -> list[ApiSpec]:
    """Convert a PageCapture / capture dict into replayable API specs.

    Captured HTTP xhr/fetch entries keep their request headers and POST bodies.
    Static endpoints from page_data_parser are added as GET specs when the
    capture has an analysis section. WebSocket entries are recorded but not
    replayed over HTTP.
    """

    specs: list[ApiSpec] = []
    seen: set[tuple[str, str]] = set()

    def add(spec: ApiSpec) -> None:
        if len(specs) >= max_specs:
            return
        if urllib.parse.urlsplit(spec.url).scheme not in {"http", "https"}:
            return
        key = (spec.method.upper(), spec.url)
        if key in seen:
            return
        seen.add(key)
        specs.append(spec)

    if include_captured:
        network = _get(page_capture, "network", None)
        if network:
            for entry in network:
                spec = _entry_to_spec(entry)
                if spec is not None:
                    add(spec)

    if include_static:
        analysis = _get(page_capture, "analysis", None)
        if isinstance(analysis, dict):
            endpoints = analysis.get("api_endpoints") or []
            for endpoint in endpoints:
                add(_static_endpoint_to_spec(endpoint))
        elif analysis is not None:
            endpoints = getattr(analysis, "api_endpoints", None) or []
            for endpoint in endpoints:
                add(_static_endpoint_to_spec(endpoint))

    for spec in specs:
        analysis = _get(page_capture, "analysis", None)
        if analysis is not None:
            pagination = (
                analysis.get("pagination")
                if isinstance(analysis, dict)
                else getattr(analysis, "pagination", None)
            )
            if pagination:
                spec.pagination = pagination
    return specs


def load_page_capture(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dot_get(data: Any, path: str | None, default: Any = None) -> Any:
    if not path:
        return default
    current = data
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part, default)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else default
        else:
            return default
        if current is default:
            return default
    return current


def _extract_items(data: Any, items_path: str | None) -> list[Any]:
    if items_path:
        value = _dot_get(data, items_path)
        return value if isinstance(value, list) else []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "data", "records", "list", "rows", "results"):
            value = data.get(key)
            if isinstance(value, list):
                return value
        return [data]
    return []


def _build_url(url: str, params: dict[str, Any] | None) -> str:
    if not params:
        return url
    query = urllib.parse.urlencode(params, doseq=True)
    separator = "&" if urllib.parse.urlsplit(url).query else "?"
    return f"{url}{separator}{query}"


def _looks_like_pagination(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("type"))


class ApiClient:
    """Fetch API specs through a rate-limited, cookie-aware HTTP session."""

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
        proxy_pool: ProxyPool | None = None,
        min_interval: float = 0.0,
        jitter: float = 0.2,
        max_retries: int = 0,
        backoff_base: float = 0.5,
        backoff_max: float = 30.0,
        timeout: float = DEFAULT_TIMEOUT,
        cookies: list[dict[str, Any]] | None = None,
        backend: str = "standard",
        auto_install: bool | None = None,
    ) -> None:
        self.headers = dict(headers or {})
        self.proxy = proxy
        self.proxy_pool = proxy_pool
        self.min_interval = min_interval
        self.jitter = jitter
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.timeout = timeout
        self.backend = backend
        self.auto_install = auto_install
        self.session = self._new_session()
        if cookies:
            self.add_cookies(cookies)

    def _new_session(self) -> MediaSession:
        return create_fetch_session(
            {"backend": self.backend, "auto_install": self.auto_install},
            headers=dict(self.headers),
            proxy=self.proxy,
            proxy_pool=self.proxy_pool,
            min_interval=self.min_interval,
            jitter=self.jitter,
            max_retries=self.max_retries,
            backoff_base=self.backoff_base,
            backoff_max=self.backoff_max,
            timeout=self.timeout,
        )

    def add_cookies(self, cookies: list[dict[str, Any]]) -> None:
        """Import Playwright-style cookies into the API session."""
        self.session.load_cookies(cookies)

    def close(self) -> None:
        """Release optional smart-fetch transports (standard session is a no-op)."""
        self.session.close()

    def _fetch_one(
        self,
        spec: ApiSpec,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> ApiResponse:
        url = spec.url
        merged_params = dict(spec.params or {})
        if params:
            merged_params.update(params)
        url = _build_url(url, merged_params or None)
        headers = dict(spec.headers or {})
        body = spec.body
        json_body = body if isinstance(body, dict | list) else None
        data = None if json_body is not None else body
        started = time.monotonic()
        result, status, response_headers = self.session.request_json_with_meta(
            spec.method,
            url,
            headers=headers,
            json_body=json_body,
            data=data,
            timeout=timeout or self.timeout,
        )
        return ApiResponse(
            data=result,
            status=status,
            headers=response_headers,
            duration_ms=(time.monotonic() - started) * 1000,
        )

    def fetch_spec(
        self,
        spec: ApiSpec,
        timeout: float | None = None,
        pagination: dict[str, Any] | None = None,
    ) -> Any:
        """Fetch one spec, automatically walking pages when configured."""
        pagination_cfg = pagination
        if pagination_cfg is None and _looks_like_pagination(spec.pagination):
            pagination_cfg = spec.pagination
        if not pagination_cfg:
            return self._fetch_one(spec, timeout=timeout).data
        return self._fetch_paginated(spec, pagination_cfg, timeout=timeout)[0]

    def _fetch_with_pages(
        self,
        spec: ApiSpec,
        timeout: float | None = None,
    ) -> tuple[Any, int, ApiResponse | None]:
        pagination_cfg = None
        if _looks_like_pagination(spec.pagination):
            pagination_cfg = spec.pagination
        if not pagination_cfg:
            response = self._fetch_one(spec, timeout=timeout)
            return response.data, 1, response
        return self._fetch_paginated(spec, pagination_cfg, timeout=timeout)

    def _fetch_paginated(
        self,
        spec: ApiSpec,
        pagination: dict[str, Any],
        timeout: float | None = None,
    ) -> tuple[list[Any], int, ApiResponse | None]:
        pagination_type = str(pagination.get("type", "page")).lower()
        param = str(pagination.get("param", "page"))
        page_size = int(pagination.get("page_size", 20))
        page_size_param = pagination.get("page_size_param")
        max_pages = max(1, int(pagination.get("max_pages", 100)))
        items_path = pagination.get("items_path")
        total_path = pagination.get("total_path")
        has_more_path = pagination.get("has_more_path")
        next_path = pagination.get("next_path")
        records: list[Any] = []
        pages = 0
        last_response: ApiResponse | None = None

        def reached_total(data: Any) -> bool:
            if not total_path:
                return False
            total = _dot_get(data, str(total_path))
            try:
                return bool(total is not None and len(records) >= int(total))
            except (TypeError, ValueError):
                return False

        if pagination_type == "page":
            page = int(pagination.get("start", 1))
            for _ in range(max_pages):
                params: dict[str, Any] = {param: page}
                if page_size_param:
                    params[str(page_size_param)] = page_size
                response = self._fetch_one(spec, params=params, timeout=timeout)
                data = response.data
                last_response = response
                items = _extract_items(data, items_path)
                records.extend(items)
                pages += 1
                if not items or reached_total(data):
                    break
                if has_more_path:
                    has_more = _dot_get(data, str(has_more_path))
                    if has_more is not None and has_more in {False, "false", "0", 0}:
                        break
                page += 1
        elif pagination_type == "offset":
            offset = int(pagination.get("start", 0))
            for _ in range(max_pages):
                params = {param: offset}
                if page_size_param:
                    params[str(page_size_param)] = page_size
                response = self._fetch_one(spec, params=params, timeout=timeout)
                data = response.data
                last_response = response
                items = _extract_items(data, items_path)
                records.extend(items)
                pages += 1
                if not items or reached_total(data):
                    break
                if has_more_path:
                    has_more = _dot_get(data, str(has_more_path))
                    if has_more is not None and has_more in {False, "false", "0", 0}:
                        break
                offset += page_size
        elif pagination_type == "cursor":
            cursor = pagination.get("start")
            for _ in range(max_pages):
                if cursor is None:
                    break
                params = {param: cursor}
                response = self._fetch_one(spec, params=params, timeout=timeout)
                data = response.data
                last_response = response
                items = _extract_items(data, items_path)
                records.extend(items)
                pages += 1
                next_value = _dot_get(data, str(next_path)) if next_path else None
                if not items or next_value in (None, "", False):
                    break
                if reached_total(data):
                    break
                cursor = next_value
        else:
            raise ValueError(f"unsupported pagination type: {pagination_type}")

        return records, pages, last_response

    def _fetch_result(
        self,
        spec: ApiSpec,
        timeout: float | None = None,
    ) -> ApiFetchResult:
        try:
            data, pages, meta = self._fetch_with_pages(spec, timeout=timeout)
            security = None
            error = None
            if meta is not None and meta.status is not None:
                body_text = (
                    data
                    if isinstance(data, str)
                    else json.dumps(data, ensure_ascii=False)
                    if data is not None
                    else ""
                )
                report = detect_security_mechanisms(
                    meta.status,
                    spec.url,
                    meta.headers or {},
                    body_text,
                    html=body_text,
                    page_url=spec.url,
                )
                if report.is_blocked:
                    security = report.to_dict()
                    error = f"blocked by {report.primary_kind}"
                elif meta.status >= 400:
                    security = report.to_dict()
                    error = f"HTTP {meta.status}"
            return ApiFetchResult(
                spec=spec,
                data=data,
                pages=pages,
                status=meta.status if meta is not None else None,
                headers=meta.headers if meta is not None else None,
                duration_ms=meta.duration_ms if meta is not None else None,
                security=security,
                error=error,
            )
        except Exception as exc:
            return ApiFetchResult(spec=spec, error=str(exc))

    def fetch_all(
        self,
        specs: list[ApiSpec],
        concurrency: int = 1,
    ) -> list[ApiFetchResult]:
        results: list[ApiFetchResult] = []
        if concurrency <= 1:
            for spec in specs:
                results.append(self._fetch_result(spec))
            return results

        def worker(spec: ApiSpec) -> ApiFetchResult:
            cookies = [
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "expires": cookie.expires,
                    "session": cookie.discard,
                }
                for cookie in self.session.cookies
            ]
            client = ApiClient(
                headers=self.headers,
                proxy=self.proxy,
                proxy_pool=self.proxy_pool,
                min_interval=self.min_interval,
                jitter=self.jitter,
                max_retries=self.max_retries,
                backoff_base=self.backoff_base,
                backoff_max=self.backoff_max,
                timeout=self.timeout,
                cookies=cookies,
                backend=self.backend,
                auto_install=self.auto_install,
            )
            try:
                return client._fetch_result(spec)
            finally:
                client.close()

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            results = list(pool.map(worker, specs))
        return results

    def save_results(
        self,
        results: list[ApiFetchResult],
        path: str | Path,
    ) -> Path:
        out = Path(path)
        if out.suffix.lower() == ".jsonl":
            lines = [json.dumps(item.to_dict(), ensure_ascii=False) for item in results]
            out.write_text("\n".join(lines), encoding="utf-8")
        else:
            out.write_text(
                json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return out

    def save_specs(self, specs: list[ApiSpec], path: str | Path) -> Path:
        out = Path(path)
        out.write_text(
            json.dumps([spec.to_dict() for spec in specs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return out


class _SelfTestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path.startswith("/api/items"):
            body = json.dumps(
                {
                    "items": [
                        {"id": 1, "name": "one"},
                        {"id": 2, "name": "two"},
                    ],
                    "total": 2,
                }
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/config"):
            body = json.dumps({"enabled": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 0:
            self.rfile.read(length)
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        pass


def _self_test() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        capture = {
            "network": [
                {
                    "method": "GET",
                    "url": f"{base}/api/items?page=1",
                    "resource_type": "fetch",
                    "status": 200,
                    "json_data": {"total": 2},
                }
            ],
            "analysis": {
                "api_endpoints": [
                    {"method": "GET", "url": f"{base}/api/config", "source": "script"}
                ],
                "pagination": {"page": [{"path": "page", "key": "page", "value": "1"}]},
            },
        }
        specs = build_api_specs(capture)
        assert len(specs) == 2, specs
        client = ApiClient()
        results = client.fetch_all(specs)
        assert results[0].error is None, results[0].error
        assert results[0].data["total"] == 2
        assert results[1].error is None, results[1].error
        assert results[1].data["enabled"] is True
    finally:
        server.shutdown()
        server.server_close()
    print("api_client self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover and fetch API data")
    parser.add_argument("--input", help="PageCapture JSON produced by browser_session.py")
    parser.add_argument("--output", help="output path for specs or fetched results")
    parser.add_argument("--fetch", action="store_true", help="fetch discovered API specs")
    parser.add_argument("--headers", default=None, help='JSON object, e.g. {"X-Token": "..."}')
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--min-interval", type=float, default=0.0)
    parser.add_argument("--max-retries", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument(
        "--backend",
        default="standard",
        help="standard or auto (curl_cffi -> cloudscraper -> httpx -> urllib)",
    )
    parser.add_argument(
        "--auto-install",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="auto-install missing optional web-fetch packages (default: auto mode installs)",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.input:
        parser.error("--input is required unless --self-test is used")
    capture = load_page_capture(args.input)
    specs = build_api_specs(capture)
    if not args.fetch:
        payload = [spec.to_dict() for spec in specs]
        if args.output:
            Path(args.output).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    headers = json.loads(args.headers) if args.headers else None
    client = ApiClient(
        headers=headers,
        proxy=args.proxy,
        min_interval=args.min_interval,
        max_retries=args.max_retries,
        backend=args.backend,
        auto_install=args.auto_install,
    )
    results = client.fetch_all(specs, concurrency=args.concurrency)
    if args.output:
        client.save_results(results, args.output)
    else:
        print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
