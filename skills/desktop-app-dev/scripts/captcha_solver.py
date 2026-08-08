"""CAPTCHA solver interface and third-party service adapter.

The generic HTTP adapter follows the common submit-then-poll pattern used by
services such as 2captcha. Replace `base_url` and response parsing with the
documentation of the actual service. Keep the API key encrypted in local
config (Windows DPAPI / keyring), never in source or plaintext config.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


class CaptchaError(RuntimeError):
    """Raised when a CAPTCHA cannot be solved."""


@dataclass
class CaptchaResult:
    success: bool
    task_id: str
    answer: str | None = None
    raw: str | None = None


class CaptchaSolver:
    """Submit-then-poll adapter for third-party CAPTCHA services."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://2captcha.com",
        timeout: float = 120.0,
        poll_interval: float = 3.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval

    def solve_image(
        self,
        image_path: str | Path,
        min_length: int = 0,
        max_length: int = 0,
        language: int = 0,
        phrase: bool = False,
        case_sensitive: bool = False,
        numeric: int = 0,
    ) -> CaptchaResult:
        image_path = Path(image_path)
        if not image_path.exists():
            raise CaptchaError(f"captcha image not found: {image_path}")
        params = {
            "key": self.api_key,
            "method": "base64",
            "body": _b64encode_file(image_path),
            "min_len": min_length,
            "max_len": max_length,
            "language": language,
            "phrase": 1 if phrase else 0,
            "regsense": 1 if case_sensitive else 0,
            "numeric": numeric,
        }
        return self._solve(params)

    def solve_recaptcha_v2(
        self, site_key: str, page_url: str, invisible: bool = False
    ) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "version": "v2",
                "invisible": 1 if invisible else 0,
            }
        )

    def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "hcaptcha",
                "sitekey": site_key,
                "pageurl": page_url,
            }
        )

    def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "turnstile",
                "sitekey": site_key,
                "pageurl": page_url,
            }
        )

    def _solve(self, params: dict) -> CaptchaResult:
        task_id = self._submit(params)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            answer = self._poll(task_id)
            if answer is not None:
                return CaptchaResult(success=True, task_id=task_id, answer=answer, raw=answer)
            time.sleep(self.poll_interval)
        raise CaptchaError(f"CAPTCHA task {task_id} timed out")

    def _submit(self, params: dict) -> str:
        response = self._request(f"{self.base_url}/in.php", params)
        if response.startswith("OK|"):
            return response.split("|", 1)[1]
        raise CaptchaError(f"captcha submit failed: {response}")

    def _poll(self, task_id: str) -> str | None:
        params = {"key": self.api_key, "action": "get", "id": task_id}
        response = self._request(f"{self.base_url}/res.php", params)
        if response == "CAPCHA_NOT_READY":
            return None
        if response.startswith("OK|"):
            return response.split("|", 1)[1]
        raise CaptchaError(f"captcha poll failed: {response}")

    def _request(self, url: str, params: dict) -> str:
        data = urllib.parse.urlencode(params).encode("utf-8")
        request = urllib.request.Request(url, data=data)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise CaptchaError(f"captcha HTTP error {exc.code}: {exc.read()[:200]!r}") from exc


class ManualCaptchaSolver:
    """Bridge between the UI thread and a worker waiting for user input."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._answer: str | None = None
        self._image_path: Path | None = None

    def request_captcha(self, image_path: str | Path | None = None) -> None:
        self._image_path = Path(image_path) if image_path else None
        self._answer = None
        self._event.clear()

    def submit_answer(self, answer: str) -> None:
        self._answer = answer
        self._event.set()

    def wait_for_answer(self, timeout: float = 300.0) -> str:
        if not self._event.wait(timeout):
            raise CaptchaError("manual CAPTCHA answer timed out")
        if self._answer is None:
            raise CaptchaError("manual CAPTCHA was cancelled")
        return self._answer

    @property
    def image_path(self) -> Path | None:
        return self._image_path


def _b64encode_file(path: Path) -> str:
    import base64

    return base64.b64encode(path.read_bytes()).decode("ascii")
