"""Tests for WebSocket / EventSource parsing and real-time frame capture."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from api_client import ApiSpec  # noqa: E402
from browser_session import BrowserSession, NetworkCaptureOptions, NetworkEntry  # noqa: E402
from page_data_parser import analyze_page  # noqa: E402
from param_augmenter import collect_page_param_hints  # noqa: E402
from web_data_pipeline import WebDataPipeline, _config_from_url  # noqa: E402


def test_page_parser_discovers_websocket_and_eventsource() -> None:
    html = (
        '<script>'
        'const ws = new WebSocket("wss://example.com/socket");'
        'ws.send(JSON.stringify({room:"a"}));'
        'const es = new EventSource("/api/events?room=a");'
        "</script>"
    )
    analysis = analyze_page(html, "https://example.com/")
    ws = next(endpoint for endpoint in analysis.api_endpoints if endpoint.method == "WS")
    assert ws.url == "wss://example.com/socket"
    assert ws.body == {"room": "a"}
    sse = next(endpoint for endpoint in analysis.api_endpoints if endpoint.method == "SSE")
    assert sse.url == "https://example.com/api/events?room=a"
    assert sse.content_type == "text/event-stream"
    assert len(analysis.streams) >= 2


def test_browser_session_captures_websocket_frames() -> None:
    class FakePage:
        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}

        def on(self, event: str, handler: object) -> None:
            self.handlers[event] = handler

    class FakeWebSocket:
        url = "wss://example.com/socket"

        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}

        def on(self, event: str, handler: object) -> None:
            self.handlers[event] = handler

    session = BrowserSession(headless=True)
    session.page = FakePage()
    session.start_capture(NetworkCaptureOptions())
    websocket = FakeWebSocket()
    session._on_websocket(websocket)
    websocket.handlers["framesent"]('{"type":"join","room":"a"}')
    websocket.handlers["framereceived"]('{"type":"data","id":1}')
    entries = session.stop_capture()
    frames = [entry for entry in entries if entry.direction]
    assert len(frames) == 2
    assert frames[0].direction == "sent"
    assert frames[0].frame_data == {"type": "join", "room": "a"}
    assert frames[1].direction == "received"
    assert frames[1].frame_data == {"type": "data", "id": 1}


def test_browser_session_captures_sse_events() -> None:
    session = BrowserSession(headless=True)
    session._capture_options = NetworkCaptureOptions()
    session._network = []
    entry = NetworkEntry(
        method="GET",
        url="https://example.com/events",
        resource_type="eventsource",
    )
    session._record_sse_events(
        entry,
        'event: update\ndata: {"id":1}\n\nid: 2\ndata: hello\n\n',
    )
    frames = [item for item in session._network if item.direction == "received"]
    assert len(frames) == 2
    assert frames[0].frame_data["event"] == "update"
    assert frames[0].frame_data["data"] == {"id": 1}
    assert frames[1].frame_data["id"] == "2"
    assert frames[1].frame_data["data"] == "hello"


def test_web_pipeline_skips_stream_specs_for_http_fetch() -> None:
    assert WebDataPipeline._is_stream_spec(
        ApiSpec(method="WS", url="wss://example.com/socket", source="websocket")
    )
    assert WebDataPipeline._is_stream_spec(
        ApiSpec(method="SSE", url="https://example.com/events", source="event-source")
    )
    assert not WebDataPipeline._is_stream_spec(
        ApiSpec(method="GET", url="https://example.com/api/items")
    )


def test_page_parser_discovers_dom_and_js_events() -> None:
    html = (
        '<button onclick="fetch(\'/api/click\')">x</button>'
        '<script>document.addEventListener("click", () => fetch("/api/listener"));</script>'
    )
    analysis = analyze_page(html, "https://example.com/")
    html_events = [event for event in analysis.events if event["source"] == "html"]
    js_events = [event for event in analysis.events if event["source"] == "js"]
    assert any(
        event["event"] == "click" and "/api/click" in event["handler"]
        for event in html_events
    )
    assert any(
        event["event"] == "click"
        and any("/api/listener" in url for url in event["handler_urls"])
        for event in js_events
    )


def test_url_mode_config_covers_full_site_auto_crawl() -> None:
    config = _config_from_url(
        "https://example.com",
        max_depth=2,
        max_pages=50,
        crawl_api=True,
        site_index="state/site-index.json",
    )
    assert config["subpages"]["seeds"] == ["https://example.com"]
    assert config["subpages"]["max_depth"] == 2
    assert config["subpages"]["max_pages"] == 50
    assert config["subpages"]["crawl_api_endpoints"] is True
    assert config["subpages"]["skip_blocked"] is False
    assert config["subpages"]["block_retries"] == 2
    assert config["api"]["auto_augment_params"] is True
    assert config["api"]["site_index_output"] == "state/site-index.json"


def test_url_mode_config_can_enable_browser_events_and_storage() -> None:
    config = _config_from_url(
        "https://example.com",
        browser=True,
        trigger_events=True,
        capture_storage=True,
    )
    assert config["browser"]["enabled"] is True
    assert "click" in config["browser"]["trigger_events"]
    assert config["browser"]["capture_storage"] is True


def test_browser_session_captures_storage_and_triggers_events() -> None:
    class FakeContext:
        def cookies(self) -> list[dict[str, str]]:
            return [{"name": "sid", "value": "abc"}]

        def storage_state(self) -> dict[str, object]:
            return {"origins": []}

    class FakePage:
        def evaluate(self, script: str) -> object:
            if "localStorage" in script:
                return {"room": "a"}
            return [{"tag": "BUTTON", "event": "click"}]

    session = BrowserSession(headless=True)
    session.context = FakeContext()
    session.page = FakePage()
    storage = session.capture_storage()
    assert storage["local"] == {"room": "a"}
    assert storage["cookies"][0]["name"] == "sid"
    assert session.trigger_page_events() == [{"tag": "BUTTON", "event": "click"}]


def test_storage_values_feed_param_hints() -> None:
    hints = collect_page_param_hints(
        "https://example.com/",
        None,
        storage={
            "origins": [
                {
                    "localStorage": [
                        {"name": "room", "value": "a"},
                    ]
                }
            ],
            "local": {"token": "x"},
        },
    )
    assert hints["room"] == ["a"]
    assert hints["token"] == ["x"]
