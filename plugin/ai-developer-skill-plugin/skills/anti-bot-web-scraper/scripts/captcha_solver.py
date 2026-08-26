"""CAPTCHA solver interface and third-party service adapter.

The generic HTTP adapter follows the common submit-then-poll pattern used by
services such as 2captcha. Replace `base_url` and response parsing with the
documentation of the actual service. Keep the API key encrypted in local
config (Windows DPAPI / keyring), never in source or plaintext config.

`detect_captchas()` also recognizes the common CAPTCHA scripts embedded in a
page (reCAPTCHA v2/v3, hCaptcha, Turnstile, Geetest, image CAPTCHAs) and
`AutoCaptchaSolver` routes each detected challenge to the configured
third-party service without a manual UI dialog.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


class CaptchaError(RuntimeError):
    """Raised when a CAPTCHA cannot be solved."""


@dataclass
class CaptchaResult:
    success: bool
    task_id: str
    answer: str | None = None
    raw: str | None = None


@dataclass
class CaptchaChallenge:
    kind: str
    site_key: str | None = None
    page_url: str | None = None
    image_url: str | None = None
    selector: str | None = None
    script_url: str | None = None
    frame_url: str | None = None
    challenge: str | None = None
    action: str | None = None
    confidence: float = 0.0
    audio_url: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "site_key": self.site_key,
            "page_url": self.page_url,
            "image_url": self.image_url,
            "selector": self.selector,
            "script_url": self.script_url,
            "frame_url": self.frame_url,
            "challenge": self.challenge,
            "action": self.action,
            "confidence": self.confidence,
            "audio_url": self.audio_url,
        }


class _CaptchaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.script_srcs: list[str] = []
        self.script_texts: list[str] = []
        self.elements: list[tuple[str, dict[str, str]]] = []
        self._script_text: list[str] = []
        self._in_script = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        tag = tag.lower()
        if tag == "script":
            src = attr_map.get("src", "").strip()
            if src:
                self.script_srcs.append(src)
            self._script_text = []
            self._in_script = True
        elif tag in {"div", "iframe", "img", "input", "audio", "button"}:
            self.elements.append((tag, attr_map))

    def handle_data(self, data: str) -> None:
        if self._in_script:
            self._script_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._in_script:
            self.script_texts.append("".join(self._script_text))
            self._in_script = False


_CAPTCHA_IMAGE_HINTS = (
    "captcha",
    "kaptcha",
    "securimage",
    "verify_code",
    "verifycode",
    "security_code",
    "code_image",
    "yanzhengma",
)
_STRONG_CAPTCHA_INPUT_HINTS = (
    "captcha",
    "verify_code",
    "verifycode",
    "security_code",
    "checkcode",
    "yanzhengma",
)
_SLIDER_CAPTCHA_HINTS = (
    "geetest_slider",
    "geetest_slide",
    "nc_iconfont",
    "btn_slide",
    "yidun_slider",
    "captcha-slider",
    "verify-slider",
    "slide-verify",
    "secsdk-captcha-drag-icon",
    "滑块",
)
_AUDIO_CAPTCHA_HINTS = (
    "audio-captcha",
    "captcha-audio",
    "play audio",
    "listen",
    "语音",
    "音频",
)


def detect_captchas(html: str, page_url: str | None = None) -> list[CaptchaChallenge]:
    """Detect CAPTCHA scripts, elements, and image challenges in a page."""
    parser = _CaptchaHTMLParser()
    parser.feed(html)
    challenges: list[CaptchaChallenge] = []
    seen: set[tuple[str, str | None]] = set()

    def add(
        kind: str,
        *,
        site_key: str | None = None,
        image_url: str | None = None,
        selector: str | None = None,
        script_url: str | None = None,
        frame_url: str | None = None,
        challenge: str | None = None,
        action: str | None = None,
        confidence: float = 0.5,
        audio_url: str | None = None,
    ) -> None:
        key = (kind, site_key or image_url or selector or script_url or audio_url or "")
        if key in seen:
            return
        seen.add(key)
        challenges.append(
            CaptchaChallenge(
                kind=kind,
                site_key=site_key,
                page_url=page_url,
                image_url=image_url,
                selector=selector,
                script_url=script_url,
                frame_url=frame_url,
                challenge=challenge,
                action=action,
                confidence=confidence,
                audio_url=audio_url,
            )
        )

    for src in parser.script_srcs:
        lower = src.lower()
        if "google.com/recaptcha/api.js" in lower:
            parsed = urllib.parse.urlparse(src)
            params = urllib.parse.parse_qs(parsed.query)
            render = (params.get("render") or [""])[0]
            if render and render.lower() != "explicit":
                add("recaptcha_v3", site_key=render, script_url=src, confidence=0.8)
            else:
                add("recaptcha_v2", script_url=src, confidence=0.6)
        elif "recaptcha/enterprise.js" in lower or "recaptcha/enterprise" in lower:
            parsed = urllib.parse.urlparse(src)
            params = urllib.parse.parse_qs(parsed.query)
            render = (params.get("render") or [""])[0]
            add(
                "recaptcha_enterprise",
                site_key=render or None,
                script_url=src,
                confidence=0.75,
            )
        elif "hcaptcha.com/1/api.js" in lower:
            add("hcaptcha", script_url=src, confidence=0.6)
        elif "turnstile/v0/api.js" in lower:
            add("turnstile", script_url=src, confidence=0.6)
        elif "geetest" in lower:
            add("geetest", script_url=src, confidence=0.6)
        elif "funcaptcha.com" in lower or "arkoselabs.com" in lower:
            parsed = urllib.parse.urlparse(src)
            params = urllib.parse.parse_qs(parsed.query)
            pkey = (params.get("pkey") or [""])[0]
            add(
                "funcaptcha",
                site_key=pkey or None,
                script_url=src,
                confidence=0.8,
            )
        elif "captcha-delivery.com" in lower or "datadome" in lower:
            add("datadome", script_url=src, confidence=0.6)
        elif "px-captcha" in lower or "perimeterx" in lower:
            add("perimeterx", script_url=src, confidence=0.6)
        elif "awswaf.com" in lower or "awswaf" in lower:
            add("awswaf", script_url=src, confidence=0.6)

    captcha_images: list[tuple[int, str | None]] = []
    captcha_inputs: list[tuple[int, str]] = []
    for index, (tag, attrs) in enumerate(parser.elements):
        classes = attrs.get("class", "").lower()
        element_id = attrs.get("id", "").lower()
        if tag == "div":
            if "g-recaptcha" in classes:
                site_key = attrs.get("data-sitekey") or None
                add(
                    "recaptcha_v2",
                    site_key=site_key,
                    selector="div.g-recaptcha",
                    confidence=0.9 if site_key else 0.7,
                )
            if "h-captcha" in classes:
                site_key = attrs.get("data-sitekey") or None
                add(
                    "hcaptcha",
                    site_key=site_key,
                    selector="div.h-captcha",
                    confidence=0.9 if site_key else 0.7,
                )
            if "cf-turnstile" in classes:
                site_key = attrs.get("data-sitekey") or None
                add(
                    "turnstile",
                    site_key=site_key,
                    selector="div.cf-turnstile",
                    confidence=0.9 if site_key else 0.7,
                )
            if "geetest" in classes or "geetest" in element_id:
                site_key = attrs.get("data-sitekey") or None
                add(
                    "geetest",
                    site_key=site_key,
                    selector=(f"#{element_id}" if element_id else "div[id*=geetest]"),
                    confidence=0.7,
                )
            if (
                "funcaptcha" in classes
                or "funcaptcha" in element_id
                or "arkose" in classes
                or attrs.get("data-pkey")
            ):
                add(
                    "funcaptcha",
                    site_key=attrs.get("data-pkey") or None,
                    selector=(f"#{element_id}" if element_id else "div[class*=funcaptcha]"),
                    confidence=0.8,
                )
            if "px-captcha" in classes or "perimeterx" in classes:
                add(
                    "perimeterx",
                    site_key=attrs.get("data-sitekey") or None,
                    selector="div.px-captcha, div[class*=perimeterx]",
                    confidence=0.75,
                )
            if "awswaf" in classes or "aws-waf" in classes:
                add(
                    "awswaf",
                    site_key=attrs.get("data-sitekey") or None,
                    selector="div[class*=awswaf], div[class*=aws-waf]",
                    confidence=0.75,
                )
            if any(hint in classes or hint in element_id for hint in _SLIDER_CAPTCHA_HINTS):
                selector = (
                    f"#{element_id}"
                    if element_id
                    else f".{classes.split()[0]}"
                    if classes
                    else "div[id*=slide], div[class*=slider]"
                )
                add(
                    "slider",
                    selector=selector,
                    confidence=0.78,
                )
        elif tag == "img":
            src = (attrs.get("src") or attrs.get("data-src") or "").strip()
            combined = f"{src} {attrs.get('alt', '')}".lower()
            if any(hint in combined for hint in _CAPTCHA_IMAGE_HINTS):
                image_url = urllib.parse.urljoin(page_url or "", src) if src else None
                captcha_images.append((index, image_url))
        elif tag == "audio":
            src = (attrs.get("src") or "").strip()
            combined = (
                f"{attrs.get('class', '')} {attrs.get('id', '')} "
                f"{attrs.get('aria-label', '')}"
            ).lower()
            is_captcha_audio = "captcha" in combined or "verify" in combined or any(
                hint in combined for hint in _AUDIO_CAPTCHA_HINTS
            )
            if is_captcha_audio:
                add(
                    "audio",
                    audio_url=urllib.parse.urljoin(page_url or "", src) if src else None,
                    selector=(
                        f"#{attrs['id']}"
                        if attrs.get("id")
                        else "audio[src*=captcha], audio[class*=captcha]"
                    ),
                    confidence=0.7,
                )
        elif tag == "button":
            combined = f"{attrs.get('class', '')} {attrs.get('id', '')}".lower()
            if any(hint in combined for hint in _AUDIO_CAPTCHA_HINTS):
                add(
                    "audio",
                    selector=(
                        f"#{attrs['id']}"
                        if attrs.get("id")
                        else "button[class*=audio], button[id*=audio]"
                    ),
                    confidence=0.55,
                )
        elif tag == "input":
            name = attrs.get("name", "").lower()
            input_id = attrs.get("id", "").lower()
            input_class = attrs.get("class", "").lower()
            combined = f"{name} {input_id} {input_class}"
            if any(hint in combined for hint in _STRONG_CAPTCHA_INPUT_HINTS) and attrs.get(
                "type", "text"
            ) not in {"hidden", "submit", "button"}:
                selector = (
                    f"input[name={attrs['name']}]"
                    if attrs.get("name")
                    else f"#{input_id}"
                    if input_id
                    else None
                )
                if selector:
                    captcha_inputs.append((index, selector))

    for image_index, image_url in captcha_images:
        selector = next(
            (
                input_selector
                for input_index, input_selector in captcha_inputs
                if input_index > image_index
            ),
            "input[name*=captcha], input[name*=verify_code]",
        )
        add(
            "image",
            image_url=image_url,
            selector=selector,
            confidence=0.85,
        )
    for _, selector in captcha_inputs:
        if not any(
            challenge.kind == "image" and challenge.selector == selector for challenge in challenges
        ):
            add("image", image_url=None, selector=selector, confidence=0.5)

    script_text = "\n".join(parser.script_texts)
    if re.search(r"\bgrecaptcha\.execute\b", script_text, re.I):
        add("recaptcha_v3", confidence=0.4)
    if re.search(r"\bgrecaptcha\.render\b", script_text, re.I):
        add("recaptcha_v2", confidence=0.4)
    if re.search(r"\bhcaptcha\.render\b", script_text, re.I):
        add("hcaptcha", confidence=0.4)
    if re.search(r"\bturnstile\.render\b", script_text, re.I):
        add("turnstile", confidence=0.4)
    if re.search(r"\binitGeetest\b", script_text, re.I):
        add("geetest", confidence=0.4)
    if re.search(r"funcaptcha|arkoselabs|arkose", script_text, re.I):
        add("funcaptcha", confidence=0.4)
    if re.search(r"datadome|captcha-delivery\.com", script_text, re.I):
        add("datadome", confidence=0.4)
    if re.search(r"perimeterx|px-captcha", script_text, re.I):
        add("perimeterx", confidence=0.4)
    if re.search(r"awswaf|aws-waf", script_text, re.I):
        add("awswaf", confidence=0.4)
    if re.search(r"recaptcha/enterprise", script_text, re.I):
        add("recaptcha_enterprise", confidence=0.4)

    site_key_match = re.search(
        r"sitekey\s*[:=]\s*[\"']([^\"']+)[\"']",
        script_text,
        re.I,
    )
    if site_key_match:
        site_key = site_key_match.group(1)
        if re.search(r"\bgrecaptcha\b", script_text, re.I):
            add("recaptcha_v2", site_key=site_key, confidence=0.5)
        elif re.search(r"\bhcaptcha\b", script_text, re.I):
            add("hcaptcha", site_key=site_key, confidence=0.5)
        elif re.search(r"\bturnstile\b", script_text, re.I):
            add("turnstile", site_key=site_key, confidence=0.5)

    geetest_gt = re.search(
        r"\bgt\s*[:=]\s*[\"']([a-f0-9]{20,})[\"']",
        script_text,
        re.I,
    )
    geetest_challenge = re.search(
        r"\bchallenge\s*[:=]\s*[\"']([^\"']+)[\"']",
        script_text,
        re.I,
    )
    if geetest_gt:
        add(
            "geetest",
            site_key=geetest_gt.group(1),
            challenge=geetest_challenge.group(1) if geetest_challenge else None,
            confidence=0.7,
        )

    challenges.sort(key=lambda item: (-item.confidence, item.kind))
    return challenges


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

    def get_balance(self) -> float:
        """Return the current account balance for this 2captcha-style API."""
        params = {"key": self.api_key, "action": "getbalance"}
        response = self._request(f"{self.base_url}/res.php", params)
        try:
            return float(response)
        except ValueError as exc:
            raise CaptchaError(f"invalid CAPTCHA balance response: {response[:200]}") from exc

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

    def solve_audio(
        self,
        audio_path_or_url: str | Path,
    ) -> CaptchaResult:
        """Solve an audio CAPTCHA through a 2captcha-style audio endpoint."""
        source = Path(audio_path_or_url)
        if not source.exists():
            source = self._download_audio(str(audio_path_or_url))
        params = {
            "key": self.api_key,
            "method": "audio",
            "body": _b64encode_file(source),
        }
        return self._solve(params)

    def _download_audio(self, url: str) -> Path:
        if not url.startswith(("http://", "https://")):
            raise CaptchaError(f"invalid audio CAPTCHA URL: {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            raise CaptchaError(f"audio CAPTCHA download failed: {exc.code}") from exc
        tmp = Path(tempfile.gettempdir()) / f"captcha-audio-{uuid.uuid4().hex}.mp3"
        tmp.write_bytes(data)
        return tmp

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

    def solve_funcaptcha(self, public_key: str, page_url: str) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "funcaptcha",
                "publickey": public_key,
                "pageurl": page_url,
            }
        )

    def solve_recaptcha_enterprise(
        self,
        site_key: str,
        page_url: str,
        action: str | None = None,
        min_score: float = 0.3,
    ) -> CaptchaResult:
        params: dict[str, Any] = {
            "key": self.api_key,
            "method": "userrecaptcha",
            "googlekey": site_key,
            "pageurl": page_url,
            "enterprise": 1,
        }
        if action:
            params["version"] = "v3"
            params["action"] = action
            params["min_score"] = min_score
        else:
            params["version"] = "v2"
        return self._solve(params)

    def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "turnstile",
                "sitekey": site_key,
                "pageurl": page_url,
            }
        )

    def solve_recaptcha_v3(
        self,
        site_key: str,
        page_url: str,
        action: str | None = None,
        min_score: float = 0.3,
    ) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "userrecaptcha",
                "googlekey": site_key,
                "pageurl": page_url,
                "version": "v3",
                "action": action or "",
                "min_score": min_score,
            }
        )

    def solve_geetest(
        self,
        gt: str,
        challenge: str,
        page_url: str,
    ) -> CaptchaResult:
        return self._solve(
            {
                "key": self.api_key,
                "method": "geetest",
                "gt": gt,
                "challenge": challenge,
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


class AutoCaptchaSolver:
    """Automatic CAPTCHA pipeline: detect, solve, and return answers.

    Routes detected challenges to a third-party `CaptchaSolver` without a
    manual dialog. Set `allow_manual_fallback` only when the product is
    allowed to pause for a human.
    """

    def __init__(
        self,
        solver: CaptchaSolver,
        allow_manual_fallback: bool = False,
        manual_solver: ManualCaptchaSolver | None = None,
        ocr_solver: OcrCaptchaSolver | None = None,
    ) -> None:
        self.solver = solver
        self.allow_manual_fallback = allow_manual_fallback
        self.manual_solver = manual_solver
        self.ocr_solver = ocr_solver
        self.last_errors: list[tuple[int, str]] = []

    @property
    def has_service(self) -> bool:
        """Return True when the wrapped provider has a usable API key."""
        key = getattr(self.solver, "api_key", None)
        if key:
            return True
        return bool(getattr(self.solver, "providers", None))

    def solve_challenge(
        self,
        challenge: CaptchaChallenge,
        image_path: str | Path | None = None,
    ) -> str:
        if challenge.kind == "image" and self.ocr_solver is not None:
            path = image_path
            if path is None and challenge.image_url:
                try:
                    path = self._download_image(challenge.image_url)
                except CaptchaError:
                    path = None
            if path is not None:
                try:
                    result = self.ocr_solver.solve_image(path)
                    if result.success and result.answer:
                        return result.answer
                except CaptchaError:
                    pass
        try:
            return self._solve_with_service(challenge, image_path)
        except CaptchaError:
            if self.allow_manual_fallback and self.manual_solver is not None:
                if challenge.kind == "image" and challenge.image_url:
                    image_path = image_path or self._download_image(challenge.image_url)
                self.manual_solver.request_captcha(image_path)
                return self.manual_solver.wait_for_answer()
            raise

    def solve_detected(
        self,
        challenges: list[CaptchaChallenge],
        image_paths: list[str | Path] | None = None,
        max_challenges: int | None = None,
        continue_on_error: bool = False,
    ) -> list[tuple[CaptchaChallenge, str]]:
        solved: list[tuple[CaptchaChallenge, str]] = []
        self.last_errors = []
        image_index = 0
        for index, challenge in enumerate(challenges):
            if max_challenges is not None and index >= max_challenges:
                break
            image_path = None
            if challenge.kind == "image" and image_paths:
                if image_index < len(image_paths):
                    image_path = image_paths[image_index]
                image_index += 1
            try:
                solved.append(
                    (challenge, self.solve_challenge(challenge, image_path=image_path))
                )
            except CaptchaError as exc:
                self.last_errors.append((index, str(exc)))
                if not continue_on_error:
                    raise
        return solved

    def _solve_with_service(
        self,
        challenge: CaptchaChallenge,
        image_path: str | Path | None,
    ) -> str:
        if not self.has_service:
            raise CaptchaError("no CAPTCHA provider API key configured")
        page_url = challenge.page_url or ""
        if challenge.kind == "image":
            path = image_path
            if path is None and challenge.image_url:
                path = self._download_image(challenge.image_url)
            if path is None:
                raise CaptchaError("image CAPTCHA requires image_url or image_path")
            result = self.solver.solve_image(path)
        elif challenge.kind == "recaptcha_v2":
            result = self.solver.solve_recaptcha_v2(challenge.site_key or "", page_url)
        elif challenge.kind == "recaptcha_v3":
            result = self.solver.solve_recaptcha_v3(
                challenge.site_key or "",
                page_url,
                action=challenge.action,
            )
        elif challenge.kind == "recaptcha_enterprise":
            enterprise_solver = getattr(self.solver, "solve_recaptcha_enterprise", None)
            if enterprise_solver is None:
                result = self.solver.solve_recaptcha_v2(challenge.site_key or "", page_url)
            else:
                result = enterprise_solver(
                    challenge.site_key or "",
                    page_url,
                    action=challenge.action,
                )
        elif challenge.kind == "hcaptcha":
            result = self.solver.solve_hcaptcha(challenge.site_key or "", page_url)
        elif challenge.kind == "funcaptcha":
            funcaptcha_solver = getattr(self.solver, "solve_funcaptcha", None)
            if funcaptcha_solver is None:
                raise CaptchaError("CAPTCHA provider does not support FunCaptcha / Arkose")
            result = funcaptcha_solver(challenge.site_key or "", page_url)
        elif challenge.kind == "turnstile":
            result = self.solver.solve_turnstile(challenge.site_key or "", page_url)
        elif challenge.kind == "geetest":
            result = self.solver.solve_geetest(
                challenge.site_key or "",
                challenge.challenge or "",
                page_url,
            )
        elif challenge.kind == "audio":
            solver_audio = getattr(self.solver, "solve_audio", None)
            if solver_audio is None:
                raise CaptchaError("CAPTCHA provider does not support audio")
            result = solver_audio(challenge.audio_url or "")
        elif challenge.kind == "slider":
            solver_slider = getattr(self.solver, "solve_slider", None)
            if solver_slider is None:
                raise CaptchaError("CAPTCHA provider does not support slider tasks")
            result = solver_slider(challenge.selector or "")
        else:
            raise CaptchaError(f"unsupported CAPTCHA kind: {challenge.kind}")
        if not result.success or not result.answer:
            raise CaptchaError(f"CAPTCHA solver returned no answer for {challenge.kind}")
        return result.answer

    def _download_image(self, url: str) -> Path:
        if not url.startswith(("http://", "https://")):
            raise CaptchaError(f"invalid captcha image URL: {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            raise CaptchaError(f"captcha image download failed: {exc.code}") from exc
        tmp = Path(tempfile.gettempdir()) / f"captcha-{uuid.uuid4().hex}.img"
        tmp.write_bytes(data)
        return tmp


def preprocess_captcha_image(
    image_path: str | Path,
    output_path: str | Path | None = None,
    *,
    denoise: bool = True,
    threshold: int = 140,
    scale: int = 2,
) -> Path:
    """Preprocess a CAPTCHA image with optional Pillow filters."""
    source = Path(image_path)
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError:
        return source
    image = Image.open(source)
    image = ImageOps.grayscale(image)
    if denoise:
        image = image.filter(ImageFilter.MedianFilter(3))
    image = image.point(lambda pixel: 255 if pixel > threshold else 0)
    image = image.resize(
        (image.width * max(1, scale), image.height * max(1, scale)),
        Image.LANCZOS,
    )
    output = Path(output_path) if output_path else source.with_suffix(".pre.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return output


OCR_LIBRARY_PRIORITY = (
    "ddddocr",
    "rapidocr_onnxruntime",
    "easyocr",
    "paddleocr",
    "cnocr",
    "pytesseract",
)
OCR_LIBRARY_PACKAGES = {
    "ddddocr": ("pillow", "ddddocr"),
    "rapidocr_onnxruntime": ("rapidocr_onnxruntime",),
    "easyocr": ("easyocr",),
    "paddleocr": ("paddleocr",),
    "cnocr": ("cnocr",),
    "pytesseract": ("pillow", "pytesseract"),
}
OCR_LIBRARY_ALIASES = {
    "tesseract": "pytesseract",
    "rapidocr": "rapidocr_onnxruntime",
    "paddle": "paddleocr",
    "easy": "easyocr",
    "cn": "cnocr",
}


class OcrCaptchaSolver:
    """Auto-discover and use the strongest installed/installable OCR library."""

    def __init__(
        self,
        tesseract_cmd: str | None = None,
        psm: int = 7,
        whitelist: str | None = None,
        preprocess: bool = True,
        denoise: bool = True,
        scale: int = 2,
        language: str | None = None,
        backend: str = "auto",
        auto_install: bool = True,
        priority: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.tesseract_cmd = tesseract_cmd
        self.psm = psm
        self.whitelist = whitelist
        self.preprocess = preprocess
        self.denoise = denoise
        self.scale = scale
        self.language = language
        self.backend = backend
        self.auto_install = auto_install
        self.priority = tuple(priority) if priority else OCR_LIBRARY_PRIORITY
        self._ddddocr: Any | None = None
        self._rapidocr: Any | None = None
        self._easyocr: Any | None = None
        self._paddleocr: Any | None = None
        self._cnocr: Any | None = None
        self._install_attempted = False

    @property
    def available(self) -> bool:
        return self._backend() is not None

    def _selected_backend(self) -> str | None:
        selected = str(self.backend or "auto").strip().lower()
        if selected in {"", "auto", "adaptive", "smart"}:
            return None
        return OCR_LIBRARY_ALIASES.get(selected, selected)

    def _available(self, library: str) -> bool:
        module_names = {
            "ddddocr": "ddddocr",
            "rapidocr_onnxruntime": "rapidocr_onnxruntime",
            "easyocr": "easyocr",
            "paddleocr": "paddleocr",
            "cnocr": "cnocr",
            "pytesseract": "pytesseract",
        }
        try:
            importlib.import_module(module_names[library])
            if library == "pytesseract":
                importlib.import_module("PIL")
        except (ImportError, KeyError):
            return False
        return True

    def _backend(self) -> str | None:
        selected = self._selected_backend()
        if selected is not None:
            return selected if self._available(selected) else None
        for library in self.priority:
            if self._available(library):
                return library
        return None

    def _install_missing(self) -> None:
        from ensure_web_fetch_dependencies import ensure

        selected = self._selected_backend()
        candidates = [selected] if selected is not None else list(self.priority)
        last_error: Exception | None = None
        for library in candidates:
            packages = OCR_LIBRARY_PACKAGES.get(library)
            if not packages:
                continue
            try:
                ensure(install=True, packages=packages)
            except Exception as exc:
                last_error = exc
                continue
            if self._available(library):
                return
        if last_error is not None:
            raise CaptchaError(f"local OCR auto-install failed: {last_error}")
        raise CaptchaError("local OCR libraries are unavailable after auto-install")

    def solve_image(self, image_path: str | Path) -> CaptchaResult:
        path = Path(image_path)
        if not path.exists():
            raise CaptchaError(f"captcha image not found: {path}")
        backend = self._backend()
        if backend is None and self.auto_install and not self._install_attempted:
            self._install_attempted = True
            self._install_missing()
            backend = self._backend()
        if backend is None:
            raise CaptchaError(
                "no usable local OCR library; install one with "
                "ensure_web_fetch_dependencies.py --ocr-only"
            )
        if backend == "ddddocr":
            return self._solve_ddddocr(path)
        if backend == "pytesseract":
            return self._solve_pytesseract(path)
        if backend == "rapidocr_onnxruntime":
            return self._solve_rapidocr(path)
        if backend == "easyocr":
            return self._solve_easyocr(path)
        if backend == "paddleocr":
            return self._solve_paddleocr(path)
        if backend == "cnocr":
            return self._solve_cnocr(path)
        raise CaptchaError(f"unsupported OCR backend: {backend}")

    def _answer(self, text: str) -> CaptchaResult:
        text = str(text or "").strip()
        if not text:
            raise CaptchaError("local OCR returned an empty answer")
        return CaptchaResult(success=True, task_id="local-ocr", answer=text, raw=text)

    def _solve_ddddocr(self, path: Path) -> CaptchaResult:
        import ddddocr

        if self._ddddocr is None:
            try:
                self._ddddocr = ddddocr.DdddOcr(show_ad=False)
            except TypeError:
                self._ddddocr = ddddocr.DdddOcr()
        with path.open("rb") as handle:
            text = self._ddddocr.classification(handle.read()).strip()
        return self._answer(text)

    def _solve_pytesseract(self, path: Path) -> CaptchaResult:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise CaptchaError(
                "local OCR requires Pillow and pytesseract; pass api_key or install them"
            ) from exc
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        config = f"--psm {int(self.psm)}"
        if self.whitelist:
            config += f" -c tessedit_char_whitelist={self.whitelist}"
        processed: Any = Image.open(path)
        if self.preprocess:
            processed = preprocess_captcha_image(
                path,
                denoise=self.denoise,
                threshold=140,
                scale=self.scale,
            )
        else:
            processed = processed.convert("RGB")
        text = pytesseract.image_to_string(
            processed,
            config=config,
            lang=self.language,
        ).strip()
        return self._answer(text)

    def _solve_rapidocr(self, path: Path) -> CaptchaResult:
        import rapidocr_onnxruntime

        if self._rapidocr is None:
            self._rapidocr = rapidocr_onnxruntime.RapidOCR()
        result, _ = self._rapidocr(str(path))
        text = "".join(str(item[1]) for item in (result or [])).strip()
        return self._answer(text)

    def _solve_easyocr(self, path: Path) -> CaptchaResult:
        import easyocr

        if self._easyocr is None:
            self._easyocr = easyocr.Reader(["ch_sim", "en"], gpu=False)
        result = self._easyocr.readtext(str(path), detail=0, paragraph=True)
        text = "".join(str(item) for item in (result or [])).strip()
        return self._answer(text)

    def _solve_paddleocr(self, path: Path) -> CaptchaResult:
        from paddleocr import PaddleOCR

        if self._paddleocr is None:
            self._paddleocr = PaddleOCR(
                use_angle_cls=True,
                lang="ch",
                show_log=False,
            )
        result = self._paddleocr.ocr(str(path), cls=True)
        parts: list[str] = []
        for page in result or []:
            for line in page or []:
                if isinstance(line, dict):
                    parts.append(str(line.get("text", "")))
                elif isinstance(line, list | tuple) and len(line) >= 2:
                    parts.append(str(line[1][0]))
        return self._answer("".join(parts))

    def _solve_cnocr(self, path: Path) -> CaptchaResult:
        from cnocr import CnOcr

        if self._cnocr is None:
            self._cnocr = CnOcr()
        result = self._cnocr.ocr(str(path))
        text = "".join(item.get("text", "") for item in (result or [])).strip()
        return self._answer(text)


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


class AudioCaptchaSolver:
    """Audio CAPTCHA adapter with provider or local speech-to-text callback."""

    def __init__(
        self,
        provider: CaptchaSolver | None = None,
        transcribe: Any | None = None,
    ) -> None:
        self.provider = provider
        self.transcribe = transcribe

    def solve_audio(self, audio_url_or_path: str | Path) -> CaptchaResult:
        path = Path(audio_url_or_path)
        if not path.exists():
            path = self._download(str(audio_url_or_path))
        if self.transcribe is not None:
            answer = str(self.transcribe(path) or "").strip()
            if not answer:
                raise CaptchaError("audio transcription returned an empty answer")
            return CaptchaResult(success=True, task_id="audio-stt", answer=answer)
        if self.provider is not None:
            return self.provider.solve_audio(path)
        raise CaptchaError("audio CAPTCHA requires a provider or a transcribe callable")

    @staticmethod
    def _download(url: str) -> Path:
        if not url.startswith(("http://", "https://")):
            raise CaptchaError(f"invalid audio CAPTCHA URL: {url}")
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
        except urllib.error.HTTPError as exc:
            raise CaptchaError(f"audio CAPTCHA download failed: {exc.code}") from exc
        tmp = Path(tempfile.gettempdir()) / f"captcha-audio-{uuid.uuid4().hex}.mp3"
        tmp.write_bytes(data)
        return tmp


class MultiCaptchaSolver:
    """Try multiple CAPTCHA providers in order, then fall back if provided."""

    def __init__(
        self,
        providers: list[CaptchaSolver],
        *,
        fallback: Any | None = None,
    ) -> None:
        self.providers = [provider for provider in providers if provider is not None]
        self.fallback = fallback
        self._cooldown: dict[int, float] = {}

    def _solve(self, method: str, *args: Any, **kwargs: Any) -> CaptchaResult:
        errors: list[str] = []
        now = time.time()
        for index, provider in enumerate(self.providers):
            if self._cooldown.get(index, 0.0) > now:
                continue
            fn = getattr(provider, method, None)
            if fn is None:
                continue
            try:
                result = fn(*args, **kwargs)
                self._cooldown.pop(index, None)
                return result
            except CaptchaError as exc:
                self._cooldown[index] = time.time() + 60.0
                errors.append(f"{type(provider).__name__}: {exc}")
        if self.fallback is not None:
            fn = getattr(self.fallback, method, None)
            if fn is not None:
                try:
                    return fn(*args, **kwargs)
                except CaptchaError as exc:
                    errors.append(f"fallback: {exc}")
        raise CaptchaError("all CAPTCHA providers failed: " + "; ".join(errors))

    def status(self) -> list[dict[str, Any]]:
        now = time.time()
        return [
            {
                "provider": type(provider).__name__,
                "available": self._cooldown.get(index, 0.0) <= now,
                "cooldown_until": self._cooldown.get(index),
            }
            for index, provider in enumerate(self.providers)
        ]

    def reset_cooldown(self) -> None:
        self._cooldown.clear()

    def solve_image(self, *args: Any, **kwargs: Any) -> CaptchaResult:
        return self._solve("solve_image", *args, **kwargs)

    def solve_recaptcha_v2(self, *args: Any, **kwargs: Any) -> CaptchaResult:
        return self._solve("solve_recaptcha_v2", *args, **kwargs)

    def solve_hcaptcha(self, *args: Any, **kwargs: Any) -> CaptchaResult:
        return self._solve("solve_hcaptcha", *args, **kwargs)

    def solve_turnstile(self, *args: Any, **kwargs: Any) -> CaptchaResult:
        return self._solve("solve_turnstile", *args, **kwargs)

    def solve_recaptcha_v3(self, *args: Any, **kwargs: Any) -> CaptchaResult:
        return self._solve("solve_recaptcha_v3", *args, **kwargs)

    def solve_geetest(self, *args: Any, **kwargs: Any) -> CaptchaResult:
        return self._solve("solve_geetest", *args, **kwargs)


class _JsonTaskProvider:
    """Shared create-task / poll-result flow for JSON CAPTCHA APIs."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str,
        create_path: str,
        result_path: str,
        timeout: float = 120.0,
        poll_interval: float = 3.0,
        balance_path: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.create_path = create_path.lstrip("/")
        self.result_path = result_path.lstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.balance_path = balance_path

    def _request(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise CaptchaError(
                f"CAPTCHA provider HTTP {exc.code}: {exc.read()[:300]!r}"
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CaptchaError(f"CAPTCHA provider invalid JSON: {raw[:300]}") from exc
        if data.get("errorId"):
            raise CaptchaError(str(data.get("errorDescription") or data.get("error") or "provider error"))
        return data

    def _solve_task(
        self,
        task: dict[str, Any],
        solution_keys: tuple[str, ...],
    ) -> CaptchaResult:
        created = self._request(self.create_path, self._create_payload(task))
        task_id = str(created.get("taskId") or "")
        if not task_id:
            raise CaptchaError(f"CAPTCHA provider did not return taskId: {created}")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            result = self._request(self.result_path, self._result_payload(task_id))
            status = str(result.get("status") or "").lower()
            if status == "ready":
                solution = result.get("solution") or {}
                answer = next(
                    (str(solution.get(key) or "") for key in solution_keys if solution.get(key)),
                    None,
                )
                if answer:
                    return CaptchaResult(
                        success=True,
                        task_id=task_id,
                        answer=answer,
                        raw=json.dumps(result, ensure_ascii=False, default=str),
                    )
                raise CaptchaError(f"CAPTCHA provider returned empty solution: {result}")
            if status in {"failed", "error"}:
                raise CaptchaError(f"CAPTCHA task failed: {result}")
            time.sleep(self.poll_interval)
        raise CaptchaError(f"CAPTCHA task {task_id} timed out")

    def _create_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _result_payload(self, task_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def get_balance(self) -> float:
        """Return the current account balance from a JSON provider."""
        if not self.balance_path:
            raise CaptchaError("this CAPTCHA provider does not expose balance")
        data = self._request(self.balance_path, {"clientKey": self.api_key})
        try:
            return float(data.get("balance") or 0)
        except (TypeError, ValueError) as exc:
            raise CaptchaError(f"invalid CAPTCHA balance response: {data}") from exc


class CapSolverSolver(_JsonTaskProvider):
    """CapSolver adapter for reCAPTCHA, hCaptcha, Turnstile, and image text."""

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url=str(kwargs.pop("base_url", "https://api.capsolver.com")),
            create_path="createTask",
            result_path="getTaskResult",
            timeout=float(kwargs.pop("timeout", 120.0)),
            poll_interval=float(kwargs.pop("poll_interval", 3.0)),
            balance_path="getBalance",
        )

    def _create_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"clientKey": self.api_key, "task": task}

    def _result_payload(self, task_id: str) -> dict[str, Any]:
        return {"clientKey": self.api_key, "taskId": task_id}

    def solve_recaptcha_v2(self, site_key: str, page_url: str, invisible: bool = False) -> CaptchaResult:
        task: dict[str, Any] = {
            "type": "ReCaptchaV2TaskProxyLess",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }
        if invisible:
            task["isInvisible"] = True
        return self._solve_task(task, ("gRecaptchaResponse",))

    def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve_task(
            {
                "type": "HCaptchaTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
            ("gRecaptchaResponse", "token"),
        )

    def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve_task(
            {
                "type": "TurnstileTaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
            ("token",),
        )

    def solve_image(self, image_path: str | Path, **kwargs: Any) -> CaptchaResult:
        path = Path(image_path)
        if not path.exists():
            raise CaptchaError(f"captcha image not found: {path}")
        return self._solve_task(
            {
                "type": "ImageToTextTask",
                "body": _b64encode_file(path),
            },
            ("text",),
        )


class AntiCaptchaSolver(_JsonTaskProvider):
    """AntiCaptcha adapter for reCAPTCHA, hCaptcha, Turnstile, and image text."""

    def __init__(self, api_key: str, **kwargs: Any) -> None:
        super().__init__(
            api_key,
            base_url=str(kwargs.pop("base_url", "https://api.anti-captcha.com")),
            create_path="createTask",
            result_path="getTaskResult",
            timeout=float(kwargs.pop("timeout", 120.0)),
            poll_interval=float(kwargs.pop("poll_interval", 3.0)),
            balance_path="getBalance",
        )

    def _create_payload(self, task: dict[str, Any]) -> dict[str, Any]:
        return {"clientKey": self.api_key, "task": task}

    def _result_payload(self, task_id: str) -> dict[str, Any]:
        return {"clientKey": self.api_key, "taskId": task_id}

    def solve_recaptcha_v2(self, site_key: str, page_url: str, invisible: bool = False) -> CaptchaResult:
        task: dict[str, Any] = {
            "type": "NoCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
        }
        if invisible:
            task["isInvisible"] = True
        return self._solve_task(task, ("gRecaptchaResponse",))

    def solve_hcaptcha(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve_task(
            {
                "type": "HCaptchaTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
            ("gRecaptchaResponse", "token"),
        )

    def solve_turnstile(self, site_key: str, page_url: str) -> CaptchaResult:
        return self._solve_task(
            {
                "type": "TurnstileTaskProxyless",
                "websiteURL": page_url,
                "websiteKey": site_key,
            },
            ("token",),
        )

    def solve_image(self, image_path: str | Path, **kwargs: Any) -> CaptchaResult:
        path = Path(image_path)
        if not path.exists():
            raise CaptchaError(f"captcha image not found: {path}")
        return self._solve_task(
            {
                "type": "ImageToTextTask",
                "body": _b64encode_file(path),
            },
            ("text",),
        )


def build_captcha_provider(config: dict[str, Any] | None = None) -> Any | None:
    """Build the configured third-party CAPTCHA provider or return None."""
    captcha = dict(config or {})
    provider = str(captcha.get("provider") or "2captcha").lower()
    env_key = str(captcha.get("api_key_env") or "CAPTCHA_API_KEY")
    api_key = os.environ.get(env_key) or captcha.get("api_key")
    if not api_key:
        return None
    if provider in {"capsolver", "capsolver_solver"}:
        return CapSolverSolver(
            api_key,
            base_url=str(captcha.get("base_url") or "https://api.capsolver.com"),
        )
    if provider in {"anticaptcha", "anti-captcha"}:
        return AntiCaptchaSolver(
            api_key,
            base_url=str(captcha.get("base_url") or "https://api.anti-captcha.com"),
        )
    return CaptchaSolver(
        api_key,
        base_url=str(captcha.get("base_url") or "https://2captcha.com"),
    )


def _b64encode_file(path: Path) -> str:
    import base64

    return base64.b64encode(path.read_bytes()).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAPTCHA detection and solving helpers")
    parser.add_argument("--html", default=None, help="HTML file to scan for CAPTCHA challenges")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        sample = (
            '<html><body><div class="g-recaptcha" data-sitekey="6Lc_test"></div>'
            '<img src="/captcha.png" alt="captcha"><input name="verify_code"></body></html>'
        )
        challenges = detect_captchas(sample, page_url="https://example.com/login")
        kinds = {challenge.kind for challenge in challenges}
        assert "recaptcha_v2" in kinds and "image" in kinds, kinds
        print("captcha_solver self-test OK")
        return 0
    if not args.html:
        parser.error("--html is required unless --self-test is used")
    html = Path(args.html).read_text(encoding="utf-8")
    challenges = detect_captchas(html)
    print(
        json.dumps(
            [challenge.to_dict() for challenge in challenges],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
