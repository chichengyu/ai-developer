# Media pipeline clients for every desktop language

The media engine is a Python sidecar exposed as a local HTTP service
(`scripts/media_pipeline_service.py`) and a dependency installer
(`scripts/setup_media_dependencies.ps1` / `scripts/media_dependencies.py`).
Any desktop UI language can enqueue tasks and poll progress without
reimplementing crawler, HLS, chunked download, ffmpeg, or SQLite queue
logic.

Ready-made wrapper templates live in `clients/`: TypeScript, C# / .NET,
Go, Rust, Kotlin, Swift, Java, and C++.

Start the service once per app session:

```powershell
python scripts/media_pipeline_service.py --db C:\app\media_tasks.sqlite --port 8765
```

Security: start the service with `--token <random-per-session-token>`.
Every request except `/health` must then send
`Authorization: Bearer <token>`.

Enqueue pattern for every client:

```text
POST /tasks
{"kind": "download", "payload": {"url": "...", "dest": "C:\\out\\video.mp4"}, "dedupe_key": "sha256(url)"}

GET /tasks/<id>
GET /tasks/<id>/progress
GET /tasks/<id>/events?after=<event-count>&timeout=<0-30>
```

`/tasks/<id>/progress` returns `status`, `stage`, `progress`, and
`progress_meta`. Download snapshots include total file size, downloaded
bytes, percent, speed, ETA, chunk counts, merge progress, and elapsed time;
HLS snapshots include segment counts plus downloaded/merged bytes; transcode
snapshots include input/output bytes, duration, remaining time, fps,
bitrate, and frame. `/tasks/<id>/events` returns ordered live events with
the same `meta` and a `next` cursor. Pass `timeout` up to 30 to long-poll
for the next event instead of returning immediately.

`GET /formats` returns the unified target catalog:

```json
{
  "count": 100,
  "categories": [{"id": "video", "label": "Video"}, ...],
  "formats": [{"extension": "mp4", "category": "video", "engine": "ffmpeg", ...}]
}
```

Every client wrapper ships `formats()` / `Formats()` / `FormatsAsync()`
for this endpoint.

Supported `kind` values:

- `analyze` -- deep page parse: metadata, embedded JSON state, API
  endpoints, JSON media URLs, pagination fields, and detected CAPTCHA
  challenges.
- `crawl` -- parse a page and enqueue media downloads; pass
  `"deep": true` in the payload to include the page-data summary.
- `download` -- chunked file.
- `batch-download` -- multiple files with aggregate bytes / speed / ETA.
- `hls` -- m3u8 stream.
- `transcode` -- ffmpeg.
- `convert` -- single-file conversion through
  `scripts/file_converter.py` (ffmpeg + stdlib + copy + optional).
- `batch-convert` -- folder conversion with aggregate byte-based progress.
- `publish` -- platform adapter.

Analyze payload options: `base_url`, `include_data`, `headers`, `proxy`.
Crawl payload options: `deep`, `download`, `dest_dir`, `base_url`,
`headers`, `proxy`. Download payload options: `concurrency`,
`chunk_size`, `chunk_retries`, `resume`, `headers`, `proxy`,
`adaptive_concurrency` (default true), `slow_shard_switch` (default
true), `slow_after_seconds`, `slow_idle_seconds`, `slow_restart_limit`,
`tune_interval`, and `auto_chunk_sizing` (default true). HLS payload
options: `concurrency`, `quality`
(zero-based variant index), `segment_retries`, `merge_fallback`,
`keep_segments`, `headers`, `proxy`.
`batch-download` payloads take `urls` and `dest_dir` plus the same
per-file options as `download`; their `progress_meta` includes `done` /
`total`, `downloaded_bytes`, `total_bytes`, `speed`, `eta_s`, `current`,
and `elapsed_s`. Transcode payload options:
`profile` (mp4 / mp4-hq / hevc / hevc-hq / webm / avi / ts / ogg /
ogg-audio / gif /
mp3 / m4a / wav / flac / opus / aac / ac3 / mkv / mov / m2ts / mpeg /
flv / wmv / m4v / 3gp / ogv / vob / asf / mka / oga / aiff / wma / amr /
mp2 / dts / eac3 / m4b / alac / jpg / png / bmp / tiff / webp / avif /
heic / jxl / ico), `video_codec`,
`video_preset`, `crf`, `audio_codec`,
`audio_bitrate`, `video_bitrate`, `resolution`, `fps`,
`audio_channels`, `audio_sample_rate`, `smart_copy` (default true),
`hardware` (true or an encoder name), `faststart`, `audio_only`,
`start_time`, `duration`, `threads`, and `extra_args`.
Download payloads also accept `max_speed_bytes_per_sec` to cap total
throughput across all shards.
All fetch-based kinds also accept `min_interval`, `jitter`, `max_retries`,
`backoff_base`, `backoff_max`, `robots_text`, `adaptive_throttle`,
`throttle_base_delay`, `throttle_max_delay`, and `user_agent` for polite,
rate-limited crawling.

`convert` payloads take `src`, `dst`, optional `profile`, and `extra_args`;
`batch-convert` payloads take `srcs` (list of file paths), `output_dir`,
and `target` (one catalog extension, e.g. `mp3` or `html`). Their
`progress_meta` includes `input_size`, `output_size`, `percent`, `stage`,
and for batches `done` / `total`, `input_bytes_done`,
`total_input_bytes`, `output_bytes`, `current`, and `elapsed_s`.

To inspect a local media file before transcoding, call
`POST /media/probe` with `{"path": "C:\\media\\input.mp4"}`; the response
contains duration, streams, codecs, and resolution when ffprobe is
available.

## Python

```python
from task_queue import TaskQueue

queue = TaskQueue("media_tasks.sqlite")
task = queue.enqueue(
    "download",
    {"url": "https://example.com/video.mp4", "dest": "out/video.mp4"},
    dedupe_key="sha256:url",
)
```

## C# / .NET

```csharp
using System.Net.Http.Json;

var http = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:8765") };
var body = new {
    kind = "download",
    payload = new { url = "https://example.com/video.mp4", dest = @"C:\out\video.mp4" },
    dedupe_key = "sha256:url"
};
var task = await http.PostAsJsonAsync("/tasks", body);
var json = await task.Content.ReadAsStringAsync();
```

## JavaScript / TypeScript

```ts
const response = await fetch("http://127.0.0.1:8765/tasks", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    kind: "download",
    payload: { url: "https://example.com/video.mp4", dest: "C:/out/video.mp4" },
    dedupe_key: "sha256:url"
  })
});
const task = await response.json();
```

## Go

```go
payload := map[string]any{
    "kind":       "download",
    "payload":    map[string]any{"url": "https://example.com/video.mp4", "dest": `C:\out\video.mp4`},
    "dedupe_key": "sha256:url",
}
buf, _ := json.Marshal(payload)
resp, err := http.Post("http://127.0.0.1:8765/tasks", "application/json", bytes.NewReader(buf))
```

## Rust

```rust
let body = serde_json::json!({
    "kind": "download",
    "payload": {"url": "https://example.com/video.mp4", "dest": r"C:\out\video.mp4"},
    "dedupe_key": "sha256:url"
});
let task = reqwest::Client::new()
    .post("http://127.0.0.1:8765/tasks")
    .json(&body)
    .send()
    .await?
    .json::<serde_json::Value>()
    .await?;
```

## Kotlin / JVM

```kotlin
val client = OkHttpClient()
val body = """
    {"kind":"download","payload":{"url":"https://example.com/video.mp4","dest":"C:\\out\\video.mp4"},"dedupe_key":"sha256:url"}
""".trimIndent()
val request = Request.Builder()
    .url("http://127.0.0.1:8765/tasks")
    .post(body.toRequestBody("application/json".toMediaType()))
    .build()
val task = client.newCall(request).execute().body!!.string()
```

## Swift

```swift
var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/tasks")!)
request.httpMethod = "POST"
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = """
{"kind":"download","payload":{"url":"https://example.com/video.mp4","dest":"C:\\out\\video.mp4"},"dedupe_key":"sha256:url"}
""".data(using: .utf8)
URLSession.shared.dataTask(with: request) { data, _, _ in
    print(String(data: data ?? Data(), encoding: .utf8) ?? "")
}.resume()
```

## Java

```java
HttpClient client = HttpClient.newHttpClient();
String body = """
    {"kind":"download","payload":{"url":"https://example.com/video.mp4","dest":"C:\\out\\video.mp4"},"dedupe_key":"sha256:url"}
    """;
HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://127.0.0.1:8765/tasks"))
    .header("Content-Type", "application/json")
    .POST(HttpRequest.BodyPublishers.ofString(body))
    .build();
client.send(request, HttpResponse.BodyHandlers.ofString());
```

## C++

```cpp
// libcurl example
curl_easy_setopt(curl, CURLOPT_URL, "http://127.0.0.1:8765/tasks");
curl_easy_setopt(curl, CURLOPT_POST, 1L);
const char* body = R"({"kind":"download","payload":{"url":"https://example.com/video.mp4","dest":"C:\\out\\video.mp4"},"dedupe_key":"sha256:url"})";
curl_easy_setopt(curl, CURLOPT_POSTFIELDS, body);
curl_easy_perform(curl);
```

## Dependency install from the desktop UI

The UI shows one button. Clicking it calls:

```text
POST /deps/install
```

The service starts a background install thread. The UI polls
`GET /deps/progress` for stage / percent / message and
`GET /deps/status` for live readiness:

```json
{
  "playwright": true,
  "pycryptodome": true,
  "chromium": true,
  "ffmpeg": true,
  "ffprobe": true,
  "ready": true
}
```

The same operation is available outside the app:

```powershell
powershell -File scripts/setup_media_dependencies.ps1 -Install
```

`-Install` is explicit; without it the script only checks.

This is the global `界面硬性要求` UI-19 flow: the app manages the runtime
inside its own directory, the user only clicks `安装依赖`, and the app
downloads / installs / configures everything automatically. For generic
app-local dependencies (not only media), use
`scripts/builtin_dependency_manager.py` with a JSON manifest; it supports
parallel chunked resume downloads, SHA-256 verification, safe archive
extraction, and app-local bin paths.
