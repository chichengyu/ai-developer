# 2026-08-08 (round 20) -- Web data pipeline

### Added

- `scripts/api_client.py` -- converts page/network captures into replayable
  API specs and fetches JSON through `MediaSession` with rate limits and
  retries; includes `build_api_specs`, `ApiClient`, and a local self-test.
- `scripts/data_processor.py` -- declarative processing engine with
  select / rename / filter / sort / dedupe / flatten / limit / aggregate
  steps and JSON / JSONL / CSV I/O.
- `scripts/web_data_pipeline.py` -- one-config end-to-end pipeline for
  fingerprint browser + auto CAPTCHA + page/API analysis + API fetching +
  data processing.
- `references/web_data_pipeline_playbook.md` -- full workflow, config
  schema, CAPTCHA modes, API replay, processing operations, UI sidecar
  integration, and compliance checklist.
- `scripts/media_pipeline_service.py` now accepts `kind: "webdata"` tasks
  so desktop UIs can run the whole pipeline through the sidecar.

### Enhanced

- `scripts/captcha_solver.py` -- local OCR adapter (`OcrCaptchaSolver`) and
  OCR-first automatic solving with third-party / manual fallback; CLI
  self-test.
- `scripts/browser_session.py` -- network entries now keep request POST
  bodies and content types; Playwright storage state can be saved/restored;
  `BrowserSession` accepts a `storage_state` profile path.
- `scripts/media_session.py` -- `request_json()` for arbitrary methods with
  JSON or raw bodies.
- `scripts/media_dependencies.py` -- checks/installs Pillow and pytesseract
  and reports system `tesseract` availability as the `ocr` status key.

### Verified

- `smoke_windows.ps1` -- 82 / 82
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 560 checks
- `test_no_bom.py` -- 179 files, 0 BOM / U+FEFF
- media pipeline -- 36 / 36; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates
