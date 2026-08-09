# 2026-08-08 (round 9) -- All-language sidecar + runtime installer

### Added

- `scripts/media_dependencies.py` -- check / install Playwright,
  pycryptodome, Chromium, and portable ffmpeg; `--install` is explicit.
- `scripts/setup_media_dependencies.ps1` -- PowerShell wrapper with
  check-only default and `-Install`.
- `scripts/media_pipeline_service.py` -- local HTTP sidecar with task
  queue, workers, crawl / download / HLS / transcode handlers,
  dependency install endpoint, and JSON API.
- `references/media_pipeline_clients.md` -- C# / JS / TS / Go / Rust /
  Kotlin / Swift / Java / C++ client snippets for the sidecar.
- `clients/` -- ready-made wrapper templates in the same 8 languages.
- `scripts/media_pipeline_service.py` -- `/deps/progress` endpoint,
  task enqueue now accepts `max_attempts` / `resume_token`, and
  download / HLS tasks accept proxy, headers, concurrency, chunk size,
  and resume settings via payload.
- `scripts/task_queue.py` -- `count()` now supports the same search
  filter as `list_tasks()`, so list totals are correct when searching.
- `scripts/media_dependencies.py` / `setup_media_dependencies.ps1` --
  ffmpeg download URL can be overridden with `--ffmpeg-url` / `-FfmpegUrl`.
- `scripts/media_downloader.py` -- per-chunk retry with exponential
  backoff via `chunk_retries`.
- `scripts/hls_downloader.py` -- `quality` selects a zero-based master
  variant instead of always taking the highest bandwidth.
- `scripts/media_pipeline_service.py` -- service startup closes the SQLite
  queue if the HTTP server cannot bind.
- `tests/test_media_pipeline.py` -- dependency status, HTTP sidecar, and
  crawl handler tests; media pipeline suite is now 11/11.

### Fixed

- `scripts/task_queue.py` -- retry tasks support `run_after` delayed
  scheduling and existing databases migrate the new column.
- `scripts/media_dependencies.py` -- Chromium detection now covers
  Windows, macOS, and Linux Playwright cache paths.
- `scripts/captcha_solver.py` -- solver HTTP errors now surface as
  `CaptchaError` with the server response instead of a raw urllib error.
