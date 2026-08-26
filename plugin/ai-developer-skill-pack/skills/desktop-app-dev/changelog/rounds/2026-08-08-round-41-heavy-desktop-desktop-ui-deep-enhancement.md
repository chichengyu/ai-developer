# 2026-08-08 (round 41) -- Heavy desktop + desktop UI deep enhancement

### Added

- `references/heavy_desktop_playbook.md` -- layered architecture + DI,
  virtualization / paging matrix, long-running job persistence,
  startup/memory profiling, single-instance / crash readiness, plugin
  isolation, and 100k-row acceptance.
- `references/desktop_ui_playbook.md` -- design tokens, theme registry,
  control catalog, layout, data grids, keyboard interaction, state
  management, accessibility, and UI performance.
- `templates/heavy_desktop_acceptance.md` -- fill-in acceptance for data
  volume, architecture, long jobs, performance, stability, windows, and
  plugins.
- `templates/desktop_ui_tokens.json` -- one token source with light / dark /
  high-contrast colors, typography, spacing, radii, dimensions, and motion.
- `templates/desktop_ui_checklist.md` -- deep UI acceptance across theming,
  layout, controls, interaction, accessibility, performance, and
  screenshots.
- `scripts/heavy_desktop_verify.ps1` -- starts or attaches to a desktop
  app, measures cold start / working set / private memory / CPU, and writes
  an optional JSON report; includes `-SelfTest`.

### Docs

- `SKILL.md` adds Step 4.8 (heavy desktop) and Step 4.9 (desktop UI),
  new Step 6 release gates, and links to the new references / templates.
- `README.md`, `INDEX.md`, and `references/ui_hard_requirements.md` add
  entry points for heavy desktop and deep desktop UI work.

### Tests

- `tests/test_docs.py` verifies the two new playbooks, acceptance
  templates, token JSON, and `heavy_desktop_verify.ps1`.
- `tests/smoke_windows.ps1` adds the profiler self-test and heavy/UI
  wiring checks; 123/123 pass.
