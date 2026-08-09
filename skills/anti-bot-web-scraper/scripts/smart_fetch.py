"""Adaptive multi-backend HTTP fetching for authorized web automation.

The standard `MediaSession` is intentionally dependency-free. This module
adds an optional `SmartFetchSession` that keeps the same interface while
trying stronger transports in order:

- `curl_cffi` -- browser TLS/JA3/JA4 + HTTP/2 impersonation
- `tls_client` -- Go TLS fingerprint client
- `cloudscraper` -- Cloudflare JS challenge / Turnstile solving
- `httpx` -- HTTP/2 connection pooling
- `urllib` -- standard-library fallback

`create_fetch_session()` returns the standard session unless the caller
requests `backend: "auto"` (or another adaptive value). When a response is
classified as a Cloudflare challenge / block, WAF block, rate limit, or
CAPTCHA wall, the smart session switches to the next installed backend.
Cloudflare clearance is tied to the visitor/device, so the session keeps
the same proxy, user agent, and cookies across switches.

When every HTTP transport is blocked and the caller supplies a `browser`
config, the session escalates to the stealth browser loop and merges solved
cookies back into the HTTP session.
"""

from __future__ import annotations

import http.cookies
import importlib.util
import io
import sys
import time
import urllib.error
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from http.cookiejar import Cookie
from typing import Any

from fingerprint_bank import HeaderFingerprint
from fingerprint_binding import (
    FingerprintBinding,
    apply_binding_to_fetch_config,
    binding_from_fetch_config,
    resolve_binding,
)
from media_session import MediaSession
from scrape_guard import parse_retry_after
from security_detector import detect_security_mechanisms

BACKEND_ORDER = ("curl_cffi", "tls_client", "cloudscraper", "httpx", "urllib")
EXTRA_BACKENDS = {"flaresolverr", "browser"}
DEFAULT_IMPERSONATE = "chrome"
ADAPTIVE_BACKENDS = {"auto", "adaptive", "smart", "cloudflare"}
_TLS_IDENTIFIER_ALIASES = {
    "chrome": "chrome_124",
    "edge": "chrome_124",
    "firefox": "firefox_124",
    "safari": "safari_15_6_1",
    "opera": "opera_91",
}
_CURL_IMPERSONATE_ALIASES = {
    "chrome": "chrome124",
    "chrome_124": "chrome124",
    "chrome_126": "chrome126",
    "edge": "chrome124",
    "edge_126": "chrome126",
    "firefox": "firefox124",
    "firefox_124": "firefox124",
    "firefox_127": "firefox127",
    "safari": "safari15_5",
    "safari_15_6_1": "safari15_5",
    "opera": "opera91",
    "opera_91": "opera91",
}


def _canonical_headers(headers: dict[str, Any]) -> dict[str, str]:
    result = {str(key): str(value) for key, value in headers.items()}
    lower_lookup: dict[str, tuple[str, str]] = {}
    for key, value in result.items():
        lower_lookup.setdefault(key.lower(), (key, value))
    for canonical in ("Content-Type", "Set-Cookie", "Content-Length", "Retry-After"):
        lower = canonical.lower()
        if lower in lower_lookup and canonical not in result:
            result[canonical] = lower_lookup[lower][1]
    return result


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def available_backends() -> list[str]:
    """Return installed HTTP backends in the preferred fallback order."""
    available = [name for name in BACKEND_ORDER if name == "urllib" or _module_available(name)]
    if "urllib" not in available:
        available.append("urllib")
    return available


def backend_status() -> dict[str, Any]:
    """Return a machine-readable status of every supported fetch backend."""
    installed = set(available_backends())
    return {
        "mode": "auto",
        "backends": [
            {
                "name": name,
                "installed": name in installed,
                "description": {
                    "curl_cffi": "browser TLS/JA3/JA4 + HTTP/2 impersonation",
                    "tls_client": "Go TLS fingerprint client",
                    "cloudscraper": "Cloudflare JS challenge / Turnstile solving",
                    "httpx": "HTTP/2 connection pooling",
                    "urllib": "standard-library fallback",
                }[name],
            }
            for name in BACKEND_ORDER
        ],
    }


def normalize_backend(value: str | None) -> str:
    backend = str(value or "standard").strip().lower()
    if backend in ADAPTIVE_BACKENDS:
        return "auto"
    if backend in BACKEND_ORDER or backend in EXTRA_BACKENDS:
        return backend
    return "standard"


def create_fetch_session(config: dict[str, Any] | None = None, **kwargs: Any):
    """Create a standard or adaptive session from a fetch config object."""
    cfg = dict(config or {})
    captcha_solver = cfg.get("captcha_solver") or kwargs.pop("captcha_solver", None)
    backend = normalize_backend(cfg.get("backend", "standard"))
    if backend == "standard":
        return MediaSession(**kwargs)
    binding = binding_from_fetch_config(cfg)
    if binding is not None:
        cfg = apply_binding_to_fetch_config(cfg, binding)
    auto_install = cfg.get("auto_install")
    if auto_install is None:
        auto_install = True
    return SmartFetchSession(
        backend=backend,
        backend_order=cfg.get("order"),
        impersonate=cfg.get("impersonate", DEFAULT_IMPERSONATE),
        cloudscraper_options=cfg.get("cloudscraper"),
        flaresolverr_config=cfg.get("flaresolverr"),
        browser_config=cfg.get("browser"),
        header_fingerprint=cfg.get("header_fingerprint", "chrome"),
        fingerprint_binding=binding,
        captcha_solver=captcha_solver,
        auto_install_dependencies=bool(auto_install),
        **kwargs,
    )


@dataclass
class BackendResponse:
    """Normalized response used while deciding whether to switch backend."""

    url: str
    status: int
    headers: dict[str, str]
    body: bytes
    backend: str = ""
    error: str | None = None
    security: dict[str, Any] | None = None

    def as_file(self) -> _SmartResponse:
        return _SmartResponse(self.body, self.status, self.headers)


class _SmartResponse(io.BytesIO):
    """Small urllib-compatible file wrapper used by the smart session."""

    def __init__(
        self,
        body: bytes,
        status: int,
        headers: dict[str, str],
    ) -> None:
        super().__init__(body)
        self.status = status
        self.code = status
        self.headers = headers


class SmartFetchSession(MediaSession):
    """MediaSession-compatible session that auto-switches HTTP backends."""

    def __init__(
        self,
        backend: str = "auto",
        backend_order: list[str] | tuple[str, ...] | None = None,
        impersonate: str = DEFAULT_IMPERSONATE,
        cloudscraper_options: dict[str, Any] | None = None,
        flaresolverr_config: dict[str, Any] | None = None,
        browser_config: dict[str, Any] | None = None,
        header_fingerprint: str = "chrome",
        fingerprint_binding: str | dict[str, Any] | FingerprintBinding | None = None,
        captcha_solver: Any = None,
        auto_install_dependencies: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.binding = resolve_binding(fingerprint_binding)
        self.captcha_solver = captcha_solver
        self.backend_mode = normalize_backend(backend)
        self.backend_order = tuple(backend_order) if backend_order else BACKEND_ORDER
        self.impersonate = str(
            self.binding.tls_impersonate
            if self.binding is not None
            else impersonate or DEFAULT_IMPERSONATE
        )
        self.cloudscraper_options = dict(cloudscraper_options or {})
        self.flaresolverr_config = dict(flaresolverr_config or {})
        self.browser_config = dict(browser_config or {})
        if (
            self.binding is not None
            and self.binding.compatible_engines
            and str(self.browser_config.get("engine") or "auto").lower()
            in {"auto", "adaptive", "smart"}
        ):
            self.browser_config["stealth_engine_order"] = list(
                self.binding.compatible_engines
            )
        if self.binding is not None:
            self.browser_config.setdefault("user_agent", self.binding.user_agent)
        self.header_fingerprint = str(
            self.binding.header_fingerprint
            if self.binding is not None
            else header_fingerprint or "chrome"
        )
        self.auto_install_dependencies = auto_install_dependencies
        self._cookie_items: list[dict[str, Any]] = []
        self._curl_session: Any = None
        self._tls_client: Any = None
        self._cloudscraper: Any = None
        self._httpx_client: Any = None
        self._httpx_proxy: str | None = None
        self.stats: dict[str, Any] = {
            "attempts": [],
            "last_backend": None,
            "last_security_kind": None,
            "last_error": None,
            "switches": 0,
            "browser_attempts": [],
        }

    def _fingerprinted_headers(self, headers: dict[str, str]) -> dict[str, str]:
        if self.binding is not None:
            merged = self.binding.to_header_headers(headers)
            return merged
        profile = HeaderFingerprint.for_browser(self.header_fingerprint)
        return profile.apply(headers)

    def _ordered_backends(self) -> list[str]:
        if self.backend_mode == "standard":
            return ["urllib"]
        if self.auto_install_dependencies:
            self._ensure_dependencies()
        order = list(self.backend_order)
        if self.flaresolverr_config and "flaresolverr" not in order:
            order.insert(-1, "flaresolverr")
        if (self.browser_config or self.backend_mode == "browser") and "browser" not in order:
            order.append("browser")
        if self.backend_mode == "auto":
            installed = set(available_backends())
            return [
                name
                for name in order
                if name in installed
                or (name == "flaresolverr" and self.flaresolverr_config)
                or name == "browser"
            ]
        if self.backend_mode in BACKEND_ORDER or self.backend_mode in EXTRA_BACKENDS:
            return [self.backend_mode]
        return ["urllib"]

    def _ensure_dependencies(self) -> None:
        try:
            from ensure_web_fetch_dependencies import (
                WEB_FETCH_PACKAGES,
            )
            from ensure_web_fetch_dependencies import (
                ensure as _ensure_fetch_dependencies,
            )

            _ensure_fetch_dependencies(install=True, packages=WEB_FETCH_PACKAGES)
        except Exception as exc:
            print(f"smart_fetch: auto dependency install skipped: {exc}", file=sys.stderr)

    def load_cookies(self, cookies: list[dict]) -> None:
        super().load_cookies(cookies)
        for item in cookies or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            domain = str(item.get("domain") or "")
            if not name or not domain:
                continue
            self._set_cookie_item(
                {
                    "name": name,
                    "value": str(item.get("value") or ""),
                    "domain": domain,
                    "path": str(item.get("path") or "/"),
                    "secure": bool(item.get("secure", False)),
                    "expires": item.get("expires"),
                    "httpOnly": bool(item.get("httpOnly", False)),
                    "sameSite": item.get("sameSite"),
                    "partitioned": bool(item.get("partitioned", False)),
                }
            )

    def _set_cookie_item(self, item: dict[str, Any]) -> None:
        name = str(item.get("name") or "")
        domain = str(item.get("domain") or "").lower()
        for existing in self._cookie_items:
            if (
                str(existing.get("name") or "").lower() == name.lower()
                and str(existing.get("domain") or "").lower() == domain
                and str(existing.get("path") or "/") == str(item.get("path") or "/")
            ):
                existing.update(item)
                return
        self._cookie_items.append(dict(item))
        expires = item.get("expires")
        if isinstance(expires, int | float):
            expires = int(expires) if expires > 0 else None
        self.cookies.set_cookie(
            Cookie(
                version=0,
                name=name,
                value=str(item.get("value") or ""),
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=True,
                domain_initial_dot=domain.startswith("."),
                path=str(item.get("path") or "/"),
                path_specified=True,
                secure=bool(item.get("secure", False)),
                expires=expires,
                discard=bool(item.get("session", False)),
                comment=None,
                comment_url=None,
                rest={},
            )
        )

    def _cookie_header(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or "/"
        values: list[str] = []
        for item in self._cookie_items:
            domain = str(item.get("domain") or "").lower().lstrip(".")
            if domain and host != domain and not host.endswith("." + domain):
                continue
            cookie_path = str(item.get("path") or "/")
            if cookie_path != "/" and not (
                path == cookie_path or path.startswith(cookie_path.rstrip("/") + "/")
            ):
                continue
            if item.get("secure") and parsed.scheme != "https":
                continue
            expires = item.get("expires")
            if isinstance(expires, int | float) and expires > 0 and expires < time.time():
                continue
            values.append(f"{item.get('name')}={item.get('value')}")
        return "; ".join(values)

    def _capture_set_cookie(self, url: str, headers: dict[str, str]) -> None:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname or ""
        set_cookie = ""
        for key, value in headers.items():
            if key.lower() == "set-cookie":
                set_cookie = value if not set_cookie else f"{set_cookie}; {value}"
        if not set_cookie:
            return
        try:
            simple = http.cookies.SimpleCookie()
            simple.load(set_cookie)
        except http.cookies.CookieError:
            return
        for morsel in simple.values():
            item: dict[str, Any] = {
                "name": morsel.key,
                "value": morsel.value,
                "domain": morsel.get("domain") or host,
                "path": morsel.get("path") or "/",
                "secure": bool(morsel.get("secure")),
                "expires": None,
                "httpOnly": bool(morsel.get("httponly")),
                "sameSite": morsel.get("samesite"),
                "partitioned": bool(morsel.get("partitioned")),
            }
            expires_text = morsel.get("expires")
            if expires_text:
                with suppress(TypeError, ValueError, OverflowError):
                    item["expires"] = parsedate_to_datetime(expires_text).timestamp()
            self._set_cookie_item(item)

    def _proxy_map(self) -> dict[str, str] | None:
        proxy = self._current_proxy()
        return {"http": proxy, "https": proxy} if proxy else None

    def _get_curl_session(self) -> Any:
        if self._curl_session is None:
            from curl_cffi.requests import Session

            self._curl_session = Session()
        return self._curl_session

    def _get_cloudscraper(self) -> Any:
        if self._cloudscraper is None:
            import cloudscraper

            options = dict(self.cloudscraper_options)
            browser_name = (
                "chrome"
                if self.binding is None
                else "firefox"
                if self.binding.browser_family == "firefox"
                else "chrome"
            )
            options.setdefault(
                "browser",
                {"browser": browser_name, "platform": "windows", "mobile": False},
            )
            self._cloudscraper = cloudscraper.create_scraper(**options)
        return self._cloudscraper

    def _get_httpx_client(self) -> Any:
        import httpx

        proxy = self._current_proxy()
        if self._httpx_client is None or proxy != self._httpx_proxy:
            if self._httpx_client is not None:
                self._httpx_client.close()
            try:
                self._httpx_client = httpx.Client(
                    http2=_module_available("h2"),
                    follow_redirects=True,
                    proxy=proxy,
                )
            except TypeError:
                proxies = {"http://": proxy, "https://": proxy} if proxy else None
                self._httpx_client = httpx.Client(
                    http2=_module_available("h2"),
                    follow_redirects=True,
                    proxies=proxies,
                )
            self._httpx_proxy = proxy
        return self._httpx_client

    def _try_backend(
        self,
        name: str,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        if name == "urllib":
            return self._request_urllib(url, headers, method=method, data=data, timeout=timeout)
        if name == "curl_cffi":
            return self._request_curl(url, headers, method=method, data=data, timeout=timeout)
        if name == "tls_client":
            return self._request_tls_client(
                url,
                headers,
                method=method,
                data=data,
                timeout=timeout,
            )
        if name == "cloudscraper":
            return self._request_cloudscraper(
                url,
                headers,
                method=method,
                data=data,
                timeout=timeout,
            )
        if name == "httpx":
            return self._request_httpx(url, headers, method=method, data=data, timeout=timeout)
        if name == "flaresolverr":
            return self._request_flaresolverr(
                url,
                headers,
                method=method,
                data=data,
                timeout=timeout,
            )
        if name == "browser":
            return self._request_browser(
                url,
                headers,
                method=method,
                data=data,
                timeout=timeout,
            )
        raise RuntimeError(f"unsupported fetch backend: {name}")

    def _request_flaresolverr(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        from flaresolverr import FlaresolverrClient

        if method and method.upper() != "GET":
            raise RuntimeError("flaresolverr backend currently supports GET only")
        if data:
            raise RuntimeError("flaresolverr backend currently supports GET only")
        client = FlaresolverrClient(
            base_url=str(self.flaresolverr_config.get("base_url", "http://127.0.0.1:8191")),
            timeout=float(self.flaresolverr_config.get("timeout", 90.0)),
            max_timeout=int(
                self.flaresolverr_config.get(
                    "max_timeout",
                    int((timeout or self.timeout) * 1000),
                )
            ),
        )
        result = client.request_get(
            url,
            proxy=self._current_proxy(),
            cookies=list(self._cookie_items),
            session=self.flaresolverr_config.get("session"),
            max_timeout=int(
                self.flaresolverr_config.get(
                    "max_timeout",
                    int((timeout or self.timeout) * 1000),
                )
            ),
            wait_seconds=self.flaresolverr_config.get("wait_seconds"),
            return_only_cookies=bool(self.flaresolverr_config.get("return_only_cookies", False)),
            disable_media=bool(self.flaresolverr_config.get("disable_media", False)),
        )
        for item in result.cookies:
            if item.get("name") and item.get("domain"):
                self._set_cookie_item(item)
        return BackendResponse(
            url=result.url,
            status=result.status,
            headers=_canonical_headers(result.headers),
            body=result.body.encode("utf-8"),
            backend="flaresolverr",
        )

    def _request_urllib(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        try:
            response = super()._request(
                url,
                self._fingerprinted_headers(headers),
                method=method,
                data=data,
                timeout=timeout,
            )
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            return BackendResponse(
                url=url,
                status=int(getattr(exc, "code", 0)),
                headers=(_canonical_headers(dict(exc.headers.items())) if exc.headers else {}),
                body=body,
                backend="urllib",
            )
        body = response.read()
        response_headers = dict(response.headers.items())
        status = int(getattr(response, "status", getattr(response, "code", 200)))
        response.close()
        return BackendResponse(
            url=url,
            status=status,
            headers=_canonical_headers(response_headers),
            body=body,
            backend="urllib",
        )

    def _request_curl(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        session = self._get_curl_session()
        request_headers = self._fingerprinted_headers(headers)
        cookie_header = self._cookie_header(url)
        if cookie_header:
            request_headers.setdefault("Cookie", cookie_header)
        kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": timeout or self.timeout,
            "allow_redirects": True,
        }
        if data is not None:
            kwargs["data"] = data
        proxies = self._proxy_map()
        if proxies:
            kwargs["proxies"] = proxies
        kwargs["impersonate"] = self._curl_impersonate()
        response = session.request(method or "GET", url, **kwargs)
        return BackendResponse(
            url=url,
            status=int(response.status_code),
            headers=_canonical_headers(dict(response.headers.items())),
            body=response.content or b"",
            backend="curl_cffi",
        )

    def _tls_identifier(self) -> str:
        if self.binding is not None:
            return self.binding.tls_impersonate
        value = str(self.impersonate or DEFAULT_IMPERSONATE).lower()
        return _TLS_IDENTIFIER_ALIASES.get(value, value)

    def _curl_impersonate(self) -> str:
        value = str(self.impersonate or DEFAULT_IMPERSONATE).lower()
        return _CURL_IMPERSONATE_ALIASES.get(value, value.replace("_", ""))

    def _get_tls_client(self) -> Any:
        if self._tls_client is None:
            import tls_client

            self._tls_client = tls_client.Session(client_identifier=self._tls_identifier())
        return self._tls_client

    def _request_tls_client(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        session = self._get_tls_client()
        request_headers = self._fingerprinted_headers(headers)
        cookie_header = self._cookie_header(url)
        if cookie_header:
            request_headers.setdefault("Cookie", cookie_header)
        kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout_seconds": timeout or self.timeout,
            "allow_redirects": True,
        }
        if data is not None:
            kwargs["data"] = data
        proxy = self._current_proxy()
        if proxy:
            kwargs["proxy"] = proxy
        request_method = str(method or "GET").upper()
        try:
            response = session.request(request_method, url, **kwargs)
        except AttributeError:
            if request_method == "GET":
                response = session.get(url, **kwargs)
            elif request_method == "HEAD":
                response = session.head(url, **kwargs)
            elif request_method == "POST":
                response = session.post(url, **kwargs)
            elif request_method == "PUT":
                response = session.put(url, **kwargs)
            elif request_method == "DELETE":
                response = session.delete(url, **kwargs)
            else:
                raise
        return BackendResponse(
            url=url,
            status=int(response.status_code),
            headers=_canonical_headers(dict(response.headers.items())),
            body=response.content or b"",
            backend="tls_client",
        )

    def _request_browser(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        if method and method.upper() != "GET":
            raise RuntimeError("browser backend currently supports GET only")
        if data:
            raise RuntimeError("browser backend currently supports GET only")
        from stealth_browser import solve_cloudflare_with_stealth_browser

        cfg = self.browser_config or {}
        engine = cfg.get("engine", "auto")
        proxy = cfg.get("proxy") or self._current_proxy()
        result = solve_cloudflare_with_stealth_browser(
            url,
            engine=str(engine),
            engine_order=cfg.get("stealth_engine_order") or cfg.get("engine_order"),
            proxy=proxy,
            browser_path=cfg.get("browser_path"),
            headless=bool(cfg.get("headless", True)),
            headless_fallback=bool(cfg.get("headless_fallback", True)),
            storage_state=cfg.get("storage_state"),
            timeout_ms=float(
                cfg.get(
                    "challenge_timeout",
                    cfg.get("timeout_ms", (timeout or self.timeout) * 1000),
                )
            ),
            auto_install=bool(cfg.get("auto_install", self.auto_install_dependencies)),
            max_attempts=int(cfg.get("max_attempts", cfg.get("challenge_attempts", 2))),
            retry_delay=float(cfg.get("retry_delay", 2.0)),
            rotate_proxy_on_fail=bool(cfg.get("rotate_proxy_on_fail", True)),
            proxy_pool=self.proxy_pool,
            fingerprint_binding=self.binding,
            captcha_solver=self.captcha_solver,
        )
        for item in result.cookies or []:
            if item.get("name") and item.get("domain"):
                self._set_cookie_item(item)
        attempts = result.attempts or []
        self.stats["browser_attempts"].extend(attempts)
        return BackendResponse(
            url=result.final_url or result.url or url,
            status=int(result.status or 200),
            headers={"Content-Type": "text/html; charset=utf-8"},
            body=(result.html or "").encode("utf-8"),
            backend=f"browser:{result.engine}",
        )

    def _request_cloudscraper(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        session = self._get_cloudscraper()
        request_headers = self._fingerprinted_headers(headers)
        cookie_header = self._cookie_header(url)
        if cookie_header:
            request_headers.setdefault("Cookie", cookie_header)
        kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": timeout or self.timeout,
            "allow_redirects": True,
        }
        if data is not None:
            kwargs["data"] = data
        proxies = self._proxy_map()
        if proxies:
            kwargs["proxies"] = proxies
        response = session.request(method or "GET", url, **kwargs)
        return BackendResponse(
            url=url,
            status=int(response.status_code),
            headers=_canonical_headers(dict(response.headers.items())),
            body=response.content or b"",
            backend="cloudscraper",
        )

    def _request_httpx(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ) -> BackendResponse:
        client = self._get_httpx_client()
        request_headers = self._fingerprinted_headers(headers)
        cookie_header = self._cookie_header(url)
        if cookie_header:
            request_headers.setdefault("Cookie", cookie_header)
        kwargs: dict[str, Any] = {
            "headers": request_headers,
            "timeout": timeout or self.timeout,
            "follow_redirects": True,
        }
        if data is not None:
            kwargs["content"] = data
        response = client.request(method or "GET", url, **kwargs)
        return BackendResponse(
            url=url,
            status=int(response.status_code),
            headers=_canonical_headers(dict(response.headers.items())),
            body=response.content or b"",
            backend="httpx",
        )

    def _classify(self, response: BackendResponse) -> bool:
        body_text = response.body.decode("utf-8", "replace")
        report = detect_security_mechanisms(
            response.status,
            response.url,
            response.headers,
            body_text,
            html=body_text,
            page_url=response.url,
        )
        self.stats["last_security_kind"] = report.primary_kind
        if (
            report.is_blocked
            and report.primary_kind in {"captcha_required", "cloudflare_challenge"}
            and self._has_valid_clearance(response.url)
        ):
            self.stats["last_security_kind"] = None
            return False
        return report.is_blocked

    def _has_valid_clearance(self, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        host = (parsed.hostname or "").lower()
        for item in self._cookie_items:
            if str(item.get("name") or "").lower() != "cf_clearance":
                continue
            domain = str(item.get("domain") or "").lower().lstrip(".")
            if domain and host != domain and not host.endswith("." + domain):
                continue
            expires = item.get("expires")
            if isinstance(expires, int | float) and expires > 0 and expires <= time.time():
                continue
            return True
        return False

    def _record_attempt(
        self,
        backend: str,
        status: int | None,
        headers: dict[str, str],
        body: bytes,
        error: str | None = None,
    ) -> None:
        body_text = body.decode("utf-8", "replace")
        report = detect_security_mechanisms(
            status,
            "",
            headers,
            body_text,
            html=body_text,
        )
        self.stats["attempts"].append(
            {
                "backend": backend,
                "status": status,
                "error": error,
                "security": report.primary_kind,
            }
        )
        self.stats["last_backend"] = backend
        self.stats["last_error"] = error
        self.stats["last_security_kind"] = report.primary_kind
        self.stats["switches"] = max(
            0, len(set(item["backend"] for item in self.stats["attempts"])) - 1
        )

    def _request(
        self,
        url: str,
        headers: dict[str, str],
        method: str | None = None,
        data: bytes | None = None,
        timeout: float | None = None,
    ):
        self.pacer.wait(url)
        if self._pinned_proxy is None and self.proxy_pool is not None and not self.proxy:
            sticky_key = (
                f"smart:{self.binding.name}"
                if self.binding is not None
                else f"smart:{urllib.parse.urlsplit(url).hostname or 'request'}"
            )
            self.pin_proxy(self.proxy_pool.get_sticky_proxy(sticky_key, ttl=1800))
        attempt = 0
        last: BackendResponse | None = None
        last_error: Exception | None = None
        while True:
            for name in self._ordered_backends():
                try:
                    response = self._try_backend(
                        name,
                        url,
                        headers,
                        method=method,
                        data=data,
                        timeout=timeout,
                    )
                except Exception as exc:
                    last_error = exc
                    self._report_proxy_failure(self._current_proxy())
                    self._record_attempt(name, None, {}, b"", error=str(exc))
                    continue
                self._capture_set_cookie(url, response.headers)
                blocked = self._classify(response)
                self._record_attempt(
                    response.backend or name,
                    response.status,
                    response.headers,
                    response.body,
                )
                if self.adaptive_throttle is not None:
                    if response.status >= 400 or blocked:
                        self.adaptive_throttle.on_block(response.status)
                    else:
                        self.adaptive_throttle.on_success()
                if response.status < 400 and not blocked:
                    self._report_proxy_success(self._current_proxy())
                    return response.as_file()
                if response.status >= 400 and not blocked:
                    self._report_proxy_failure(self._current_proxy())
                last = response

            if (
                last is not None
                and self.retry_policy is not None
                and self.retry_policy.should_retry(last.status, attempt)
            ):
                retry_after = parse_retry_after(last.headers.get("Retry-After"))
                self.retry_policy.sleep_before_retry(
                    last.status,
                    attempt,
                    retry_after,
                )
                attempt += 1
                continue
            break

        if last is not None:
            if last.status >= 400:
                raise urllib.error.HTTPError(
                    url,
                    last.status,
                    "HTTP error",
                    last.headers,
                    io.BytesIO(last.body),
                )
            return last.as_file()
        if last_error is not None:
            raise urllib.error.URLError(last_error)
        raise urllib.error.URLError("no fetch backend available")

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.backend_mode,
            "auto_install_dependencies": self.auto_install_dependencies,
            "available": available_backends(),
            "browser_config": self.browser_config,
            "fingerprint_binding": (
                self.binding.to_dict() if self.binding is not None else None
            ),
            "stats": self.stats,
        }

    def close(self) -> None:
        if self._tls_client is not None and hasattr(self._tls_client, "close"):
            self._tls_client.close()
        if self._httpx_client is not None:
            self._httpx_client.close()
        if self._cloudscraper is not None and hasattr(self._cloudscraper, "close"):
            self._cloudscraper.close()
        if self._curl_session is not None and hasattr(self._curl_session, "close"):
            self._curl_session.close()


AdaptiveFetchSession = SmartFetchSession


if __name__ == "__main__":
    print(
        "desktop-app-dev smart_fetch: import SmartFetchSession / create_fetch_session "
        "for automatic multi-backend anti-bot fetching."
    )
