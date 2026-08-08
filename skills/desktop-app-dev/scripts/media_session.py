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
from http.cookiejar import CookieJar

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
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.timeout = timeout
        self.headers = dict(headers or {})
        self.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        self.headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        self.proxy = proxy
        self.cookies = CookieJar()
        self._opener = self._build_opener()

    def _build_opener(self) -> urllib.request.OpenerDirector:
        handlers: list[urllib.request.BaseHandler] = [
            urllib.request.HTTPCookieProcessor(self.cookies)
        ]
        if self.proxy:
            handlers.append(urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))
        handlers.append(urllib.request.HTTPRedirectHandler())
        return urllib.request.build_opener(*handlers)

    def open(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ):
        request = urllib.request.Request(url, headers=self._merge_headers(headers))
        return self._opener.open(request, timeout=timeout or self.timeout)

    def head(self, url: str, headers: dict[str, str] | None = None) -> MediaProbe:
        request = urllib.request.Request(url, headers=self._merge_headers(headers), method="HEAD")
        try:
            response = self._opener.open(request, timeout=self.timeout)
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
        request = urllib.request.Request(url, headers=merged)
        with self._opener.open(request, timeout=timeout or self.timeout) as response:
            return response.read(), dict(response.headers.items())

    def get_json(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> dict:
        body, _ = self.get_bytes(url, headers=headers, timeout=timeout)
        return json.loads(body.decode("utf-8"))

    def _merge_headers(self, extra: dict[str, str] | None) -> dict[str, str]:
        merged = dict(self.headers)
        if extra:
            merged.update(extra)
        return merged

    def close(self) -> None:
        """Compatibility hook; the standard-library opener has no close."""
