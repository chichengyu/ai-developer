# 2026-08-08 (round 27) -- Automatic security identification + deep crawling

### Added

- `scripts/security_detector.py` -- classifies Cloudflare challenge / block,
  WAF, rate limit, CAPTCHA, login wall, cookie consent, JS required, geo
  block, empty page, and SPA shell responses into an actionable
  `SecurityReport`. `WebDataPipeline` uses the report to retry, rotate
  proxy, escalate to the fingerprint browser, or skip without user input.
- `scripts/deep_crawler.py` -- BFS deep crawler over links and sitemaps with
  robots.txt, same-host / include / exclude filters, depth and page limits,
  URL deduplication, and blocked-page skipping. Includes a standalone CLI.
- `MediaSession.get_bytes_with_meta()` and non-raising
  `request_json_with_meta()` now return body, status, and headers for
  4xx / 5xx responses. `ApiFetchResult` keeps `status`, `headers`, and a
  `security` report instead of only a generic exception.
- `PageDataAnalysis.links` and `BrowserSession.wait_for_challenge()`.
  `web_data_pipeline.py` accepts `security` and `crawl` config sections.
- `RobotsPolicy.sitemap_urls()` plus raw robots text access.

### Docs

- `references/web_data_pipeline_playbook.md` -- new automatic security
  identification and deep crawling sections, plus API failure metadata
  notes.
- `SKILL.md`, `README.md`, and `INDEX.md` -- pointers to the new scripts and
  config sections.
- `tests/test_media_pipeline.py` -- security classifier, deep crawler,
  HTTP error metadata, and pipeline crawl integration tests.

### Verified

- media pipeline -- 54 / 54
- test_docs.py -- 663 checks
- test_no_bom.py -- 187 files, 0 BOM / U+FEFF
- smoke_windows.ps1 -- 92 / 92
- arch awareness -- 16 / 16
- ruff check, ruff format --check, mypy scripts/ -- all green
