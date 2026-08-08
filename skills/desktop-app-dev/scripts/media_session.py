"""HTTP session helper for media acquisition templates.

Uses only the standard library so the skill templates run without extra
dependencies. For production, swap the transport with httpx / aiohttp while
keeping the same MediaSession interface.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from typing import Any

from proxy_pool import ProxyPool
from scrape_guard import (
    AdaptiveThrottle,
    RateLimiter,
    RequestPacer,
    RetryPolicy,
    RobotsPolicy,
    parse_retry_after,
)

DEFAULT_TIMEOUT = 20.0
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MediaPipeline/1.0"


def guess_filename(url: str, content_disposition: str | None = None) -> str | None:
    """Return a filename from Content-Disposition or the URL path."""
    if content_disposition:
        match = re.search(
            r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?',
            content_disposition,
            re.IGNORECASE,
        )
        if match:
            return urllib.parse.unquote(match.group(1).strip())
    path = urllib.parse.urlparse(url).path
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    if name and "." in name:
        return urllib.parse.unquote(name)
    return None


@dataclass
class MediaProbe:
    """HEAD metadata used to decide chunking and filename."""

    url: str
    status: int
    total_size: int | None
    accept_ranges: bool
    content_type: str | None
    filename: str | None
    headers: dict[str, str]

    @property
    def supports_resume(self) -> bool:
        return self.total_size is not None and self.accept_ranges


class MediaSession:
    """Persistent cookie, proxy, and header session."""

    def __init__(
        self,
        headers: dict[str, str] | None = None,
        proxy: str | None = None,
        proxy_pool: ProxyPool | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        min_interval: float = 0.0,
        jitter: float = 0.2,
        max_retries: int = 0,
        backoff_base: float = 0.5,
        backoff_max: float = 30.0,
        robots: RobotsPolicy | None = None,
        adaptive_throttle: AdaptiveThrottle | None = None,
    ) -> None:
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        self.headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        self.proxy = proxy
        self.proxy_pool = proxy_pool
        self._current_proxy_used = proxy
        self.cookies = CookieJar()
        self._opener = self._build_opener(self.proxy)
        rate_limiter = (
            RateLimiter(min_interval=min_interval, jitter=jitter) if min_interval > 0 else None
        )
        self.retry_policy = (
            RetryPolicy(
                max_retries=max_retries,
                base_delay=backoff_base,
                max_delay=backoff_max,
            )
            if max_retries > 0
            else None
        )
        self.pacer = RequestPacer(
            robots=robots,
            throttle=adaptive_throttle,
            rate_limiter=rate_limiter,
        )
        self.adaptive_throttle = adaptive_throttle

    def _build_opener(self, proxy: str | None) -> urllib.request.OpenerDirector:
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.HTTPCookieProcessor(self.cookies)
        ]
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        handlers.append(urllib.request.HTTPRedirectHandler())
        return urllib.request.build_opener(*handlers)

    def _current_proxy(self) -> str | None:
        if self.proxy_pool is not None:
            return self.proxy_pool.get_proxy()
        return self.proxy

    def _report_proxy_success(self, proxy: str | None) -> None:
        if self.proxy_pool is not None:
            self.proxy_pool.report_success(proxy)

    def _report_proxy_failure(self, proxy: str | None) -> None:
        if self.proxy_pool is not None:
            self.proxy_pool.report_failure(proxy)

    def open(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        return self._request(
            url,
            self._merge_headers(headers),
            timeout=timeout,
        )

    def head(self, url: str, headers: dict[str, str] | None = None) -> MediaProbe:
        try:
            response = self._request(
                url,
                self._merge_headers(headers),
                method="HEAD",
            )
        except urllib.error.HTTPError as exc:
            response = exc
        content_length = response.headers.get("Content-Length", "")
        total_size = int(content_length) if content_length.isdigit() else None
        accept_ranges = (response.headers.get("Accept-Ranges") or "").lower() == "bytes"
        return MediaProbe(
            url=url,
            status=int(getattr(response, "status", response.code)),
            total_size=total_size,
            accept_ranges=accept_ranges,
            content_type=response.headers.get("Content-Type"),
            filename=guess_filename(url, response.headers.get("Content-Disposition")),
            headers=dict(response.headers.items()),
        )

    def get_bytes(
        self,
        url: str,
        range_header: str | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[bytes, dict[str, str]]:
        merged = self._merge_headers(headers)
        if range_header:
            merged["Range"] = range_header
        with self._request(url, merged, timeout=timeout) as response:
            return response.read(), dict(response.headers.items())

    def get_bytes_with_meta(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[bytes, int, dict[str, str]]:
        """Fetch bytes and return body, status, and headers on any HTTP result."""
        merged = self._merge_headers(headers)
        try:
            with self._request(url, merged, timeout=timeout) as response:
                return (
                    response.read(),
                    int(getattr(response, "status", response.code)),
                    dict(response.headers.items()),
                )
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return (
                body,
                int(getattr(exc, "code", 0)),
                dict(exc.headers.items()) if exc.headers else {},
            )

    def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict:
        body, _ = self.get_bytes(url, headers=headers, timeout=timeout)
        return json.loads(body.decode("utf-8"))

    def request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        json_body: object | None = None,
        data: bytes | str | None = None,
        timeout: float | None = None,
    ):
        """Send a request and return JSON when possible, else text."""
        return self.request_json_with_meta(
            method,
            url,
            headers=headers,
            json_body=json_body,
            data=data,
            timeout=timeout,
        )[0]

    def request_json_with_meta(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        *,
        json_body: object | None = None,
        data: bytes | str | None = None,
        timeout: float | None = None,
    ) -> tuple[Any, int, dict[str, str]]:
        """Send a request and return (data, status, response headers)."""
        merged = self._merge_headers(headers)
        payload = data
        if json_body is not None:
            payload = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            merged.setdefault("Content-Type", "application/json")
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        try:
            with self._request(
                url,
                merged,
                method=method.upper(),
                data=payload,
                timeout=timeout,
            ) as response:
                body = response.read()
                content_type = (response.headers.get("Content-Type") or "").lower()
                status = int(getattr(response, "status", getattr(response, "code", 0)))
                response_headers = dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            content_type = (exc.headers.get("Content-Type") or "").lower() if exc.headers else ""
            status = int(getattr(exc, "code", 0))
            response_headers = dict(exc.headers.items()) if exc.headers else {}
        if not body:
            return None, status, response_headers
        if "json" in content_type:
            return json.loads(body.decode("utf-8")), status, response_headers
        return body.decode("utf-8", "replace"), status, response_headers

    def _merge_headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        merged = dict(self.headers)
        if extra:
            merged.update(extra)
        return merged

    def _request(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ):
        attempt = 0
        while True:
            proxy = self._current_proxy()
            if proxy != self._current_proxy_used:
                self._opener = self._build_opener(proxy)
                self._current_proxy_used = proxy
            self.pacer.wait(url)
            request = urllib.request.Request(
                url,
                headers=headers,
                method=method,
                data=data,
            )
            try:
                response = self._opener.open(request, timeout=timeout or self.timeout)
            except urllib.error.HTTPError as exc:
                self._report_proxy_failure(proxy)
                status = int(getattr(exc, "code", 0))
                if self.adaptive_throttle is not None:
                    self.adaptive_throttle.on_block(status)
                if self.retry_policy is not None and self.retry_policy.should_retry(
                    status,
                    attempt,
                ):
                    retry_after = parse_retry_after(
                        exc.headers.get("Retry-After") if exc.headers else None
                    )
                    self.retry_policy.sleep_before_retry(
                        status,
                        attempt,
                        retry_after,
                    )
                    attempt += 1
                    continue
                raise
            except urllib.error.URLError:
                self._report_proxy_failure(proxy)
                raise
            else:
                self._report_proxy_success(proxy)
                if self.adaptive_throttle is not None:
                    self.adaptive_throttle.on_success()
                return response

    def close(self) -> None:
        """Compatibility hook; the standard-library opener has no close."""

    def load_cookies(self, cookies: list[dict]) -> None:
        """Import Playwright-style cookie objects into the CookieJar."""
        for item in cookies:
            if not isinstance(item, dict):
                continue
            domain = str(item.get("domain", "") or "")
            name = str(item.get("name", "") or "")
            if not domain or not name:
                continue
            expires = item.get("expires")
            if isinstance(expires, int) and expires <= 0:
                expires = None
            self.cookies.set_cookie(
                Cookie(
                    version=0,
                    name=name,
                    value=str(item.get("value", "") or ""),
                    port=None,
                    port_specified=False,
                    domain=domain,
                    domain_specified=True,
                    domain_initial_dot=domain.startswith("."),
                    path=str(item.get("path", "/") or "/"),
                    path_specified=True,
                    secure=bool(item.get("secure", False)),
                    expires=expires,
                    discard=bool(item.get("session", False)),
                    comment=None,
                    comment_url=None,
                    rest={},
                )
            )


if __name__ == "__main__":
    print(
        "desktop-app-dev media_session: import MediaSession for cookie-aware retry HTTP sessions."
    )
