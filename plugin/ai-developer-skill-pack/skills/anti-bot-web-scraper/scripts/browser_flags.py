"""Anti-detect browser launch arguments shared by Selenium engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ANTI_DETECT_ARGS = (
    "--disable-blink-features=AutomationControlled",
    "--disable-automation",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-notifications",
    "--disable-popup-blocking",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-client-side-phishing-detection",
    "--disable-sync",
    "--disable-domain-reliability",
    "--metrics-recording-only",
    "--no-pings",
    "--disable-hang-monitor",
    "--disable-breakpad",
    "--no-crash-upload",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-ipc-flooding-protection",
    "--disable-default-apps",
    "--disable-extensions",
    "--disable-account-consistency",
    "--disable-search-engine-choice-screen",
    "--disable-session-crashed-bubble",
    "--disable-device-discovery-notifications",
    "--disable-features=OptimizationHints,MediaRouter,TranslateUI,"
    "InterestFeedContentSuggestions,PrivacySandboxSettings4,MediaEngagementBubble,"
    "InfiniteSessionRestore",
    "--use-mock-keychain",
    "--no-service-autorun",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--mute-audio",
    "--disable-save-password-bubble",
    "--disable-password-generation",
    "--password-store=basic",
    "--lang=zh-CN",
    "--start-maximized",
    "--window-size=1920,1080",
    "--force-device-scale-factor=1",
    "--disable-component-extensions-with-background-pages",
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
)


@dataclass
class BrowserLaunchProfile:
    """One consistent anti-detect browser launch profile."""

    headless: bool = True
    user_agent: str | None = None
    locale: str = "zh-CN"
    timezone_id: str | None = None
    extra_args: list[str] = field(default_factory=list)
    exclude_switches: list[str] = field(
        default_factory=lambda: ["enable-automation", "enable-logging"]
    )
    prefs: dict[str, Any] = field(
        default_factory=lambda: {
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False,
            "profile.default_content_setting_values.notifications": 2,
        }
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> BrowserLaunchProfile:
        values = dict(data or {})
        return cls(
            headless=bool(values.get("headless", True)),
            user_agent=values.get("user_agent"),
            locale=str(values.get("locale") or "zh-CN"),
            timezone_id=values.get("timezone_id"),
            extra_args=[str(item) for item in values.get("extra_args") or []],
            exclude_switches=[str(item) for item in values.get("exclude_switches") or []],
            prefs=dict(values.get("prefs") or {}),
        )

    def args(self) -> list[str]:
        args = list(ANTI_DETECT_ARGS)
        args.extend(self.extra_args)
        args.append(f"--lang={self.locale}")
        if self.timezone_id:
            args.append(f"--timezone={self.timezone_id}")
        if self.headless:
            args.append("--headless=new")
        if self.user_agent:
            args.append(f"--user-agent={self.user_agent}")
        return list(dict.fromkeys(args))

    def apply_chrome_options(self, options: Any, proxy: str | None = None) -> None:
        for arg in self.args():
            options.add_argument(arg)
        if proxy:
            options.add_argument(f"--proxy-server={proxy}")
        try:
            options.add_experimental_option("excludeSwitches", self.exclude_switches)
            options.add_experimental_option("useAutomationExtension", False)
            options.add_experimental_option("prefs", self.prefs)
        except Exception:
            pass

    def apply_undetected_options(self, options: Any, proxy: str | None = None) -> None:
        for arg in self.args():
            options.add_argument(arg)
        if proxy:
            options.add_argument(f"--proxy-server={proxy}")

    def seleniumbase_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "uc": True,
            "headless": self.headless,
            "incognito": True,
            "locale": self.locale,
        }
        if self.user_agent:
            kwargs["agent"] = self.user_agent
        return kwargs


def default_browser_profile(headless: bool = True) -> BrowserLaunchProfile:
    return BrowserLaunchProfile(headless=headless)


if __name__ == "__main__":
    print(default_browser_profile().args())
