"""Tests for automatic subpage API parameter augmentation."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api_client import ApiSpec  # noqa: E402
from page_data_parser import analyze_page  # noqa: E402
from param_augmenter import (  # noqa: E402
    augment_specs,
    build_site_api_index,
    collect_page_param_hints,
    discover_specs_from_pages,
    extract_api_urls,
)
from stealth_patch_bank import compose_patches  # noqa: E402


def test_collect_page_param_hints_merges_sources() -> None:
    hints = collect_page_param_hints(
        "https://example.com/list?category=books&page=2",
        {
            "api_endpoints": [{"url": "https://example.com/api/items?tag=new"}],
            "json_api_fields": [{"key": "author", "value": "jane"}],
            "pagination": {"page": [{"value": 3}]},
            "form_fields": [{"name": "q", "value": "fantasy"}],
            "embedded_json": [],
        },
        links=["https://example.com/item/1?sort=asc"],
        media_urls=["https://example.com/stream.m3u8?token=media-token"],
        network=[
            {
                "url": "https://example.com/api/items?room=a",
                "frame_data": {"room": "a", "token": "ws-token"},
                "json_data": {"id": 7},
                "body_text": "https://example.com/next?cursor=abc",
            }
        ],
    )
    assert "category" in hints and "books" in hints["category"]
    assert "tag" in hints and "new" in hints["tag"]
    assert "author" in hints and "jane" in hints["author"]
    assert "q" in hints and "fantasy" in hints["q"]
    assert "sort" in hints and "asc" in hints["sort"]
    assert "page" in hints
    assert "token" in hints
    assert "media-token" in hints["token"]
    assert "ws-token" in hints["token"]
    assert "room" in hints and "a" in hints["room"]
    assert "id" in hints and "7" in hints["id"]
    assert "cursor" in hints and "abc" in hints["cursor"]


def test_augment_specs_expands_related_subpage_ids() -> None:
    pages = [
        {
            "url": "https://example.com/sub/item/1",
            "links": [],
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/sub-data?id=1",
                        "source": "fetch",
                    }
                ],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [],
            },
        },
        {
            "url": "https://example.com/sub/item/2",
            "links": [],
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/sub-data?id=2",
                        "source": "fetch",
                    }
                ],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [],
            },
        },
    ]
    specs = [
        ApiSpec(
            method="GET",
            url="https://example.com/api/sub-data",
            params={"id": "1"},
        )
    ]
    output, stats = augment_specs(specs, pages, {"max_variants": 20})
    ids = [spec.params.get("id") for spec in output if spec.params]
    assert "2" in ids, ids
    assert stats.variants >= 1
    assert stats.added_keys >= 1


def test_path_placeholder_fill_and_param_map() -> None:
    pages = [
        {
            "url": "https://example.com/api/items/1",
            "analysis": {"api_endpoints": []},
        }
    ]
    specs = [
        ApiSpec(
            method="GET",
            url="https://example.com/api/items/{id}",
            params={"page": "1"},
        )
    ]
    config = {
        "param_map": [
            {
                "match": "/api/items/",
                "params": {"category": ["a", "b"]},
            }
        ]
    }
    output, _stats = augment_specs(specs, pages, config)
    urls = [spec.url for spec in output]
    assert "https://example.com/api/items/1" in urls
    categories = {spec.params.get("category") for spec in output if spec.params}
    assert "a" in categories
    assert "b" in categories


def test_page_parser_collects_form_fields() -> None:
    html = (
        '<form action="/search" method="get">'
        '<input name="q" value="fantasy">'
        '<input name="page" value="1">'
        "</form>"
    )
    analysis = analyze_page(html, "https://example.com/")
    names = {field.name for field in analysis.form_fields}
    assert names == {"q", "page"}
    assert analysis.form_fields[0].action == "/search"


def test_page_parser_extracts_template_literal_endpoints() -> None:
    html = '<script>fetch(`/api/items/${id}?page=${page}`)</script>'
    analysis = analyze_page(html, "https://example.com/")
    urls = [endpoint.url for endpoint in analysis.api_endpoints]
    assert any("/api/items/{id}" in url for url in urls)


def test_page_parser_extracts_object_style_url() -> None:
    html = '<script>axios({url: "/api/config"})</script>'
    analysis = analyze_page(html, "https://example.com/")
    urls = [endpoint.url for endpoint in analysis.api_endpoints]
    assert any(url.endswith("/api/config") for url in urls)


def _path_pages() -> list[dict[str, object]]:
    return [
        {
            "url": "https://example.com/items/1",
            "links": [],
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/items/1",
                        "source": "fetch",
                    }
                ],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [{"data": {"items": [{"id": "1"}]}}],
            },
        },
        {
            "url": "https://example.com/items/2",
            "links": [],
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/items/2",
                        "source": "fetch",
                    }
                ],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [{"data": {"items": [{"id": "2"}]}}],
            },
        },
    ]


def test_site_api_index_infers_path_template() -> None:
    index = build_site_api_index(_path_pages(), {"max_values_per_param": 10})
    assert index["summary"]["endpoints"] == 2
    assert index["summary"]["templates"] == 1
    assert index["summary"]["pages"] == 2
    assert index["summary"]["param_keys"] >= 1
    assert "id" in index["param_bank"]
    assert index["templates"][0]["placeholders"] == ["id"]


def test_augment_specs_infers_path_template_variants() -> None:
    specs = [
        ApiSpec(
            method="GET",
            url="https://example.com/api/items/1",
        )
    ]
    output, stats = augment_specs(specs, _path_pages(), {"max_variants": 20})
    urls = [spec.url for spec in output]
    assert "https://example.com/api/items/2" in urls
    assert stats.templates >= 1
    assert stats.variants >= 1


def test_response_data_drives_next_round_params() -> None:
    response_pages = [
        {
            "url": "https://example.com/api/list",
            "links": [],
            "analysis": {
                "api_endpoints": [],
                "json_api_fields": [],
                "pagination": {},
                "form_fields": [],
                "embedded_json": [
                    {
                        "data": {
                            "items": [
                                {"id": "10"},
                                {"id": "11"},
                            ]
                        }
                    }
                ],
            },
        }
    ]
    specs = [
        ApiSpec(
            method="GET",
            url="https://example.com/api/detail",
        )
    ]
    output, _stats = augment_specs(specs, response_pages, {"max_variants": 20})
    ids = [spec.params.get("id") for spec in output if spec.params]
    assert "10" in ids
    assert "11" in ids


def test_stealth_patch_bank_media_and_wake_lock() -> None:
    payload = compose_patches()
    assert "MediaCapabilities" in payload
    assert "wakeLock" in payload


def test_extract_api_urls_from_response_data() -> None:
    data = {
        "next_url": "/api/items?page=2",
        "items": [
            {"url": "https://example.com/api/items/1"},
        ],
    }
    urls = extract_api_urls(data, "https://example.com/api/list")
    assert "https://example.com/api/items?page=2" in urls
    assert "https://example.com/api/items/1" in urls


def test_discover_specs_from_response_pages() -> None:
    pages = [
        {
            "url": "https://example.com/api/list",
            "analysis": {
                "api_endpoints": [
                    {
                        "method": "GET",
                        "url": "https://example.com/api/detail/1",
                        "source": "response-url",
                    }
                ]
            },
        }
    ]
    specs = discover_specs_from_pages(pages)
    assert any(spec.url.endswith("/api/detail/1") for spec in specs)
