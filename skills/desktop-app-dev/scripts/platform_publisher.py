"""Platform publisher adapter interface with retry support.

Each platform gets one adapter that implements `login`, `upload`, and
`publish`. The `RetryPublisher` wrapper adds idempotent retries around the
adapter so transient upload failures do not lose the task.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from media_downloader import CancelToken


@dataclass
class PublishRequest:
    title: str
    file_path: Path
    description: str = ""
    tags: list[str] = field(default_factory=list)
    cover_path: Path | None = None
    category: str | None = None
    visibility: str = "public"
    extra: dict = field(default_factory=dict)


@dataclass
class PublishProgress:
    stage: str
    percent: float | None
    uploaded_bytes: int
    total_bytes: int | None
    message: str = ""


@dataclass
class PublishResult:
    platform: str
    item_id: str
    url: str
    raw: dict = field(default_factory=dict)


class Publisher(ABC):
    """Base class for one publishing platform."""

    @abstractmethod
    def login(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def upload(
        self,
        request: PublishRequest,
        progress: Callable[[PublishProgress], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    def publish(self, result: PublishResult) -> PublishResult:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class RetryPublisher(Publisher):
    """Wraps a Publisher with bounded, exponential-backoff retries."""

    def __init__(
        self,
        inner: Publisher,
        attempts: int = 3,
        backoff_seconds: float = 2.0,
    ) -> None:
        self.inner = inner
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds

    def login(self) -> None:
        self._with_retry(self.inner.login)

    def upload(
        self,
        request: PublishRequest,
        progress: Callable[[PublishProgress], None] | None = None,
        cancel: CancelToken | None = None,
    ) -> PublishResult:
        return self._with_retry(lambda: self.inner.upload(request, progress, cancel))

    def publish(self, result: PublishResult) -> PublishResult:
        return self._with_retry(lambda: self.inner.publish(result))

    def close(self) -> None:
        self.inner.close()

    def _with_retry(self, operation: Callable):
        last_error: Exception | None = None
        for attempt in range(self.attempts):
            try:
                return operation()
            except Exception as exc:
                last_error = exc
                if attempt < self.attempts - 1:
                    time.sleep(self.backoff_seconds * (2**attempt))
        assert last_error is not None
        raise last_error


if __name__ == "__main__":
    print(
        "desktop-app-dev platform_publisher: subclass PlatformPublisher to add a publish adapter."
    )
