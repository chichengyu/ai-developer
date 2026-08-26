# 2026-08-08 (round 8) -- Media acquisition pipeline

### Added

- `references/media_acquisition_playbook.md` -- architecture, SQLite task
  queue design, crawl / HLS / download / transcode / publish pipeline,
  CAPTCHA and anti-bot handling, crash recovery, and compliance notes.
- `scripts/media_session.py` -- cookies, proxy, retry HTTP session.
- `scripts/media_parser.py` -- HTML media extraction + m3u8 parsing.
- `scripts/media_downloader.py` -- Range chunked download, resume,
  concurrency, checkpoint files, and progress callbacks.
- `scripts/hls_downloader.py` -- HLS segments, AES-128 keys, ffmpeg merge.
- `scripts/captcha_solver.py` -- third-party solver + manual fallback.
- `scripts/browser_session.py` -- Playwright login / cookies / fingerprint.
- `scripts/task_queue.py` -- SQLite persistent queue with atomic claims,
  dedupe, retry, progress, and stale-running recovery.
- `scripts/ffmpeg_transcoder.py` -- ffmpeg / ffprobe progress wrapper.
- `scripts/platform_publisher.py` -- publish adapter interface + retry.
- `tests/test_media_pipeline.py` -- 5 local tests for queue persistence,
  parser, manual CAPTCHA, chunked download, and HLS download.
- `tests/smoke_windows.ps1` -- runs the media pipeline test suite.
