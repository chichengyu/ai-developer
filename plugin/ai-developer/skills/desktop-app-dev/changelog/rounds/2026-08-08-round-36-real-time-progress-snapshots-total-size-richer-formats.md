# 2026-08-08 (round 36) -- Real-time progress snapshots + total size + richer formats

### Added

- `scripts/media_downloader.py` -- automatic shard sizing for small files,
  `probe` / `merge` / `done` progress snapshots with total file size,
  downloaded bytes, percent, speed, window `speed_avg`, ETA, chunk counts,
  merge progress, and elapsed time; `DownloadResult` now returns elapsed
  time and average speed.
- `scripts/ffmpeg_transcoder.py` -- rich transcode snapshots
  (`input_size`, `output_size`, `duration_s`, `remaining_s`, `fps`,
  `bitrate`, `frame`, `state`), a `finalize` event with the real output file
  size, new format profiles (`avi`, `ts`, `ogg`, `opus`, `aac`, `ac3`,
  `gif`), and `start_time` / `duration` / `threads` options.
- `scripts/hls_downloader.py` -- HLS progress now reports downloaded bytes
  and the final merged output size.
- `scripts/task_queue.py` / `scripts/media_pipeline_service.py` -- SQLite
  `progress_meta` column with migration, persisted progress snapshots,
  richer task events, `GET /tasks/<id>/progress`, and payload forwarding
  for `auto_chunk_sizing`, `start_time`, `duration`, and `threads`.
- `clients/*` -- `taskProgress` / `taskEvents` in TypeScript, C# / .NET,
  Go, Rust, Kotlin, Swift, Java, and C++; TypeScript and Go also ship a
  `watchProgress` helper that polls until the task finishes.

### Tests

- `tests/test_media_pipeline.py` -- 5 new cases (progress metadata
  persistence, download total-size snapshots, auto chunk sizing, rich
  transcode progress, sidecar progress endpoint); 69/69 pass.

### Docs

- `references/media_acquisition_playbook.md`,
  `references/media_pipeline_clients.md`, `clients/README.md`, `SKILL.md`,
  `README.md`, and `INDEX.md` updated with the live progress snapshot
  contract, richer format presets, and client polling helpers.
