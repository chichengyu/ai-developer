# Media acquisition and desktop task persistence

Playbook for a desktop media tool that crawls a website, extracts
video / audio / images, downloads with chunked resume, transcodes with
ffmpeg, and republishes to multiple platforms. It complements the
`scripts/media_*.py`, `scripts/page_data_parser.py`,
`scripts/scrape_guard.py`, `scripts/captcha_solver.py`,
`scripts/browser_session.py`, `scripts/task_queue.py`,
`scripts/ffmpeg_transcoder.py`, and `scripts/platform_publisher.py`
templates in this skill. The engine is exposed to every desktop UI
language through `scripts/media_pipeline_service.py` plus the ready-made
`clients/` wrappers; runtime dependencies install through
`scripts/builtin_dependency_manager.py`, `scripts/media_dependencies.py`,
and `scripts/setup_media_dependencies.ps1`.

## 1. Architecture

```text
PySide6 desktop shell
  ├── task table + pagination        (UI-07)
  ├── download / transcode progress  (live signals)
  ├── log center                     (UI-13)
  └── theme center                   (UI-10)
          │
          ▼
SQLite persistent task queue
  ├── crawl tasks
  ├── download tasks (chunk map + resume token)
  ├── transcode tasks
  └── publish tasks
          │
          ▼
Worker pool (QThreadPool / Python threads)
  ├── crawler / parser
  ├── chunked downloader
  ├── ffmpeg transcoder
  └── platform publisher
```

Keep the UI thread free. Every network, download, transcode, and publish
operation runs in a worker. The worker reads the next task from SQLite,
updates progress in SQLite, and emits a small Qt signal object for live
UI updates. On restart, SQLite is the source of truth: tasks, progress,
chunk checkpoints, and failure reasons survive the process.

## 2. SQLite 持久化队列 (Why SQLite for the queue)

- One local file, no external database server.
- ACID transactions protect `queued -> running -> succeeded/failed`
  transitions.
- WAL mode lets the UI read progress while workers write.
- `busy_timeout` prevents `database is locked` errors in a desktop app.
- A task row stores JSON payload, so one queue handles crawl / download /
  transcode / publish without extra tables.

Recommended pragmas:

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA foreign_keys = ON;
```

## 3. Task schema

```sql
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                -- crawl | download | transcode | publish
    dedupe_key TEXT UNIQUE,            -- stable id to avoid duplicate tasks
    payload TEXT NOT NULL,             -- JSON task input
    status TEXT NOT NULL DEFAULT 'queued',
    priority INTEGER NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    progress REAL NOT NULL DEFAULT 0,  -- 0.0 .. 1.0
    stage TEXT,                        -- "parse", "segments", "merge", "upload"
    progress_meta TEXT,                -- JSON live snapshot: bytes, speed, ETA, sizes
    resume_token TEXT,                 -- JSON chunk map / m3u8 position
    error TEXT,
    result_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
    ON tasks(status, priority, id);
```

`dedupe_key` is the hard guard for UI-11: a crawl result cannot create
the same download task twice. Use a stable key such as
`sha256(source_url)` or `site|media_id`.

## 4. State machine

```text
queued -> running -> succeeded
   ^         |
   |         v
   |      failed
   |         |
   +---------+  (attempts < max_attempts -> queued again)

running <-> paused
running/cancelled -> cancelled (temp files cleaned)
```

Crash recovery on startup:

```text
UPDATE tasks
SET status = 'queued', updated_at = now
WHERE status = 'running';
```

This is safe because a worker writes `progress` and `resume_token`
before starting each resumable unit. A task marked `running` by a dead
process is put back into the queue; the downloader skips already-downloaded
chunks from the chunk map.

## 5. Atomic worker claim

Multiple workers must not run the same task. Claim with one transaction:

```sql
UPDATE tasks
SET status = 'running', attempts = attempts + 1, updated_at = now
WHERE id IN (
    SELECT id FROM tasks
    WHERE status = 'queued'
    ORDER BY priority DESC, id ASC
    LIMIT 1
)
RETURNING id, kind, payload, resume_token;
```

If the SQLite version does not support `RETURNING`, select ids first and
then update inside the same transaction. Use one connection per worker
thread plus a short `busy_timeout`, or serialize writes behind one
`threading.RLock` as the included `scripts/task_queue.py` does.

## 6. 分片下载与断点续传 (Progress and resume)

- UI progress is a live signal; durable progress is SQLite.
- Throttle durable writes: persist progress every 1-2 seconds or after a
  chunk finishes, not on every byte.
- Chunked download keeps one `.part` file per chunk and a JSON chunk map
  in `resume_token`:

```json
{
  "chunks": [
    {"index": 0, "start": 0, "end": 8388607, "done": true},
    {"index": 1, "start": 8388608, "end": 16777215, "done": false}
  ],
  "total_size": 104857600
}
```

- On resume, skip `done: true` chunks, re-download missing chunks, then
  merge and atomically rename the final file.
- Each chunk retries with exponential backoff (`chunk_retries`), so a
  temporary network drop does not fail the whole file.
- Adaptive concurrency is on by default: a sliding-window speed tracker
  grows the worker count while adding workers improves throughput
  (`tune_interval`) and shrinks it after an error burst or throughput
  loss. `adaptive_concurrency=false` restores fixed worker behavior.
- Slow-shard switching is on by default: a shard that stalls below 15%
  of the current global speed for `slow_after_seconds` is cancelled and
  restarted from its current byte offset (up to `slow_restart_limit`
  times), which also rotates to the next proxy when a proxy pool is
  configured.
- When HEAD omits `Content-Length` / `Accept-Ranges`, the downloader
  issues a one-byte Range GET and reads the total from `Content-Range`
  before falling back to a single-stream download.
- Live progress includes window `speed_avg` and `eta_s` alongside the
  existing overall `speed` field.
- Every download snapshot also reports `downloaded`, `total` (the known
  total file size), `percent`, `speed`, `speed_avg`, `eta_s`,
  `chunks_done` / `chunks_total`, `merge_done` / `merge_total`, and
  `elapsed_s`; a `probe` event fires before bytes start so the UI can show
  the file size immediately, and a final `done` event reports the completed
  size, elapsed time, and average speed.
- `auto_chunk_sizing` (default true) sizes shards so small files still use
  every connection; pass a custom `chunk_size` to disable it.
- `max_speed_bytes_per_sec` caps total download throughput across all
  shards with a shared speed limiter, useful for polite or metered
  downloads without losing resume/concurrency.
- HLS resume stores the last completed segment index; already-downloaded
  `.ts` / `.m4s` files are reused.
- URL-derived filenames go through `safe_output_name` (defined in
  `scripts/media_downloader.py`) before touching the filesystem, so
  encoded `..` / separator tricks cannot escape the output directory.
- Transcode resume is not generally possible; instead re-run ffmpeg and
  show progress from `-progress pipe:1`.

## 7. Crawl and parse

1. Use one persistent session with cookies, user-agent, and optional
   proxy from `scripts/media_session.py`.
2. Fetch the page, parse links with `scripts/media_parser.py`.
3. Deep-parse the page with `scripts/page_data_parser.py`
   (`analyze_page()`): metadata, JSON-LD / `application/json` state,
   Next.js / Nuxt / global-state scripts, embedded JSON media and API
   fields, pagination fields, and API endpoints from `fetch` / XHR /
   axios / forms / preloads / script tags. It also derives Next.js
   `/_next/data/<buildId><page>.json` routes from `__NEXT_DATA__`, and
   reports detected CAPTCHA challenges. The same analysis runs from a
   CLI: `python scripts/page_data_parser.py --url <page-url>`.
4. For SPA / API-driven pages, `scripts/browser_session.py`
   (`capture_page_data()`) records runtime `xhr` / `fetch` / WebSocket
   traffic with method, status, content type, size, and JSON bodies,
   then combines the network capture with the static parse.
5. Extract direct media URLs (`video`, `audio`, `img`, `source`,
   `poster`, `data-src`, `srcset`) and HLS playlists (`m3u8`).
6. Normalize relative URLs against the page URL or `<base href>`.
7. Enqueue one task per media URL with `dedupe_key`. For deep analysis
   only, enqueue `kind: "analyze"`; `crawl` accepts `"deep": true` to
   include the same page-data summary in its result.
8. Rate-limit requests and honor `robots.txt` / platform terms where
   possible; aggressive crawling risks IP blocks and account bans.

## 8. HLS / m3u8

`scripts/hls_downloader.py` handles:

- Master playlist selection: pick the highest-bandwidth variant when the
  user did not choose a quality; `quality` selects a zero-based variant.
- `#EXT-X-KEY` AES-128 keys: download the key URI, decrypt segments.
- Segment retries with exponential backoff (`segment_retries`).
- `#EXT-X-BYTERANGE` segments: each segment is fetched with the exact
  Range request; offsets without `@offset` are resolved sequentially per
  media URI.
- `#EXT-X-MAP` init segments: the init file is downloaded once, written
  first into the concat list, and included in the fallback merge.
- Segment names keep the real extension (`.ts` / `.m4s`), and
  already-downloaded segments are reused for resume.
- ffmpeg merge: build a concat list, then
  `ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4`.
- No-ffmpeg fallback: concatenate init + segments directly into the
  requested output file when `merge_fallback=true` (default), and keep
  segments unless `keep_segments=false`.

## 9. CAPTCHA and account login

`scripts/captcha_solver.py` defines a uniform interface:

- `detect_captchas()` auto-recognizes reCAPTCHA v2/v3, hCaptcha,
  Turnstile, Geetest, and image CAPTCHA scripts/elements on a page
- `CaptchaSolver.solve_image()` / `solve_recaptcha_v2()` /
  `solve_recaptcha_v3()` / `solve_hcaptcha()` / `solve_turnstile()` /
  `solve_geetest()` for third-party service calls
- `AutoCaptchaSolver` detects a page's challenges and solves them through
  the third-party service without a manual dialog
- `ManualCaptchaSolver` remains an explicit opt-in fallback

Full-auto login flow:

```python
from captcha_solver import AutoCaptchaSolver, CaptchaSolver
from browser_session import BrowserSession

solver = AutoCaptchaSolver(CaptchaSolver(api_key="from-encrypted-config"))
session = BrowserSession()
session.start()
session.login(
    url,
    username,
    password,
    username_selector,
    password_selector,
    submit_selector,
    auto_captcha_solver=solver,
    max_captcha_retries=3,
)
```

`BrowserSession.solve_captchas_auto()` can also be called directly after a
page load; it detects challenges, solves them, and fills the response
fields in the page.

Third-party solving services normally follow a two-step pattern:

```text
POST in.php    -> task id
GET  res.php   -> answer when ready
```

Keep API keys encrypted in local config (Windows DPAPI / keyring), never
in plaintext. A failure must go to the log center with the exact reason
and a suggested next step (UI-13). Do not claim a solver can bypass every
challenge; many platforms require human confirmation.

## 10. Anti-bot, proxy, fingerprint

`scripts/browser_session.py` provides a Playwright session with:

- Stable user agent, locale, timezone, viewport, screen, platform,
  languages, hardware concurrency, device memory, and color scheme;
  `FingerprintOptions.generate(seed=...)` creates one stable profile per
  account and `save()/load()` persist it
- Cookie persistence between runs
- Proxy support
- Runtime XHR/fetch/WebSocket capture (`capture_page_data()`)
- Auto CAPTCHA detect/solve (`solve_captchas_auto()`)
- Optional action pacing (`action_interval` / `action_jitter`)

`scripts/scrape_guard.py` adds polite HTTP-side protection for
`scripts/media_session.py`:

- `RateLimiter` -- minimum interval plus random jitter
- `RetryPolicy` -- exponential backoff with `Retry-After` support
- `RobotsPolicy` -- robots.txt allow/deny and crawl-delay checks
- `AdaptiveThrottle` -- increases pacing after 403/429/5xx, eases on success

The sidecar accepts these as task payload options (`min_interval`,
`jitter`, `max_retries`, `backoff_base`, `backoff_max`, `robots_text`,
`adaptive_throttle`), so every crawl/download/analyze task can be paced.

Good practices:

- Use the same session/fingerprint for login and downloads; changing
  mid-session is a common block signal.
- Rotate proxies slowly and only when the site allows it; per-request
  IP rotation is a stronger block signal for most risk controls.
- Add jitter between requests, honor retry-after, and back off
  exponentially on 429 / 5xx.
- Treat anti-bot as failure handling, not guaranteed bypass. Log the
  block, keep the session, and offer a manual retry.

## 11. Transcoding

`scripts/ffmpeg_transcoder.py` runs:

```text
ffmpeg -i input.mp4 -c:v libx264 -preset medium -crf 23
       -c:a aac -progress pipe:1 -nostats -y output.mp4
```

The default behavior is smart remux: when `ffprobe` shows the source
video/audio codecs already match the target container and no
resolution / fps / bitrate change is requested, `-c copy` is used
instead of re-encoding. Set `smart_copy=false` to force a full encode.

Named presets cover the common format targets:

- `mp4` / `mp4-hq` -- H.264 + AAC with optional `+faststart`
- `hevc` / `hevc-hq` -- H.265 + AAC
- `webm` -- VP9 + Opus
- `mp3` / `m4a` / `wav` / `flac` -- audio-only extraction
- `mkv` / `mov` -- broad container / editing targets

Set `hardware=true` to auto-detect a GPU encoder from `ffmpeg -encoders`
(NVENC, AMF, QSV, VideoToolbox), or pass an encoder name such as
`h264_nvenc` to pin it. Hardware encoders automatically use their native
quality arguments (`-cq`, `-global_quality`, `-qp_i/-qp_p`, `-q:v`)
instead of software `-crf`.

`build_ffmpeg_args()` returns the exact command line without running it,
which makes UI previews and tests easy. The one-shot CLI supports
`--profile`, `--hardware`, `--no-smart-copy`, `--resolution`, bitrate /
fps / audio options, and `--list-profiles`.

Parse `out_time_ms` and total duration from `ffprobe` to compute
percentage. If duration is unknown, show elapsed time and current stage
instead of a fake percentage.

The ffmpeg command always runs with `-progress pipe:1 -nostats` so real
encode output is parsed. Transcode progress now carries `out_time_s`, `percent`, `speed`, `fps`,
`bitrate`, `frame`, `input_size` (source file bytes), `output_size`
(ffmpeg `total_size` bytes), `duration_s`, `remaining_s`, and `state`.
When ffmpeg exits, a `finalize` event reports the actual output file size.
`start_time`, `duration`, and `threads` options are supported for clipping
and CPU tuning. The named preset list adds `avi`, `ts`, `ogg`, `opus`,
`aac`, `ac3`, and `gif` on top of the mp4 / hevc / webm / mkv / mov / audio
formats, plus `m2ts`, `mpeg`, `flv`, `wmv`, `m4v`, `3gp`, `ogv`, `vob`,
`asf`, `mka`, `oga`, `aiff`, `wma`, `amr`, `mp2`, `dts`, `eac3`, `m4b`,
`alac`, and image targets (`jpg`, `png`, `bmp`, `tiff`, `webp`, `avif`,
`heic`, `jxl`, `ico`).

## 11.5 Unified format catalog and generic conversion

`scripts/media_formats.py` is the single format registry for the desktop
media tool. It covers video, audio, image, subtitle, document, data, and
archive targets, and every entry declares the engine that can produce it:

- `ffmpeg` -- video / audio / image targets through
  `scripts/ffmpeg_transcoder.py`.
- `stdlib` -- text, markdown/HTML, CSV/JSON/JSONL/XML/INI, SRT/VTT/ASS
  subtitle, and ZIP/TAR/GZ/BZ2/XZ archive conversions using the Python
  standard library.
- `copy` -- byte-for-byte targets such as SVG, log, or subtitle passthrough.
- `optional` -- PDF / Office / HEIC / 7z / RAR / YAML targets that require
  an external tool; the converter returns a clear unavailable error
  instead of silently producing garbage.

Query the catalog from the UI:

```text
GET /formats
python scripts/media_formats.py --list
python scripts/media_formats.py --lookup mp4 --json
```

`scripts/file_converter.py` dispatches `convert_file()` by target
extension, and `convert_many()` converts a folder with aggregate
byte-based progress (`total_input_bytes`, per-file `done`/`total`,
output bytes, percent, elapsed time). Archive extraction is available as
`extract_archive()` with zip/tar path-traversal guards. The sidecar accepts
`kind: "convert"` and `kind: "batch-convert"` tasks, so any desktop UI
language gets the same live progress/event contract as downloads.

## 12. Publishing

`scripts/platform_publisher.py` defines a `Publisher` interface:

- `login()` with API token, cookies, or browser session
- `upload()` with progress callback
- `publish()` with visibility / schedule / tags
- `close()` to release sessions

Each platform is one adapter. Add retries, idempotency keys, and upload
resume where the platform supports it. Do not reuse a download session's
login for a platform that requires a separate account session unless the
adapter explicitly shares it.

## 13. UI integration

- `task_queue.py` is framework-agnostic; the PySide6 layer polls or
  receives change events and refreshes the table.
- Live progress: worker emits `progress = Signal(object)` carrying
  `{task_id, stage, percent, speed, eta, total, downloaded, ...}`; UI
  updates one row. The sidecar persists this as `progress_meta` and exposes
  `GET /tasks/<id>/progress` plus
  `GET /tasks/<id>/events?after=N&timeout=0..30`; the optional timeout
  long-polls for the next event for near-real-time UI updates.
- Format pickers: call `GET /formats` once and group the returned catalog
  by category (`video`, `audio`, `image`, `subtitle`, `document`, `data`,
  `archive`) so the UI can offer every supported target without
  hard-coding extensions.
- Built-in dependency center (UI-19): show one status row per runtime,
  call `POST /deps/install` after the user clicks `安装依赖`, poll
  `GET /deps/progress` for bytes / speed / ETA / stage, and use
  `scripts/builtin_dependency_manager.py` when the app needs a generic
  app-local dependency manifest instead of the media-specific installer.
- Before a transcode job, the UI can call `POST /media/probe` with
  `{"path": "C:\\media\\input.mp4"}` to get duration, streams, codecs,
  and resolution so the user sees source metadata before choosing a
  format preset.
- Log center: worker failures are written to SQLite `error` and to a log
  row with reason + suggested fix.
- Table pagination (UI-07) maps to `list_tasks(limit, offset)`.
- Auto-refresh interval (UI-09) re-queries the table; it does not replace
  live progress events.
- Advanced automation: rotating proxies (`scripts/proxy_pool.py`),
  multi-account leases (`scripts/account_manager.py`), recurring schedules
  (`scripts/task_scheduler.py`), and completion notifications
  (`scripts/notifier.py`) integrate through the sidecar; see
  `references/web_data_pipeline_playbook.md` sections 9-12.

## 14. Compliance

Automated login, CAPTCHA solving, scraping, and republishing may violate
platform terms or local law. Before shipping:

- Confirm the user has permission to download and republish the content.
- Store credentials encrypted and locally.
- Add rate limits and a global stop switch.
- Expose every failure in the log center instead of hiding it.
- Do not market the tool as a CAPTCHA bypass or anti-ban tool.
