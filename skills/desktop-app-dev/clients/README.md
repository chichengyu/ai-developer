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
