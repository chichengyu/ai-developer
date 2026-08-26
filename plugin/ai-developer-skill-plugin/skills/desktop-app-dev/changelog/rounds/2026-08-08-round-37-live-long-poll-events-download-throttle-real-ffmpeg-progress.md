# 2026-08-08 (round 37) -- Live long-poll events + download throttle + real ffmpeg progress

### Added

- `scripts/ffmpeg_transcoder.py` -- every generated ffmpeg command now
  includes `-progress pipe:1 -nostats`, so real encodes emit live
  `out_time_ms` / `total_size` / `fps` / `bitrate` / `frame` progress
  instead of only parsing fake output.
- `scripts/media_downloader.py` -- shared `SpeedLimiter` and
  `max_speed_bytes_per_sec` download option; total throughput is capped
  across all shards while keeping adaptive concurrency and resume.
- `scripts/media_pipeline_service.py` -- task events support long polling
  via `GET /tasks/<id>/events?after=N&timeout=0..30`; the request waits
  for the next event instead of returning immediately.
- `clients/*` -- `taskEvents(id, after, timeout)` wrappers now expose the
  long-poll timeout in TypeScript, C# / .NET, Go, Rust, Kotlin, Swift,
  Java, and C++.

### Tests

- `tests/test_media_pipeline.py` -- 3 new cases (speed limiter throttle,
  download speed-limit integration, sidecar long-poll events) plus
  assertions that generated ffmpeg args contain the real progress flags;
  72/72 pass.

### Docs

- `references/media_acquisition_playbook.md`,
  `references/media_pipeline_clients.md`, and `clients/README.md` updated
  with `max_speed_bytes_per_sec`, `-progress pipe:1 -nostats`, and the
  long-poll event API.
