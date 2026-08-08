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
```

Supported `kind` values: `crawl` (parse a page and enqueue media
downloads), `download` (chunked file), `hls` (m3u8 stream),
`transcode` (ffmpeg), and `publish` (platform adapter).

Download payload options: `concurrency`, `chunk_size`, `resume`,
`headers`, `proxy`. HLS payload options: `concurrency`, `quality`
(zero-based variant index), `headers`, `proxy`.

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
