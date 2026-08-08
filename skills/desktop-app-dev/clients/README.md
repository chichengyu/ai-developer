# Media pipeline clients

Minimal HTTP client wrappers for the local media pipeline service
(`scripts/media_pipeline_service.py`). Each wrapper can enqueue a task,
read one task, check dependency status / progress, and start the
dependency install.

Files:

| Language | File |
|---|---|
| TypeScript / JavaScript | `media_client.ts` |
| C# / .NET | `MediaClient.cs` |
| Go | `media_client.go` |
| Rust | `media_client.rs` |
| Kotlin / JVM | `MediaClient.kt` |
| Swift | `MediaClient.swift` |
| Java | `MediaClient.java` |
| C++ | `media_client.cpp` |

These are starting templates, not compiled here. Install the matching
HTTP/JSON dependency in your project (fetch / HttpClient / reqwest /
OkHttp / URLSession / java.net.http / libcurl), then run the service:

```powershell
python scripts/media_pipeline_service.py --db app.sqlite --port 8765
```

When the service starts with `--token <token>`, every client sends
`Authorization: Bearer <token>`. The wrappers accept the token as the
second constructor argument.

Example task:

```json
{"kind": "download", "payload": {"url": "https://example.com/video.mp4", "dest": "out/video.mp4"}, "dedupe_key": "sha256:url"}
```

## Live progress

Every wrapper exposes `taskProgress(id)` and `taskEvents(id, after)` so the
UI can poll real-time snapshots without reimplementing the engine.

Every wrapper also exposes `formats()` (named `FormatsAsync` / `Formats`
in C# / Go) to load the unified format catalog from `GET /formats`.
Task kinds include `download`, `batch-download`, `hls`, `transcode`,
`convert`, `batch-convert`, `analyze`, `crawl`, `webdata`, and `publish`.

```text
GET /tasks/<id>/progress
GET /tasks/<id>/events?after=<event-count>&timeout=<0-30>
```

`/tasks/<id>/progress` returns `status`, `stage`, `progress` (0.0 to 1.0),
and `progress_meta`. The `progress_meta` object includes the fields that
match the current kind:

- download: `downloaded`, `total`, `percent`, `speed`, `speed_avg`, `eta_s`,
  `chunks_done`, `chunks_total`, `merge_done`, `merge_total`, `elapsed_s`,
  `phase`
- hls: `done`, `total`, `percent`, `downloaded_bytes`, `total_bytes`,
  `output_size`, `stage`
- transcode: `percent`, `out_time_s`, `speed`, `fps`, `bitrate`,
  `input_size`, `output_size`, `duration_s`, `remaining_s`, `frame`, `state`
- convert: `input_size`, `output_size`, `percent`, `stage`, `elapsed_s`
- batch-convert: `done`, `total`, `input_bytes_done`, `total_input_bytes`,
  `output_bytes`, `current`, `percent`, `elapsed_s`

`/tasks/<id>/events` returns ordered `events` plus `next`; each event has
`stage`, `percent`, `message`, `meta`, and `at`. Poll with `after=next` to
receive only new events. Pass a positive `timeout` (up to 30 seconds) to
long-poll: the request waits for the next event instead of returning
immediately, which gives near-real-time updates without busy polling.

The `taskEvents` wrappers accept an optional `timeout` argument:
`taskEvents(id, after, timeout)`.

The TypeScript and Go wrappers also include `watchProgress(id, callback)`
helpers that poll until the task reaches `succeeded`, `failed`, or
`cancelled`.
