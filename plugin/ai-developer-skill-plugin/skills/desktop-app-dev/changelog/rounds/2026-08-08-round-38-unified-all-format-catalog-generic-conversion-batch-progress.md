# 2026-08-08 (round 38) -- Unified all-format catalog + generic conversion + batch progress

### Added

- `scripts/media_formats.py` -- unified format registry covering video,
  audio, image, subtitle, document, data, and archive targets, with
  ffmpeg / stdlib / copy / optional engine hints, `lookup_format()`,
  `catalog_payload()`, and a `--list` / `--lookup` CLI.
- `scripts/file_converter.py` -- generic single-file and folder conversion:
  ffmpeg for media/images, stdlib for text / markdown / HTML / CSV / JSON /
  JSONL / XML / INI / SRT / VTT / ASS and ZIP/TAR/GZ/BZ2/XZ archives, plus
  safe `extract_archive()` and aggregate byte-based `convert_many()`
  progress.
- `scripts/ffmpeg_transcoder.py` -- expanded format presets and container
  mappings: m2ts/mts, mpeg, flv, wmv, m4v, 3gp, ogv, vob, asf, mka, oga,
  aiff, wma, amr, mp2, dts, eac3, m4b, alac, and jpg/png/bmp/tiff/webp/
  avif/heic/jxl/ico image targets, plus per-codec quality args and
  single-frame image extraction.
- `scripts/media_downloader.py` -- checkpoint validation against ETag /
  Last-Modified, optional `expected_sha256` verification, `content_type` /
  `filename` on `DownloadResult`, and `download_batch()` with aggregate
  bytes, speed, ETA, and per-file progress.
- `scripts/media_pipeline_service.py` -- `GET /formats` plus
  `kind: "convert"`, `kind: "batch-convert"`, and
  `kind: "batch-download"` tasks with the same live progress/event
  contract.
- `clients/*` -- `formats()` / `Formats()` / `FormatsAsync()` wrappers in
  TypeScript, C# / .NET, Go, Rust, Kotlin, Swift, Java, and C++.
- `examples/media-toolkit/` -- runnable tkinter demo with live download
  percent / total size / speed / ETA and an all-format conversion tab.

### Tests

- `tests/test_media_pipeline.py` -- 6 new cases (format catalog/profile
  integration, text/archive/subtitle/batch conversion, ffmpeg dispatch +
  optional-target error, ETag/hash download integrity, batch download
  progress, sidecar formats + convert tasks); 78/78 pass.

### Docs

- `README.md`, `SKILL.md`, `INDEX.md`,
  `references/media_acquisition_playbook.md`,
  `references/media_pipeline_clients.md`, `clients/README.md`,
  `examples/README.md`, and `tests/README.md` updated with the unified
  format catalog, conversion kinds, batch progress, and the new example.
