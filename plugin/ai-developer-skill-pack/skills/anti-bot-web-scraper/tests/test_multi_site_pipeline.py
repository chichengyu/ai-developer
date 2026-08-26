"""Tests for parallel multi-site full-site crawling."""

from __future__ import annotations

import http.server
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from multi_site_pipeline import (  # noqa: E402
    _should_retry_result,
    build_site_configs,
    run_site,
    run_site_with_retry,
)
from web_data_pipeline import _SelfTestHandler  # noqa: E402


def test_build_site_configs_isolates_each_url() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        configs = build_site_configs(
            ["https://example.com/a", "https://example.com/b"],
            output_dir=Path(tmp) / "sites",
            max_depth=2,
            max_pages=10,
            crawl_api=True,
            browser=True,
            site_index=True,
            min_interval=1.5,
            jitter=0.3,
            max_retries=3,
            backoff_base=3.0,
            backoff_max=45.0,
        )
        assert len(configs) == 2
        assert configs[0]["subpages"]["seeds"] == ["https://example.com/a"]
        assert configs[0]["api"]["site_index_output"].endswith("site-api-index.json")
        assert configs[0]["subpages"]["min_interval"] == 1.5
        assert configs[0]["api"]["jitter"] == 0.3
        assert configs[0]["api"]["max_retries"] == 3
        assert configs[0]["api"]["backoff_max"] == 45.0
        assert configs[1]["output"] != configs[0]["output"]
        assert configs[0]["summary_output"] != configs[1]["summary_output"]
        assert configs[0]["reverse_output"].endswith("reverse-report.json")
        assert configs[0]["reverse_output"] != configs[1]["reverse_output"]


def test_parallel_site_crawl_runs_end_to_end() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SelfTestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with tempfile.TemporaryDirectory() as tmp:
            configs = build_site_configs(
                [f"{base}/list", f"{base}/sub/list"],
                output_dir=Path(tmp) / "sites",
                max_depth=2,
                max_pages=20,
                site_index=True,
            )
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(run_site, configs))
            assert len(results) == 2
            assert all(result["ok"] for result in results), results
            assert all(result["summary"]["api_specs"] >= 1 for result in results)
            assert sum(result["summary"]["crawl_pages"] for result in results) >= 4
    finally:
        server.shutdown()
        server.server_close()


def test_site_retry_policy_only_retries_on_failure_by_default() -> None:
    assert _should_retry_result({"ok": False}, False) is True
    assert _should_retry_result({"ok": True, "summary": {}}, False) is False
    assert (
        _should_retry_result(
            {
                "ok": True,
                "summary": {
                    "crawl_summary": {"blocked": 2},
                    "api_blocks": 1,
                },
            },
            True,
        )
        is True
    )


def test_run_site_with_retry_recovers_from_transient_failure() -> None:
    calls = {"count": 0}

    def fake_run(_config: dict[str, object]) -> dict[str, object]:
        calls["count"] += 1
        if calls["count"] < 3:
            return {"ok": False, "url": "https://example.com", "error": "transient"}
        return {"ok": True, "url": "https://example.com", "summary": {}}

    with mock.patch("multi_site_pipeline.run_site", side_effect=fake_run):
        result = run_site_with_retry(
            {},
            retries=3,
            delay=0.01,
            backoff=1.0,
        )
    assert result["ok"] is True
    assert result["attempts"] == 3
    assert result["retries"] == 2
