# 2026-08-08 (round 39) -- UI-19 built-in dependency center + app-local manager

### Added

- Global hard requirement `UI-19 内置依赖中心`: every desktop app that
  needs an external runtime (ffmpeg / tesseract / ImageMagick / Playwright
  Chromium / 7z, etc.) manages it inside the app; the user clicks
  `安装依赖`, and the app automatically downloads / installs / configures
  with live bytes, speed, ETA, and stage. No terminal commands, no manual
  PATH editing, no global install, no interactive prompts.
- `scripts/builtin_dependency_manager.py` -- generic app-local dependency
  manager: JSON manifest, check-only default, parallel chunked resumable
  downloads, SHA-256 verification, safe zip/tar extraction, portable /
  archive / pip / detect kinds, app-local bin paths, and environment
  configuration.
- `scripts/media_dependencies.py` -- ffmpeg zip now downloads through the
  chunked concurrent resumable downloader with a local cache and live
  bytes / speed / ETA progress instead of a single-stream fetch.

### Docs

- `SKILL.md`, `README.md`, `INDEX.md`,
  `references/ui_hard_requirements.md`,
  `templates/requirements_checklist.md`,
  `templates/release_checklist.md`,
  `references/media_acquisition_playbook.md`, and
  `references/media_pipeline_clients.md` updated with UI-01..UI-19 and
  the built-in dependency center contract.

### Tests

- `tests/test_media_pipeline.py` -- 3 new cases (archive install with
  checksum, portable install + checksum mismatch, check-only default);
  81/81 pass.
