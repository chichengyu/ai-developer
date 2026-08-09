# 2026-08-07 (round 5) -- Environment bootstrap

### Added

- `scripts/bootstrap_environment.ps1` -- auto-selects the framework via
  `select_framework.py --json`, or accepts `-Framework`, then detects and
  installs the matching SDK / toolchain with winget / pip.
- `scripts/toolchain_map.json` -- framework-to-toolchain mapping for all
  canonical frameworks.
- `tests/fixtures/sample_brief.json` plus smoke coverage for the bootstrap
  dry run and JSON validity.
- SKILL.md Step 2.5, README layout, and INDEX environment setup section.
