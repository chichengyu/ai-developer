# 2026-08-08 (round 10) -- Audit fixes, source backup restore, stricter types

### Fixed

- `scripts/build_linux.ps1` -- Go builds no longer pass the Windows-only
  `-H windowsgui` linker flag.
- `scripts/build_go_fyne.ps1` -- fixed broken EXE-name derivation when
  `-Strip` / `-NoConsole` rebuild the binary.
- `scripts/build_go_wails.ps1` -- corrected the `-Nsis` comment to match
  the actual switch default.
- `scripts/build_qt.ps1` -- only passes `--qmldir` to windeployqt when the
  project actually contains a `qml` directory.
- `scripts/media_downloader.py` -- servers without `Content-Length` now
  fall back to a single-stream download instead of passing `None` into
  the chunk map builder.
- `scripts/media_dependencies.py` -- dependency status now returns real
  booleans for `ffmpeg` / `ffprobe`.
- `scripts/hls_downloader.py` -- AES IV parsing also accepts an uppercase
  `0X` prefix.
- `scripts/media_parser.py`, `scripts/task_queue.py`,
  `scripts/hls_downloader.py`, `scripts/media_pipeline_service.py` --
  fixed all remaining mypy errors (13 findings) and made mypy clean.
- `SKILL.md` -- Step 4.2 now documents press and release as two separate
  `SendInput` calls, matching the smoke-test regression guard.
- `SKILL.md` -- corrected the mobile skill name in the out-of-scope table.

### Added

- Restored source preservation integration: `-BackupSource` on
  `scripts/build_python.ps1` and `scripts/build_dotnet.ps1` creates a
  timestamped source zip before the build starts.
- `scripts/backup_source.ps1` now excludes the `source_backup` folder so
  repeated backups never archive previous backups.
- `tests/smoke_windows.ps1` -- backup-source smoke test and platform-flag
  regression checks for `build_linux.ps1` / `build_go_fyne.ps1`.
- `tests/smoke_linux.sh` / `tests/smoke_macos.sh` -- run `test_docs.py`,
  `test_media_pipeline.py`, and `test_arch_awareness.ps1` when Python /
  PowerShell are available.
- `tests/test_docs.py` -- structural checks for source-preservation docs,
  `-BackupSource` wiring, README layout, and the SendInput batching rule.
