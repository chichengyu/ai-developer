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
import json
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
        elif tag in {"div", "iframe", "img", "input"}:
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
    ) -> None:
        key = (kind, site_key or image_url or selector or script_url or "")
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
        elif "hcaptcha.com/1/api.js" in lower:
            add("hcaptcha", script_url=src, confidence=0.6)
        elif "turnstile/v0/api.js" in lower:
            add("turnstile", script_url=src, confidence=0.6)
        elif "geetest" in lower:
            add("geetest", script_url=src, confidence=0.6)

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
        elif tag == "img":
            src = (attrs.get("src") or attrs.get("data-src") or "").strip()
            combined = f"{src} {attrs.get('alt', '')}".lower()
            if any(hint in combined for hint in _CAPTCHA_IMAGE_HINTS):
                image_url = urllib.parse.urljoin(page_url or "", src) if src else None
                captcha_images.append((index, image_url))
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
    ) -> list[tuple[CaptchaChallenge, str]]:
        solved: list[tuple[CaptchaChallenge, str]] = []
        image_index = 0
        for index, challenge in enumerate(challenges):
            if max_challenges is not None and index >= max_challenges:
                break
            image_path = None
            if challenge.kind == "image" and image_paths:
                if image_index < len(image_paths):
                    image_path = image_paths[image_index]
                image_index += 1
            solved.append((challenge, self.solve_challenge(challenge, image_path=image_path)))
        return solved

    def _solve_with_service(
        self,
        challenge: CaptchaChallenge,
        image_path: str | Path | None,
    ) -> str:
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
        elif challenge.kind == "hcaptcha":
            result = self.solver.solve_hcaptcha(challenge.site_key or "", page_url)
        elif challenge.kind == "turnstile":
            result = self.solver.solve_turnstile(challenge.site_key or "", page_url)
        elif challenge.kind == "geetest":
            result = self.solver.solve_geetest(
                challenge.site_key or "",
                challenge.challenge or "",
                page_url,
            )
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


class OcrCaptchaSolver:
    """Local OCR adapter that uses optional Pillow + pytesseract."""

    def __init__(
        self,
        tesseract_cmd: str | None = None,
        psm: int = 7,
        whitelist: str | None = None,
        preprocess: bool = True,
    ) -> None:
        self.tesseract_cmd = tesseract_cmd
        self.psm = psm
        self.whitelist = whitelist
        self.preprocess = preprocess

    @property
    def available(self) -> bool:
        try:
            import PIL  # noqa: F401
            import pytesseract  # noqa: F401
        except ImportError:
            return False
        return True

    def solve_image(self, image_path: str | Path) -> CaptchaResult:
        try:
            import pytesseract
            from PIL import Image
        except ImportError as exc:
            raise CaptchaError(
                "local OCR requires Pillow and pytesseract; pass api_key or install them"
            ) from exc
        path = Path(image_path)
        if not path.exists():
            raise CaptchaError(f"captcha image not found: {path}")
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
        config = f"--psm {int(self.psm)}"
        if self.whitelist:
            config += f" -c tessedit_char_whitelist={self.whitelist}"
        processed: Any = Image.open(path)
        if self.preprocess:
            from PIL import ImageOps

            processed = ImageOps.grayscale(processed)
            processed = processed.point(lambda pixel: 255 if pixel > 140 else 0)
            processed = processed.resize((processed.width * 2, processed.height * 2))
        text = pytesseract.image_to_string(processed, config=config).strip()
        if not text:
            raise CaptchaError("local OCR returned an empty answer")
        return CaptchaResult(success=True, task_id="local-ocr", answer=text, raw=text)


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
