"""Tests for JS request body/params/GraphQL endpoint parsing."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api_client import build_api_specs  # noqa: E402
from page_data_parser import analyze_page  # noqa: E402


def test_fetch_post_body_is_parsed() -> None:
    html = (
        '<script>fetch("/api/login", {method:"POST", '
        'headers:{"Content-Type":"application/json"}, '
        'body: JSON.stringify({user:"a", pass:"b"})})</script>'
    )
    analysis = analyze_page(html, "https://example.com/")
    login = next(endpoint for endpoint in analysis.api_endpoints if endpoint.method == "POST")
    assert login.body == {"user": "a", "pass": "b"}
    assert login.content_type == "application/json"


def test_axios_post_body_and_get_params_are_parsed() -> None:
    html = (
        '<script>'
        'axios.post("/api/items", {name:"x", price:10});'
        'axios.get("/api/items", {params:{page:1, size:20}});'
        "</script>"
    )
    analysis = analyze_page(html, "https://example.com/")
    post = next(endpoint for endpoint in analysis.api_endpoints if endpoint.method == "POST")
    assert post.body == {"name": "x", "price": 10}
    get = next(endpoint for endpoint in analysis.api_endpoints if endpoint.method == "GET")
    assert get.params == {"page": 1, "size": 20}


def test_graphql_operation_is_attached_to_endpoint() -> None:
    html = (
        '<script>'
        'const QUERY = `query Items($page: Int!) { items(page: $page) { id } }`;'
        'fetch("/graphql", {method:"POST", body: JSON.stringify({query: QUERY})});'
        "</script>"
    )
    analysis = analyze_page(html, "https://example.com/")
    graphql = next(
        endpoint for endpoint in analysis.api_endpoints if endpoint.url.endswith("/graphql")
    )
    assert graphql.method == "POST"
    assert "query Items" in graphql.body["query"]
    assert "variables" in graphql.body


def test_static_spec_keeps_body_params_and_content_type() -> None:
    html = (
        '<script>'
        'fetch("/api/login", {method:"POST", headers:{"Content-Type":"application/json"}, '
        'body: JSON.stringify({user:"a"})});'
        "axios.get('/api/items', {params:{page:1}});"
        "</script>"
    )
    capture = {
        "url": "https://example.com/",
        "analysis": analyze_page(html, "https://example.com/"),
    }
    specs = build_api_specs(capture, include_captured=False, include_static=True)
    login = next(spec for spec in specs if spec.method == "POST")
    assert login.body == {"user": "a"}
    assert login.content_type == "application/json"
    items = next(spec for spec in specs if spec.params and "page" in spec.params)
    assert items.params["page"] == 1
