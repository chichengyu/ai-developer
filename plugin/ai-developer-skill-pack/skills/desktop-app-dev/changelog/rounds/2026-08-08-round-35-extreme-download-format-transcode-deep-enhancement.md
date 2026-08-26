# 2026-08-08 (round 35) -- Extreme download + format transcode deep enhancement

### Added

- `scripts/media_downloader.py` -- adaptive AIMD concurrency with a
  sliding-window speed tracker (live speed / ETA in progress), slow-shard
  restart with per-chunk cancellation and restart limit, and a 1-byte
  Range GET fallback when HEAD hides the file size.
- `scripts/media_session.py` -- `Content-Range` parsing so chunked resume
  works even when servers omit `Accept-Ranges`.
- `scripts/hls_downloader.py` -- segment retries with backoff,
  `#EXT-X-BYTERANGE` byte-range segments, `#EXT-X-MAP` init segment
  download, suffix-aware segment naming, and direct concatenation
  fallback when ffmpeg is absent.
- `scripts/media_parser.py` -- `#EXT-X-MAP`, `#EXT-X-BYTERANGE`, and
  `#EXT-X-ENDLIST` parsing with sequential byte-range offsets.
- `scripts/ffmpeg_transcoder.py` -- named format presets
  (mp4/mp4-hq/hevc/hevc-hq/webm/mp3/m4a/wav/flac/mkv/mov), GPU encoder
  auto-detection (NVENC/AMF/QSV/VideoToolbox), smart copy/remux when
  source codecs already match the target, resolution/bitrate/fps/audio
  options, `build_ffmpeg_args()` for testable command construction, and a
  `--list-profiles` CLI.
- `scripts/media_pipeline_service.py` -- download / HLS / transcode
  payload options forwarded to the engine plus `POST /media/probe` for
  local media inspection.

### Tests

- `tests/test_media_pipeline.py` -- 8 new cases (speed tracker/tuning,
  adaptive download, Content-Range fallback, HLS BYTERANGE / init /
  fallback merge, transcode presets / hardware / copy, fake-ffmpeg
  progress, sidecar probe, sidecar transcode options); 64/64 pass.

### Docs

- `references/media_acquisition_playbook.md` and
  `references/media_pipeline_clients.md` updated with the new download,
  HLS, transcode, and probe APIs.
