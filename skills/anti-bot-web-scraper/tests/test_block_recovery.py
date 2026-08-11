"""Tests for blocked-page recovery and request-level block retries."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api_client import ApiClient, ApiFetchResult, ApiResponse, ApiSpec  # noqa: E402
from deep_crawler import CrawlConfig, CrawledResponse, DeepCrawler  # noqa: E402
from scrape_guard import RetryPolicy  # noqa: E402
from smart_fetch import SmartFetchSession  # noqa: E402


def test_retry_policy_can_retry_block_statuses() -> None:
    policy = RetryPolicy(max_retries=2, retry_on_block=True)
    assert policy.should_retry(403, 0) is True
    assert policy.should_retry(429, 0) is True
    assert policy.should_retry(403, 2) is False
    conservative = RetryPolicy(max_retries=2, retry_on_block=False)
    assert conservative.should_retry(403, 0) is False


def test_smart_fetch_can_rotate_backend() -> None:
    session = SmartFetchSession(
        backend="auto",
        auto_install_dependencies=False,
    )
    backend = session.rotate_backend()
    assert backend is not None
    assert backend in session._ordered_backends()


def test_smart_fetch_block_recovery_rotates_proxy_and_backend() -> None:
    session = SmartFetchSession(
        backend="auto",
        auto_install_dependencies=False,
    )
    session.proxy_pool = mock.Mock()
    session.clear_pinned_proxy = mock.Mock()
    session.rotate_backend = mock.Mock(return_value="httpx")
    session._recover_blocked_identity()
    session.clear_pinned_proxy.assert_called_once()
    session.rotate_backend.assert_called_once()
    session.proxy_pool.report_failure.assert_called_once()


def test_api_client_retries_blocked_response_with_recovery() -> None:
    client = ApiClient(
        backend="standard",
        block_retries=1,
        block_retry_delay=0.0,
        block_retry_backoff=1.0,
    )
    client._recover_blocked_identity = mock.Mock()
    calls = {"count": 0}

    def fake_fetch(_spec: ApiSpec, timeout: float | None = None):
        calls["count"] += 1
        if calls["count"] == 1:
            return (
                {"challenge": "x"},
                1,
                ApiResponse(
                    data={"challenge": "x"},
                    status=403,
                    headers={},
                    duration_ms=1,
                ),
            )
        return (
            {"items": [{"id": 1}]},
            1,
            ApiResponse(
                data={"items": [{"id": 1}]},
                status=200,
                headers={"Content-Type": "application/json"},
                duration_ms=1,
            ),
        )

    client._fetch_with_pages = fake_fetch
    result = client._fetch_result(
        ApiSpec(method="GET", url="https://example.com/api/items")
    )
    assert result.error is None
    assert result.data == {"items": [{"id": 1}]}
    client._recover_blocked_identity.assert_called_once()


def test_api_fetch_result_marks_blocked_api_risky_ultimate() -> None:
    client = ApiClient(backend="standard", block_retries=0)

    def fake_fetch(_spec: ApiSpec, timeout: float | None = None):
        return (
            {"challenge": "x"},
            1,
            ApiResponse(
                data={"challenge": "x"},
                status=403,
                headers={},
                duration_ms=1,
            ),
        )

    client._fetch_with_pages = fake_fetch
    result = client._fetch_result(
        ApiSpec(method="GET", url="https://example.com/api/items")
    )
    assert result.error is not None
    assert result.risky is True
    assert result.stealth_mode == "ultimate"
    assert result.to_dict()["risky"] is True


def test_api_fetch_all_resets_session_after_risky_only() -> None:
    client = ApiClient(backend="standard")
    risky_spec = ApiSpec(method="GET", url="https://example.com/api/a")
    clean_spec = ApiSpec(method="GET", url="https://example.com/api/b")
    risky = ApiFetchResult(
        spec=risky_spec,
        error="blocked",
        security={"blocked": True},
        risky=True,
        stealth_mode="ultimate",
    )
    clean = ApiFetchResult(
        spec=clean_spec,
        data={"ok": True},
        risky=False,
        stealth_mode="adaptive",
    )
    client._fetch_result = mock.Mock(side_effect=[risky, clean])
    new_session = mock.Mock()
    client._new_session = mock.Mock(return_value=new_session)

    results = client.fetch_all([risky_spec, clean_spec])

    assert results == [risky, clean]
    client._fetch_result.assert_has_calls(
        [mock.call(risky_spec), mock.call(clean_spec)]
    )
    client._new_session.assert_called_once()
    assert client.session is new_session


def test_deep_crawler_recovers_blocked_page() -> None:
    calls = {"count": 0}

    def fake_fetch(url: str) -> CrawledResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            return CrawledResponse(
                url=url,
                status=403,
                headers={},
                body=b"blocked",
            )
        return CrawledResponse(
            url=url,
            status=200,
            headers={},
            body=b"<html><a href='/sub'>sub</a></html>",
        )

    config = CrawlConfig(
        seeds=["https://example.com/"],
        max_depth=0,
        max_pages=5,
        same_host=True,
        sitemap=False,
        respect_robots=False,
        skip_blocked=False,
        block_retries=2,
        block_retry_delay=0.01,
        block_retry_backoff=1.0,
    )
    result = DeepCrawler(config, fetch_page=fake_fetch).crawl()
    page = result.pages[0]
    assert page.blocked is False
    assert page.recovery
    assert page.recovery[-1]["recovered"] is True
    assert result.summary()["recovered_pages"] == 1
    assert result.summary()["block_recoveries"] == 1


def test_blocked_page_is_kept_when_skip_is_disabled() -> None:
    config = CrawlConfig(
        seeds=["https://example.com/"],
        max_depth=0,
        max_pages=5,
        same_host=True,
        sitemap=False,
        respect_robots=False,
        skip_blocked=False,
        block_retries=0,
    )
    result = DeepCrawler(
        config,
        fetch_page=lambda url: CrawledResponse(
            url=url,
            status=403,
            headers={},
            body=b"blocked",
        ),
    ).crawl()
    assert len(result.pages) == 1
    assert result.pages[0].blocked is True
    assert result.pages[0].skipped_reason is None
