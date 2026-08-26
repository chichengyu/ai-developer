"""Reusable stealth patches for Playwright/Patchright/Selenium contexts.

The JavaScript patch hides common automation markers from `navigator`,
`window.chrome`, permission queries, plugins, and WebGL vendor strings.
Selenium uses `selenium-stealth` when installed and falls back to CDP.
"""

from __future__ import annotations

from typing import Any

from stealth_patch_bank import compose_patches

STEALTH_JS = compose_patches()


def apply_playwright_stealth(
    context: Any,
    page: Any | None = None,
    values: dict[str, Any] | None = None,
) -> None:
    """Inject stealth JS into a Playwright/Patchright context or page."""
    from stealth_patch_bank import apply_patch_bank

    apply_patch_bank(context, page, values=values)


def apply_selenium_stealth(driver: Any, values: dict[str, Any] | None = None) -> bool:
    """Apply Selenium stealth via selenium-stealth or CDP when possible."""
    try:
        from selenium_stealth import stealth

        stealth(
            driver,
            languages=values.get("languages") if values else ["zh-CN", "zh", "en-US", "en"],
            vendor=values.get("vendor") if values else "Google Inc.",
            platform=values.get("platform") if values else "Win32",
            webgl_vendor=values.get("webgl_vendor") if values else "Intel Inc.",
            renderer=values.get("webgl_renderer") if values else "ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
            fix_hairline=True,
        )
        return True
    except Exception:
        execute_cdp = getattr(driver, "execute_cdp_cmd", None)
        if execute_cdp is None:
            return False
        try:
            execute_cdp(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": compose_patches(values=values)},
            )
            return True
        except Exception:
            return False


if __name__ == "__main__":
    print(len(STEALTH_JS))
