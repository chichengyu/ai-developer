"""Compliant scraping guard for authorized desktop automation.

Provides rate limiting, exponential retry with Retry-After support, a
robots.txt policy, and an adaptive throttle that backs off when the site
signals 403/429/5xx. This reduces the chance of an authorized scraper
being misidentified as abuse; it does not hide automation or bypass blocks.
"""

from __future__ import annotations

import random
import re
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field

_RETRY_STATUSES = (429, 500, 502, 503, 504)
_BLOCK_STATUSES = (403, 429, 500, 502, 503, 504)


class RobotsDenied(RuntimeError):
    """Raised when robots.txt disallows the requested URL."""

    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows {url}")
        self.url = url


@dataclass
class RateLimiter:
    """Minimum interval between requests with optional random jitter."""

    min_interval: float = 1.0
    jitter: float = 0.2
    _last: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._last + self.min_interval - now)
            self._last = now + delay
        if delay:
            time.sleep(delay + random.uniform(0.0, self.jitter))


@dataclass
class RetryPolicy:
    """Exponential backoff for transient HTTP failures."""

    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    retry_on_status: tuple[int, ...] = _RETRY_STATUSES

    def should_retry(self, status: int, attempt: int) -> bool:
        return attempt < self.max_retries and status in self.retry_on_status

    def sleep_before_retry(
        self,
        status: int,
        attempt: int,
        retry_after: float | None = None,
    ) -> None:
        delay = retry_after
        if delay is None:
            delay = min(self.max_delay, self.base_delay * (2**attempt))
        delay = min(self.max_delay, max(0.0, delay))
        time.sleep(delay + random.uniform(0.0, min(1.0, delay * 0.1)))


class AdaptiveThrottle:
    """Raise the pacing delay on block signals and lower it on success."""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        factor: float = 2.0,
    ) -> None:
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.factor = factor
        self._delay = base_delay
        self._lock = threading.Lock()

    @property
    def delay(self) -> float:
        with self._lock:
            return self._delay

    def on_block(self, status: int) -> None:
        if status not in _BLOCK_STATUSES:
            return
        with self._lock:
            self._delay = min(self.max_delay, self._delay * self.factor)

    def on_success(self) -> None:
        with self._lock:
            self._delay = max(self.base_delay, self._delay / self.factor)

    def sleep(self) -> None:
        delay = self.delay
        if delay > 0:
            time.sleep(delay)


class RobotsPolicy:
    """robots.txt allow/deny checks for a fixed user agent."""

    def __init__(self, user_agent: str = "MediaPipeline/1.0") -> None:
        self.user_agent = user_agent
        self._parser = urllib.robotparser.RobotFileParser()
        self._loaded = False
        self._raw = ""

    def load_text(self, text: str) -> None:
        self._raw = text
        self._parser.parse(text.splitlines())
        self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    @property
    def raw(self) -> str:
        """Return the raw robots.txt text used by this policy."""
        return self._raw

    def sitemap_urls(self) -> list[str]:
        """Return explicit `Sitemap:` entries found in robots.txt."""
        return re.findall(r"(?im)^\s*Sitemap\s*:\s*(\S+)", self._raw)

    def can_fetch(self, url: str) -> bool:
        if not self._loaded:
            return True
        return self._parser.can_fetch(self.user_agent, url)

    def crawl_delay(self) -> float:
        if not self._loaded:
            return 0.0
        delay = self._parser.crawl_delay(self.user_agent)
        if delay is not None:
            return float(delay)
        match = re.search(
            r"(?im)^crawl-delay\s*:\s*([0-9.]+)",
            self._raw,
        )
        return float(match.group(1)) if match else 0.0


@dataclass
class RequestPacer:
    """Combines robots, adaptive throttle, and rate limiting before a request."""

    robots: RobotsPolicy | None = None
    throttle: AdaptiveThrottle | None = None
    rate_limiter: RateLimiter | None = None

    def wait(self, url: str) -> None:
        if self.robots is not None:
            if not self.robots.can_fetch(url):
                raise RobotsDenied(url)
            delay = self.robots.crawl_delay()
            if delay > 0:
                time.sleep(delay)
        if self.throttle is not None:
            self.throttle.sleep()
        if self.rate_limiter is not None:
            self.rate_limiter.wait()


def parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header as seconds; HTTP-date is left to the caller."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


if __name__ == "__main__":
    print(
        "desktop-app-dev scrape_guard: import RateLimiter / RetryPolicy / RobotsPolicy / AdaptiveThrottle."
    )
