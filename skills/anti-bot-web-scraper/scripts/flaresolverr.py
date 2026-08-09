"""FlareSolverr client for Cloudflare / DDoS-Guard challenge solving.

FlareSolverr is an optional external service that runs a stealth browser
and returns the solved HTML plus cookies. The client below talks to its
HTTP JSON API using only the standard library, so the skill templates do
not gain a hard dependency. Use it when the lightweight HTTP backends
(`curl_cffi` / `cloudscraper`) cannot clear a Managed Challenge and a
full browser is too heavy for the local machine.

Typical local endpoint:

```text
http://127.0.0.1:8191/v1
```
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any


class FlaresolverrError(RuntimeError):
    """Raised when the FlareSolverr service returns an error."""


@dataclass
class FlaresolverrResult:
    """Normalized result from one FlareSolverr `request.get` call."""

    url: str
    status: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    cookies: list[dict[str, Any]] = field(default_factory=list)
    user_agent: str | None = None
    turnstile_token: str | None = None
    engine: str = "flaresolverr"

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "status": self.status,
            "headers": self.headers,
            "cookies": self.cookies,
            "user_agent": self.user_agent,
            "turnstile_token": self.turnstile_token,
            "engine": self.engine,
        }


class FlaresolverrClient:
    """Small standard-library client for a local FlareSolverr instance."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8191",
        timeout: float = 90.0,
        max_timeout: int = 60000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_timeout = max_timeout

    def request_get(
        self,
        url: str,
        *,
        proxy: str | None = None,
        cookies: list[dict[str, Any]] | None = None,
        session: str | None = None,
        max_timeout: int | None = None,
        wait_seconds: float | None = None,
        return_only_cookies: bool = False,
        disable_media: bool = False,
    ) -> FlaresolverrResult:
        """Solve a URL through FlareSolverr and return the final response."""
        payload: dict[str, Any] = {
            "cmd": "request.get",
            "url": url,
            "maxTimeout": max_timeout or self.max_timeout,
        }
        if proxy:
            payload["proxy"] = {"url": proxy}
        if cookies:
            payload["cookies"] = [
                {
                    "name": item.get("name"),
                    "value": item.get("value"),
                    "domain": item.get("domain"),
                    "path": item.get("path", "/"),
                }
                for item in cookies
                if item.get("name") and item.get("value") is not None
            ]
        if session:
            payload["session"] = session
        if return_only_cookies:
            payload["returnOnlyCookies"] = True
        if wait_seconds is not None:
            payload["waitInSeconds"] = float(wait_seconds)
        if disable_media:
            payload["disableMedia"] = True
        data = self._post(payload)
        solution = data.get("solution") or {}
        if data.get("status") == "error" or not solution:
            raise FlaresolverrError(str(data.get("message") or "flaresolverr request failed"))
        raw_headers = dict(solution.get("headers") or {})
        headers = {str(key): str(value) for key, value in raw_headers.items()}
        cookies_out = self._normalize_cookies(
            list(solution.get("cookies") or []),
            urllib.parse.urlsplit(url).hostname or "",
        )
        status = int(solution.get("status", 0) or 0)
        return FlaresolverrResult(
            url=str(solution.get("url") or url),
            status=status,
            body=str(solution.get("response") or ""),
            headers=headers,
            cookies=cookies_out,
            user_agent=solution.get("userAgent"),
            turnstile_token=solution.get("turnstile_token"),
        )

    def create_session(self, proxy: str | None = None) -> str:
        payload: dict[str, Any] = {"cmd": "sessions.create"}
        if proxy:
            payload["proxy"] = {"url": proxy}
        data = self._post(payload)
        session = data.get("session")
        if not session:
            raise FlaresolverrError(str(data.get("message") or "session creation failed"))
        return str(session)

    def destroy_session(self, session: str) -> bool:
        data = self._post({"cmd": "sessions.destroy", "session": session})
        return data.get("status") == "ok"

    def list_sessions(self) -> list[str]:
        data = self._post({"cmd": "sessions.list"})
        return [str(item) for item in data.get("sessions") or []]

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/v1",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace") if hasattr(exc, "read") else ""
            raise FlaresolverrError(f"flaresolverr HTTP {exc.code}: {raw[:300]}") from exc
        except urllib.error.URLError as exc:
            raise FlaresolverrError(f"flaresolverr unavailable: {exc.reason}") from exc
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FlaresolverrError(f"flaresolverr invalid JSON: {raw[:300]}") from exc

    @staticmethod
    def _normalize_cookies(
        cookies: list[dict[str, Any]],
        default_domain: str,
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in cookies:
            name = str(item.get("name") or "")
            value = str(item.get("value") or "")
            if not name or not value:
                continue
            normalized.append(
                {
                    "name": name,
                    "value": value,
                    "domain": str(item.get("domain") or default_domain),
                    "path": str(item.get("path") or "/"),
                    "secure": bool(item.get("secure", False)),
                    "httpOnly": bool(item.get("httpOnly", False)),
                    "sameSite": item.get("sameSite"),
                    "expires": item.get("expires"),
                    "session": bool(item.get("session", False)),
                }
            )
        return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Query a local FlareSolverr service and print its status."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8191")
    parser.add_argument("--url", default=None, help="solve this URL with request.get")
    parser.add_argument("--check", action="store_true", help="list active sessions")
    args = parser.parse_args(argv)
    client = FlaresolverrClient(base_url=args.base_url)
    try:
        if args.url:
            result = client.request_get(args.url)
            print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        elif args.check:
            print(json.dumps({"sessions": client.list_sessions()}, ensure_ascii=False))
        else:
            print(json.dumps({"base_url": client.base_url}, ensure_ascii=False))
    except FlaresolverrError as exc:
        print(f"flaresolverr error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
