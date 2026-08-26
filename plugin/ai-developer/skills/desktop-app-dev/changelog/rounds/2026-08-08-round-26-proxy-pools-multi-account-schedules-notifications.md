# 2026-08-08 (round 26) -- Proxy pools, multi-account, schedules, notifications

### Added

- `scripts/proxy_pool.py` -- round-robin / random proxy pool with failure
  cooldown plus a named `ProxyPoolStore` for sidecar-managed pools.
  `MediaSession`, `ApiClient`, and `WebDataPipeline` now rotate proxies on
  retry without changing their existing APIs.
- `scripts/account_manager.py` -- persistent multi-account profiles with
  storage state, cookie files, browser profile dirs, proxies, headers, and
  login config. Tasks lease one account at a time; failed accounts cool
  down before reuse.
- `scripts/task_scheduler.py` -- interval / daily / cron / once schedules
  persisted in the same SQLite database as the task queue, with a sidecar
  loop that enqueues due tasks.
- `scripts/notifier.py` -- best-effort completion notifications through
  desktop toast, SMTP email, and webhook.
- Sidecar endpoints: `/proxy-pools`, `/accounts`, `/schedules`, and
  `/notifications/status` / `/notifications/test`. `POST /tasks` also
  accepts `run_after_seconds` for one-shot delayed tasks.
- Per-task controls: `"account": "<name>"`, `"proxy_pool": ...`,
  `"auto_retry": false`, `"retry_delay_seconds": N`, and
  `"notify": false`.

### Docs

- `references/web_data_pipeline_playbook.md` -- new sections for proxy
  pools, multi-account sessions, scheduled tasks / retry, and notifications.
- `SKILL.md`, `README.md`, `INDEX.md`, and
  `references/media_acquisition_playbook.md` -- advanced automation
  pointers and sidecar endpoint references.

### Verified

- `smoke_windows.ps1` -- 90 / 90
- `test_docs.py` -- 647 checks
- `test_no_bom.py` -- 185 files, 0 BOM / U+FEFF
- media pipeline -- 48 / 48
- arch awareness -- 16 / 16
- ruff check, ruff format --check, mypy scripts/ -- all green
