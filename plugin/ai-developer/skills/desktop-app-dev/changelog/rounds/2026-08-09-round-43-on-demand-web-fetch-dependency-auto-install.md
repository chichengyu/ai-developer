# 2026-08-09 (round 43) -- On-demand web-fetch dependency auto-install

### Added

- `scripts/ensure_web_fetch_dependencies.py` -- standalone check / automatic
  installer for `curl_cffi`, `cloudscraper`, `httpx`, and `h2`. Default CLI
  mode installs missing packages; `--check` only reports status.
- `smart_fetch.py` / `api_client.py` / `deep_crawler.py` now accept
  `auto_install` / `--auto-install`; auto mode defaults to installing
  missing optional packages on first use, and the pipeline still falls back
  to `urllib` if installation fails. `"auto_install": false` disables it.

### Docs

- `references/web_data_pipeline_playbook.md`, `README.md`, `INDEX.md`, and
  `SKILL.md` document the auto-install flow and standalone script.

### Tests

- `tests/test_media_pipeline.py` adds dependency status and smart-fetch
  auto-install hook coverage.
