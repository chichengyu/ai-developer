# 2026-08-08 (round 18) -- Media path hardening and CI doc drift

### Added

- `media_downloader.safe_output_name` -- shared sanitizer for URL-derived
  filenames; `media_pipeline_service._filename_from_url` and
  `hls_downloader.download_hls` now reject `..`, path separators, control
  characters, Windows-reserved names, and trailing dots/spaces.
- `media_dependencies._zip_member_is_safe` -- refuses absolute, drive,
  and `..` zip entries before extracting the portable ffmpeg archive.
- Media sidecar returns 400 for non-object JSON, invalid priority /
  max_attempts / resume_token / payload, and malformed Content-Length;
  request bodies over 16 MiB return 413.
- Bearer token checks now use constant-time `hmac.compare_digest`.
- Regression tests for filename sanitization, zip safety, and bad API
  payloads; doc checks guard INDEX/README CI wording.

### Fixed

- INDEX.md and smoke_linux.sh still referenced `ubuntu-latest` while CI
  is pinned to `ubuntu-22.04`.
- README CI table omitted `--check` from the `ruff format` job.
- CI header comment said `ubuntu-latest` for the Linux job.

### Verified

- `smoke_windows.ps1` -- 77 / 77
- `test_arch_awareness.ps1` -- 16 / 16
- `test_docs.py` -- 529 checks
- `test_no_bom.py` -- 173 files, 0 BOM / U+FEFF
- media pipeline -- 15 / 15; selector self-test -- 8 / 8; VK table --
  119 keys / 10 templates
