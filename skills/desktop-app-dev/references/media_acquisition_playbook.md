# Media acquisition and desktop task persistence

Playbook for a desktop media tool that crawls a website, extracts
video / audio / images, downloads with chunked resume, transcodes with
ffmpeg, and republishes to multiple platforms. It complements the
`scripts/media_*.py`, `scripts/captcha_solver.py`,
`scripts/browser_session.py`, `scripts/task_queue.py`,
`scripts/ffmpeg_transcoder.py`, and `scripts/platform_publisher.py`
templates in this skill. The engine is exposed to every desktop UI
language through `scripts/media_pipeline_service.py` plus the ready-made
`clients/` wrappers; runtime dependencies install through
`scripts/media_dependencies.py` and
`scripts/setup_media_dependencies.ps1`.

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
- HLS resume stores the last completed segment index; already-downloaded
  `.ts` files are reused.
- URL-derived filenames go through `safe_output_name` (defined in
  `scripts/media_downloader.py`) before touching the filesystem, so
  encoded `..` / separator tricks cannot escape the output directory.
- Transcode resume is not generally possible; instead re-run ffmpeg and
  show progress from `-progress pipe:1`.

## 7. Crawl and parse

1. Use one persistent session with cookies, user-agent, and optional
   proxy from `scripts/media_session.py`.
2. Fetch the page, parse links with `scripts/media_parser.py`.
3. Extract direct media URLs (`video`, `audio`, `img`, `source`,
   `poster`, `data-src`, `srcset`) and HLS playlists (`m3u8`).
4. Normalize relative URLs against the page URL.
5. Enqueue one task per media URL with `dedupe_key`.
6. Rate-limit requests and honor `robots.txt` / platform terms where
   possible; aggressive crawling risks IP blocks and account bans.

## 8. HLS / m3u8

`scripts/hls_downloader.py` handles:

- Master playlist selection: pick the highest-bandwidth variant when the
  user did not choose a quality; `quality` selects a zero-based variant.
- `#EXT-X-KEY` AES-128 keys: download the key URI, decrypt segments.
- Segment download with the same chunked downloader.
- ffmpeg merge: build a concat list, then
  `ffmpeg -f concat -safe 0 -i list.txt -c copy out.mp4`.
- No-ffmpeg fallback: keep segments plus a `concat.txt` file.

## 9. CAPTCHA and account login

`scripts/captcha_solver.py` defines a uniform interface:

- `solve_image()` for image CAPTCHA
- `solve_recaptcha_v2()` / `solve_hcaptcha()` / `solve_turnstile()` for
  site-key challenges
- `ManualCaptchaSolver` for a UI dialog when automation is not possible

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

- Stable user agent, locale, timezone, viewport, and platform settings
- Cookie persistence between runs
- Proxy support
- Login flow with optional CAPTCHA callback

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

Parse `out_time_ms` and total duration from `ffprobe` to compute
percentage. If duration is unknown, show elapsed time and current stage
instead of a fake percentage.

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
  `{task_id, stage, percent, speed, eta}`; UI updates one row.
- Log center: worker failures are written to SQLite `error` and to a log
  row with reason + suggested fix.
- Table pagination (UI-07) maps to `list_tasks(limit, offset)`.
- Auto-refresh interval (UI-09) re-queries the table; it does not replace
  live progress events.

## 14. Compliance

Automated login, CAPTCHA solving, scraping, and republishing may violate
platform terms or local law. Before shipping:

- Confirm the user has permission to download and republish the content.
- Store credentials encrypted and locally.
- Add rate limits and a global stop switch.
- Expose every failure in the log center instead of hiding it.
- Do not market the tool as a CAPTCHA bypass or anti-ban tool.
