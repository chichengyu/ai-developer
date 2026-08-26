# 2026-08-08 (round 14) -- Framework selector/matrix alignment

### Fixed

- `scripts/select_framework.py` -- added the missing `walk` framework so
  the selector now scores all 24 canonical frameworks advertised by the
  matrix instead of 23.
- `scripts/toolchain_map.json` -- added `walk` to the Go toolchain mapping.
- `SKILL.md` -- framework matrix now includes `C# / WinForms` and
  `Python / GTK`, matching the selector and deep-dive matrix.
- `references/framework_matrix.md` -- added the `C# / WinForms` deep-dive
  section and corrected the 24-framework count.
- `references/framework_matrix.md` -- removed duplicated quick-verdict
  bullets for Rust/Go teams.
- `templates/gui_framework_decision_tree.md` -- fixed the stale
  `CommunityToolkit.Wpfdataload` typo and clarified the Avalonia
  anti-pattern for Windows-only apps.
- `scripts/build_dotnet.ps1` -- accepts `-OutputDir` and no longer assumes
  the project targets `net8.0` when reporting the publish output.

### Added

- `tests/test_docs.py` -- structural checks that the selector, SKILL
  matrix, and framework matrix all agree on the 24-framework set, plus
  duplicate-bullet and toolkit-typo guards.
