"""Tests for deep crawler API endpoint fetching and nested API discovery."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from deep_crawler import CrawlConfig, CrawledResponse, DeepCrawler  # noqa: E402
from url_store import UrlDeduplicator  # noqa: E402


def _fake_fetch(url: str) -> CrawledResponse:
    if url == "https://example.com/":
        body = b'<html><script>fetch("/api/list")</script></html>'
    elif url == "https://example.com/api/list":
        body = b'{"next_url":"/api/next","items":[{"id":1}]}'
    elif url == "https://example.com/api/next":
        body = b'{"items":[{"id":2}]}'
    else:
        return CrawledResponse(url=url, status=404, headers={}, body=b"")
    return CrawledResponse(url=url, status=200, headers={"Content-Type": "application/json"}, body=body)


def test_crawl_fetches_apis_and_discovers_nested_endpoints() -> None:
    config = CrawlConfig(
        seeds=["https://example.com/"],
        max_depth=0,
        max_pages=10,
        same_host=True,
        sitemap=False,
        respect_robots=False,
        crawl_api_endpoints=True,
        max_api_calls=10,
    )
    result = DeepCrawler(config, fetch_page=_fake_fetch).crawl()
    page = result.pages[0]
    assert page.status == 200
    assert len(page.api_responses) == 2
    assert "https://example.com/api/next" in page.api_response_urls
    assert any(
        endpoint.get("source") == "response-url"
        and endpoint.get("url") == "https://example.com/api/next"
        for endpoint in page.api_endpoints
    )
    assert result.summary()["api_responses"] == 2
    assert result.summary()["api_response_urls"] == 1


def test_crawl_api_disabled_does_not_fetch_endpoints() -> None:
    config = CrawlConfig(
        seeds=["https://example.com/"],
        max_depth=0,
        max_pages=10,
        same_host=True,
        sitemap=False,
        respect_robots=False,
        crawl_api_endpoints=False,
    )
    result = DeepCrawler(config, fetch_page=_fake_fetch).crawl()
    page = result.pages[0]
    assert page.api_responses == []
    assert page.api_response_urls == []


def test_crawl_records_streams_files_and_subtitles() -> None:
    def media_fetch(url: str) -> CrawledResponse:
        body = b"""
        <html>
          <a href="/v.m3u8">hls</a>
          <a href="/v.mpd">dash</a>
          <a href="/v.ism/Manifest">smooth</a>
          <a href="/subs.vtt">subtitle</a>
          <a href="/doc.pdf">pdf</a>
          <link rel="stylesheet" href="/app.css">
          <script src="/app.js"></script>
          <script>
            new EventSource("/events");
            new WebSocket("wss://example.com/socket");
          </script>
        </html>
        """
        return CrawledResponse(
            url=url,
            status=200,
            headers={"Content-Type": "text/html"},
            body=body,
        )

    config = CrawlConfig(
        seeds=["https://example.com/"],
        max_depth=0,
        max_pages=10,
        same_host=True,
        sitemap=False,
        respect_robots=False,
    )
    result = DeepCrawler(config, fetch_page=media_fetch).crawl()
    media = result.pages[0].media
    assert media["hls"] == ["https://example.com/v.m3u8"]
    assert media["dash"] == ["https://example.com/v.mpd"]
    assert media["smooth"] == ["https://example.com/v.ism/Manifest"]
    assert media["subtitles"] == ["https://example.com/subs.vtt"]
    assert media["files"] == ["https://example.com/doc.pdf"]
    assert result.pages[0].assets["css"] == ["https://example.com/app.css"]
    assert result.pages[0].assets["js"] == ["https://example.com/app.js"]
    assert any(item["method"] == "SSE" for item in result.pages[0].streams)
    assert any(item["method"] == "WS" for item in result.pages[0].streams)
    assert result.summary()["files"] == 1
    assert result.summary()["subtitles"] == 1
    assert result.summary()["css"] == 1
    assert result.summary()["js"] == 1
    assert result.summary()["streams"] >= 2


def test_crawl_persists_discovered_urls() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store_path = str(Path(tmp) / "urls.sqlite3")
        jsonl_path = str(Path(tmp) / "crawl.jsonl")
        config = CrawlConfig(
            seeds=["https://example.com/"],
            max_depth=0,
            max_pages=10,
            same_host=True,
            sitemap=False,
            respect_robots=False,
            url_store_path=store_path,
            jsonl_path=jsonl_path,
        )
        result = DeepCrawler(config, fetch_page=_fake_fetch).crawl()
        assert result.url_store_seen >= 1
        assert result.jsonl_lines >= 1
        with UrlDeduplicator(store_path) as store:
            assert store.contains("https://example.com/")
        assert "https://example.com/" in Path(jsonl_path).read_text(encoding="utf-8")


def test_crawl_jsonl_includes_failed_pages() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        jsonl_path = str(Path(tmp) / "crawl.jsonl")

        def error_fetch(url: str) -> CrawledResponse:
            raise RuntimeError("boom")

        config = CrawlConfig(
            seeds=["https://example.com/"],
            max_depth=0,
            max_pages=10,
            same_host=True,
            sitemap=False,
            respect_robots=False,
            jsonl_path=jsonl_path,
        )
        result = DeepCrawler(config, fetch_page=error_fetch).crawl()
        assert result.jsonl_lines >= 1
        assert "boom" in Path(jsonl_path).read_text(encoding="utf-8")
