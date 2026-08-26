# 2026-08-08 (round 28) -- Cloudflare high-intensity challenge handling

### Added

- `scripts/cloudflare_challenge.py` -- dedicated high-intensity Cloudflare
  handler: stage classification (`js_challenge`,
  `managed_non_interactive`, `turnstile_captcha`, `blocked`), `cf_clearance`
  cookie waiting, Turnstile checkbox interaction, third-party token
  injection, reload retries, and `needs_new_session` proxy-rotation signal.
- `web_data_pipeline.py` -- new `cloudflare` config section. After the
  challenge passes, the pipeline reuses the browser user agent,
  `cf_clearance` cookie, and pinned proxy for subsequent API fetches so the
  clearance is not invalidated by an IP / UA mismatch.
- `security_detector.py` -- Cloudflare challenge findings now include stage,
  sitekey, frame URL, ray ID, and clearance-cookie presence details.

### Docs

- `references/web_data_pipeline_playbook.md`, `SKILL.md`, `README.md`, and
  `INDEX.md` -- Cloudflare high-intensity workflow and `cloudflare` config.
- `tests/test_media_pipeline.py` -- Cloudflare state extraction and fake
  browser challenge-handler tests.

### Verified

- media pipeline -- 56 / 56
- test_docs.py -- 671 checks
- test_no_bom.py -- 188 files, 0 BOM / U+FEFF
- smoke_windows.ps1 -- 93 / 93
- arch awareness -- 16 / 16
- ruff check, ruff format --check, mypy scripts/ -- all green
