"""Parallel multi-site full-site crawl orchestrator.

Each URL gets an isolated job: deep crawl all pages/subpages, discover APIs,
events, WebSocket/SSE streams, auto-fill parameters, write a whole-site API
index, and save processed records. Jobs run concurrently with a thread pool.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from web_data_pipeline import WebDataPipeline, _config_from_url


def _site_key_for_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    host = (parts.netloc.lower() or "site").replace(":", "_")
    path = parts.path.strip("/").replace("/", "_") or "root"
    return f"{host}-{path}"[:120]


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base or {})
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_config(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_site_configs(
    urls: list[str],
    *,
    output_dir: str | Path,
    max_depth: int = 3,
    max_pages: int = 200,
    crawl_api: bool = False,
    browser: bool = False,
    trigger_events: bool = False,
    capture_storage: bool = False,
    site_index: bool = False,
    base_config: dict[str, Any] | None = None,
    min_interval: float = 1.0,
    jitter: float = 0.5,
    max_retries: int = 2,
    backoff_base: float = 2.0,
    backoff_max: float = 60.0,
    respect_robots: bool = True,
    skip_blocked: bool = False,
    block_retries: int = 2,
    block_retry_delay: float = 2.0,
    block_retry_backoff: float = 2.0,
    rotate_proxy_on_block: bool = True,
    retry_on_block: bool = True,
    alternate_on_block: bool = True,
    browser_on_block: bool = False,
) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    for url in urls:
        site_dir = root / _site_key_for_url(url)
        site_dir.mkdir(parents=True, exist_ok=True)
        config = _config_from_url(
            url,
            max_depth=max_depth,
            max_pages=max_pages,
            crawl_api=crawl_api,
            browser=browser,
            trigger_events=trigger_events,
            capture_storage=capture_storage,
            min_interval=min_interval,
            jitter=jitter,
            max_retries=max_retries,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
            respect_robots=respect_robots,
            skip_blocked=skip_blocked,
            block_retries=block_retries,
            block_retry_delay=block_retry_delay,
            block_retry_backoff=block_retry_backoff,
            rotate_proxy_on_block=rotate_proxy_on_block,
            retry_on_block=retry_on_block,
            alternate_on_block=alternate_on_block,
            browser_on_block=browser_on_block,
        )
        if base_config:
            config = merge_config(config, base_config)
        config["output"] = str(site_dir / "data.json")
        config["summary_output"] = str(site_dir / "summary.json")
        config["_site_url"] = url
        config["_site_dir"] = str(site_dir)
        config.setdefault("api", {})
        if site_index:
            config["api"]["site_index_output"] = str(site_dir / "site-api-index.json")
        configs.append(config)
    return configs


def run_site(config: dict[str, Any]) -> dict[str, Any]:
    url = str(config.get("_site_url") or "")
    try:
        pipeline = WebDataPipeline(config, output=config.get("output"))
        summary = pipeline.run()
        report = pipeline.final_summary_report(summary)
        summary_output = config.get("summary_output")
        if summary_output:
            from run_summary import write_report

            write_report(report, summary_output)
        return {
            "url": url,
            "ok": True,
            "output": config.get("output"),
            "site_index": config.get("api", {}).get("site_index_output"),
            "summary": summary,
            "report": report,
        }
    except Exception as exc:
        return {
            "url": url,
            "ok": False,
            "error": str(exc),
            "output": config.get("output"),
            "summary": None,
            "report": None,
        }


def _should_retry_result(
    result: dict[str, Any],
    retry_on_blocked: bool,
) -> bool:
    if not result.get("ok"):
        return True
    if not retry_on_blocked:
        return False
    summary = result.get("summary") or {}
    crawl = summary.get("crawl_summary") or {}
    blocked = int(crawl.get("blocked", 0) or 0)
    api_blocks = int(summary.get("api_blocks", 0) or 0)
    return (blocked + api_blocks) > 0


def run_site_with_retry(
    config: dict[str, Any],
    *,
    retries: int = 1,
    delay: float = 5.0,
    backoff: float = 2.0,
    retry_on_blocked: bool = False,
) -> dict[str, Any]:
    attempts = 1
    result = run_site(config)
    while attempts <= retries and _should_retry_result(result, retry_on_blocked):
        attempts += 1
        wait = delay * (backoff ** (attempts - 2))
        time.sleep(wait + random.uniform(0.0, min(1.0, wait * 0.1)))
        result = run_site(config)
    result["attempts"] = attempts
    result["retries"] = attempts - 1
    return result


def _self_test() -> None:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        configs = build_site_configs(
            ["https://example.com/a", "https://example.com/b"],
            output_dir=Path(tmp) / "sites",
            max_depth=2,
            max_pages=10,
            crawl_api=True,
            browser=True,
            site_index=True,
        )
        assert len(configs) == 2
        assert configs[0]["subpages"]["seeds"] == ["https://example.com/a"]
        assert configs[0]["api"]["site_index_output"].endswith("site-api-index.json")
        assert configs[1]["output"] != configs[0]["output"]
    print("multi_site_pipeline self-test OK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crawl multiple sites in parallel with full-site parsing."
    )
    parser.add_argument("--url", action="append", default=[], help="site URL (repeatable)")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--output-dir", default="state/multi-site")
    parser.add_argument("--combined-output", default="state/multi-site/combined.json")
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--crawl-api", action="store_true")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--trigger-events", action="store_true")
    parser.add_argument("--capture-storage", action="store_true")
    parser.add_argument("--site-index", action="store_true")
    parser.add_argument("--config", default=None, help="base JSON config merged into every job")
    parser.add_argument("--min-interval", type=float, default=1.0)
    parser.add_argument("--jitter", type=float, default=0.5)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--backoff-base", type=float, default=2.0)
    parser.add_argument("--backoff-max", type=float, default=60.0)
    parser.add_argument("--no-robots", action="store_true")
    parser.add_argument("--site-retries", type=int, default=1)
    parser.add_argument("--site-retry-delay", type=float, default=5.0)
    parser.add_argument("--site-retry-backoff", type=float, default=2.0)
    parser.add_argument("--retry-on-blocked", action="store_true")
    parser.add_argument("--block-retries", type=int, default=2)
    parser.add_argument("--block-retry-delay", type=float, default=2.0)
    parser.add_argument("--block-retry-backoff", type=float, default=2.0)
    parser.add_argument("--no-proxy-rotate", action="store_true")
    parser.add_argument("--no-retry-on-block", action="store_true")
    parser.add_argument("--no-alternate", action="store_true")
    parser.add_argument("--browser-fallback", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    if not args.url:
        parser.error("--url is required unless --self-test is used")

    base_config = None
    if args.config:
        base_config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    configs = build_site_configs(
        args.url,
        output_dir=args.output_dir,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        crawl_api=args.crawl_api,
        browser=args.browser,
        trigger_events=args.trigger_events,
        capture_storage=args.capture_storage,
        site_index=args.site_index,
        base_config=base_config,
        min_interval=args.min_interval,
        jitter=args.jitter,
        max_retries=args.max_retries,
        backoff_base=args.backoff_base,
        backoff_max=args.backoff_max,
        respect_robots=not args.no_robots,
        skip_blocked=False,
        block_retries=args.block_retries,
        block_retry_delay=args.block_retry_delay,
        block_retry_backoff=args.block_retry_backoff,
        rotate_proxy_on_block=not args.no_proxy_rotate,
        retry_on_block=not args.no_retry_on_block,
        alternate_on_block=not args.no_alternate,
        browser_on_block=args.browser_fallback,
    )
    workers = args.workers or min(4, len(configs))
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [
            pool.submit(
                run_site_with_retry,
                config,
                retries=args.site_retries,
                delay=args.site_retry_delay,
                backoff=args.site_retry_backoff,
                retry_on_blocked=args.retry_on_blocked,
            )
            for config in configs
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    ok = [result for result in results if result["ok"]]
    failed = [result for result in results if not result["ok"]]
    combined = {
        "sites": results,
        "summary": {
            "sites": len(results),
            "ok": len(ok),
            "failed": len(failed),
            "site_retries": sum(
                int(result.get("retries", 0) or 0) for result in results
            ),
            "pages": sum(
                int(result["summary"].get("pages", 0) or 0) for result in ok
            ),
            "crawl_pages": sum(
                int(result["summary"].get("crawl_pages", 0) or 0) for result in ok
            ),
            "api_specs": sum(
                int(result["summary"].get("api_specs", 0) or 0) for result in ok
            ),
            "stream_specs": sum(
                int(result["summary"].get("stream_specs", 0) or 0) for result in ok
            ),
            "blocked_pages": sum(
                int(
                    (result["summary"].get("crawl_summary") or {}).get("blocked", 0)
                    or 0
                )
                for result in ok
            ),
            "api_blocks": sum(
                int(result["summary"].get("api_blocks", 0) or 0) for result in ok
            ),
            "errors": sum(
                int(
                    (result["summary"].get("crawl_summary") or {}).get("errors", 0)
                    or 0
                )
                for result in ok
            ),
            "robots_skipped": sum(
                int(
                    (result["summary"].get("crawl_summary") or {}).get(
                        "robots_skipped", 0
                    )
                    or 0
                )
                for result in ok
            ),
            "block_recoveries": sum(
                int(result["summary"].get("block_recoveries", 0) or 0)
                for result in ok
            ),
            "recovered_pages": sum(
                int(result["summary"].get("recovered_pages", 0) or 0)
                for result in ok
            ),
            "processed_records": sum(
                int(result["summary"].get("processed_records", 0) or 0)
                for result in ok
            ),
        },
    }
    output = Path(args.combined_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(combined, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(combined["summary"], ensure_ascii=False, indent=2))
    for result in failed:
        print(
            f"site failed: {result['url']}: {result['error']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
