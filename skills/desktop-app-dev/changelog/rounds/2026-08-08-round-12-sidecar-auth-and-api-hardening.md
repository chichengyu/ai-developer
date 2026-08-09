# 2026-08-08 (round 12) -- Sidecar auth and API hardening

### Added

- `scripts/media_pipeline_service.py` -- optional `--token` Bearer auth
  for every endpoint except `/health`.
- `clients/` -- all 8 wrappers accept an optional token and send
  `Authorization: Bearer <token>`.
- `templates/security_checklist.md` -- local sidecar binding and token
  requirement.
- `templates/release_checklist.md` -- clean-machine one-click media
  runtime install verification.
