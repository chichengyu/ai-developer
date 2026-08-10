"""Ensure optional web-fetch dependencies for the adaptive fetch stack.

`smart_fetch.py` uses these packages when they are installed:

- `curl_cffi` -- browser TLS/JA3/JA4 + HTTP/2 impersonation
- `tls_client` -- Go TLS fingerprint client
- `cloudscraper` -- Cloudflare JS challenge / Turnstile solving
- `httpx` -- HTTP/2 client
- `h2` -- HTTP/2 protocol support used by httpx
- `patchright` -- undetected Playwright
- `camoufox` -- patched anti-fingerprint Firefox browser
- `scrapling` -- stealth fetcher with built-in Cloudflare solving
- `nodriver` -- CDP-only Chromium automation
- `seleniumbase` -- SeleniumBase UC / CDP mode
- `undetected_chromedriver` -- patched ChromeDriver
- `DrissionPage` -- Chromium automation with a self-developed core
- `selenium` -- Selenium WebDriver with stealth injection
- `cryptography` -- AES decryption for encrypted HLS segments
- `pillow` / `ddddocr` -- optional local image CAPTCHA OCR

The CLI defaults to automatic mode: it checks for missing packages and
installs them with pip. Use `--check` to only report status without
downloading anything, or `--http-only` to skip the stealth-browser packages.
This script deliberately does not download large browser binaries; use
`ensure_browser_binaries.py --install` when a Camoufox browser is needed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

WEB_FETCH_PACKAGES = ("curl_cffi", "tls_client", "cloudscraper", "httpx", "h2")
STEALTH_BROWSER_PACKAGES = ("patchright", "nodriver", "DrissionPage")
SELENIUM_PACKAGES = (
    "selenium",
    "seleniumbase",
    "undetected_chromedriver",
    "webdriver_manager",
    "selenium_stealth",
)
ADVANCED_BROWSER_PACKAGES = ("camoufox", "scrapling", "msgspec")
MEDIA_PACKAGES = ("cryptography",)
OCR_PACKAGES = ("pillow", "ddddocr")
OCR_TESSERACT_PACKAGES = ("pillow", "pytesseract")
ALL_WEB_FETCH_PACKAGES = (
    *WEB_FETCH_PACKAGES,
    *STEALTH_BROWSER_PACKAGES,
    *SELENIUM_PACKAGES,
    *ADVANCED_BROWSER_PACKAGES,
    *MEDIA_PACKAGES,
)
WEB_FETCH_LABELS = {
    "curl_cffi": "browser TLS/JA3/JA4 + HTTP/2 impersonation",
    "tls_client": "Go TLS fingerprint client (tls-client)",
    "cloudscraper": "Cloudflare JS challenge / Turnstile solving",
    "httpx": "HTTP/2 client",
    "h2": "HTTP/2 protocol support",
    "patchright": "undetected Playwright (drop-in sync API)",
    "playwright": "standard Playwright automation fallback",
    "nodriver": "CDP-only Chromium automation, no WebDriver",
    "DrissionPage": "Chromium automation with a self-developed core",
    "selenium": "standard Selenium WebDriver",
    "seleniumbase": "SeleniumBase UC / CDP stealth browser",
    "undetected_chromedriver": "undetected-chromedriver Selenium wrapper",
    "webdriver_manager": "automatic ChromeDriver / GeckoDriver management",
    "selenium_stealth": "Selenium stealth JS / CDP injection",
    "camoufox": "patched anti-fingerprint Firefox browser",
    "scrapling": "Scrapling stealth fetcher (Patchright / Camoufox)",
    "msgspec": "Scrapling dependency for stealth engine config validation",
    "cryptography": "AES decryption for encrypted HLS segments",
    "pillow": "image processing for local CAPTCHA OCR",
    "ddddocr": "self-contained OCR model for local CAPTCHA solving",
    "pytesseract": "Tesseract OCR adapter for local CAPTCHA solving",
    "rapidocr_onnxruntime": "RapidOCR ONNX engine for local CAPTCHA solving",
    "easyocr": "EasyOCR engine for local CAPTCHA solving",
    "paddleocr": "PaddleOCR engine for local CAPTCHA solving",
    "cnocr": "CnOcr engine for Chinese CAPTCHA solving",
}
ProgressFn = Callable[[str, float | None, str], None]


class DependencyInstallError(RuntimeError):
    """Raised when pip cannot install a required web-fetch package."""


def _noop_progress(stage: str, percent: float | None, message: str) -> None:
    print(f"[{stage}] {percent or 0:.0%} {message}")


def _module_available(name: str) -> bool:
    import_name = "PIL" if name.lower() == "pillow" else name
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def check_status(
    packages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return installed status for the requested web-fetch packages."""
    wanted = tuple(packages) if packages else ALL_WEB_FETCH_PACKAGES
    return {
        "python": sys.executable,
        "packages": [
            {
                "name": name,
                "installed": _module_available(name),
                "description": WEB_FETCH_LABELS[name],
            }
            for name in wanted
        ],
        "ready": all(_module_available(name) for name in wanted),
    }


def missing_packages() -> list[str]:
    """Return the subset of web-fetch packages that are not installed."""
    return [name for name in ALL_WEB_FETCH_PACKAGES if not _module_available(name)]


def ensure(
    install: bool = True,
    progress: ProgressFn | None = None,
    packages: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Ensure the web-fetch stack is available, installing when requested."""
    report = progress or _noop_progress
    wanted = tuple(packages) if packages else ALL_WEB_FETCH_PACKAGES
    missing = [name for name in wanted if not _module_available(name)]
    if not missing:
        return check_status(wanted)
    if not install:
        return check_status(wanted)

    report(
        "ensure",
        0.1,
        f"installing missing web-fetch packages: {', '.join(missing)}",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", *missing],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DependencyInstallError(
            f"pip install failed for {', '.join(missing)}: {result.stderr[-500:]}"
        )
    browser_packages = {
        "patchright",
        "nodriver",
        "DrissionPage",
        "selenium",
        "seleniumbase",
        "undetected_chromedriver",
        "camoufox",
        "scrapling",
    }
    if install and any(name in browser_packages for name in wanted):
        from ensure_browser_binaries import ensure as ensure_browser_binaries

        ensure_browser_binaries(install=True, progress=report)
    status = check_status(wanted)
    report("done", 1.0, "web-fetch dependencies ready")
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check or auto-install web-fetch dependencies " "(default: install missing packages)"
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="only report status; do not download anything",
    )
    parser.add_argument(
        "--packages",
        default=None,
        help="comma-separated package subset, e.g. curl_cffi,cloudscraper",
    )
    parser.add_argument(
        "--http-only",
        action="store_true",
        help="only check/install HTTP backends, skip stealth browser packages",
    )
    parser.add_argument(
        "--browser-only",
        action="store_true",
        help="only check/install browser engines, skip HTTP backends",
    )
    parser.add_argument(
        "--media-only",
        action="store_true",
        help="only check/install media processing packages (HLS decryption)",
    )
    parser.add_argument(
        "--ocr-only",
        action="store_true",
        help="only check/install local CAPTCHA OCR packages",
    )
    args = parser.parse_args(argv)
    packages = (
        [item.strip() for item in args.packages.split(",") if item.strip()]
        if args.packages
        else None
    )
    if args.http_only and packages is None:
        packages = list(WEB_FETCH_PACKAGES)
    elif args.browser_only and packages is None:
        packages = [
            *STEALTH_BROWSER_PACKAGES,
            *SELENIUM_PACKAGES,
            *ADVANCED_BROWSER_PACKAGES,
        ]
    elif args.media_only and packages is None:
        packages = list(MEDIA_PACKAGES)
    elif args.ocr_only and packages is None:
        packages = list(OCR_PACKAGES)
    result = ensure(install=not args.check, packages=packages)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ready") or args.check else 1


if __name__ == "__main__":
    raise SystemExit(main())
