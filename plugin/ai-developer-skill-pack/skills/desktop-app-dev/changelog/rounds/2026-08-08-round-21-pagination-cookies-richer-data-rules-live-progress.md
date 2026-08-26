# 2026-08-08 (round 21) -- Pagination, cookies, richer data rules, live progress

### Added

- `api_client.py` now supports automatic pagination (`page` / `offset` /
  `cursor`) driven by `items_path`, `total_path`, `has_more_path`, and
  `next_path`; fetch results report the actual page count.
- `ApiClient` accepts Playwright-style cookies so browser-login sessions are
  carried into API fetching; `web_data_pipeline` copies browser cookies
  automatically.
- `data_processor.py` adds `drop`, `default`, `convert`, `map`, and
  `replace` operations for common field cleanup and derivation.
- `web_data_pipeline.py` accepts an optional progress callback and reports
  collect / discover / fetch / process / save / done stages.
- `media_pipeline_service.py` forwards webdata task progress into the SQLite
  queue progress field for live desktop UI updates.
- `OcrCaptchaSolver` preprocesses image CAPTCHAs (grayscale, threshold,
  resize) before OCR when Pillow is available.

### Verified

- `smoke_windows.ps1` -- 82 / 82
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 560 checks
- `test_no_bom.py` -- 179 files, 0 BOM / U+FEFF
- media pipeline -- 39 / 39
