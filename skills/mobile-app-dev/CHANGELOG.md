# Changelog

## 1.1.0 -- 2026-08-07

### Added

- `scripts/select_framework.py` -- CLI implementation of Step 1.5.
- `scripts/plan_project.py` -- generates `requirements.md` and a
  task DAG in `tasks.md`.
- `scripts/scaffold_project.py` -- project skeleton generator for
  Flutter, React Native, Compose, SwiftUI, MAUI, KMP, Capacitor, and
  Tauri Mobile.
- `scripts/generate_store_metadata.py` -- drafts App Store, Play
  Store, screenshot, and privacy-label documents.
- `scripts/verify_mobile.ps1` plus `templates/verification_report.md`
  for the Step 5 smoke pass.
- CI skeletons under `templates/ci/` for GitHub Actions, GitLab CI,
  and Bitrise.
- Capacitor and Tauri Mobile build scripts, deep dives, and starter
  examples.
- `references/security_hardening.md` for secrets, attestation, and
  data-at-rest controls.
- `templates/wearable_decision_tree.md` plus watchOS, visionOS, and
  Wear OS starter examples.
- Smoke tests for the new Python tools.
- `scripts/setup_toolchain.py` -- checks or installs the SDK and
  toolchain for the selected framework (`--check-only` by default,
  `--install` opt-in).

## 1.0.1 -- 2026-08-07

### Fixed

- Android build script now computes Gradle flavor task names correctly
  (`assembleProductionRelease`, not `assembleRelease-production`) and
  runs the wrapper with `-p <ProjectDir>`.
- React Native build script is config-aware for Android
  (`bundleRelease` / `bundleDebug`), accepts a configurable
  `-ProjectDir`, maps `-Platform both` to EAS `all`, and looks for
  `.app` / `.ipa` outputs.
- .NET MAUI build script accepts `-ProjectDir` instead of hardcoding
  `./src/MyApp`, and passes the resolved `.csproj` to dotnet.
- Flutter build script runs `flutter pub get --offline` instead of
  passing an invalid `--offline` to `flutter build`, and refuses iOS
  builds on Windows / Linux.
- Swift build script actually uses `-VerboseXcodebuild` and fixes the
  test step naming to match `build-for-testing`.
- KMP build script accepts `-IosScheme` and `-AndroidModule` instead of
  hardcoding `iosApp` / `composeApp`.
- Android signing script fails in `-NonInteractive` mode when either
  password env var is missing.
- Flutter module test no longer silently ignores missing required
  tokens.
- Android build script runs unit tests unless `-SkipTests`.
- Android signing writes the keystore path with forward slashes so
  Java properties does not mangle Windows paths.
- iOS signing accepts an existing Matchfile and makes `-Readonly`
  actually fetch certs.
- Swift build script rejects archiving simulator destinations.
- React Native build script fails fast when npm is missing and tests
  are requested.
- Compose examples run mock IO on `Dispatchers.IO`, and the news-feed
  list card no longer fills the whole viewport.

### Added

- `tests/test_no_bom.py` -- guards every text file against BOM headers
  and embedded U+FEFF.
- `tests/test_references_exist.py` -- verifies backticked paths in the
  main docs and example READMEs resolve.
- Hard native constraint for hardware-backed key storage
  (Secure Enclave / StrongBox) in Step 1.5.
- Team profile section in the requirements checklist and matching
  fixture schema.
- Entitlements guidance in the Info.plist template.

### Changed

- Project metadata renamed from `mobile-app-dev-ios` to
  `mobile-app-dev` and versioned to match the changelog.
- Fixed stale split-skill paths in the example READMEs and corrected
  build-script parameter documentation.
- Aligned the fixture Kotlin version with the version catalog and
  fixed the CocoaPods offline flag (`--no-repo-update`).

## 1.0.0 -- 2026-08-07

**Consolidated re-architecture.** Replaces the four split skills
(`mobile-app-dev-ios`, `mobile-app-dev-android`, `mobile-app-dev-flutter`,
`mobile-app-dev-react-native`) with a single unified `mobile-app-dev` skill
that **deeply analyzes requirements and auto-selects the most appropriate
language and framework** (Step 1.5 in the workflow).

### Added

- **Step 1.5 -- auto-select framework**. Deterministic decision tree
  over requirements + team profile + existing codebase. Documented in
  `references/auto_selection.md` with worked examples.
- **`references/auto_selection.md`** -- canonical decision tree with
  algorithm, output schema, confidence levels, and 5 worked examples.
- **Framework deep dives consolidated** under `references/`:
  - `ios_deep_dive.md` (Swift + SwiftUI)
  - `android_deep_dive.md` (Kotlin + Compose + Hilt + Room)
  - `flutter_deep_dive.md` (Dart + Riverpod)
  - `react_native_deep_dive.md` (RN New Arch + zustand)
  - `maui_deep_dive.md` (.NET MAUI)
  - `kmp_deep_dive.md` (Kotlin Multiplatform)
- **3 production-shape examples**: `compose-news-feed`,
  `flutter-news-feed`, `rn-news-feed`.
- **Additional fixtures** in `tests/fixtures/`: `libs.versions.toml`,
  `pubspec.yaml`, `analysis_options.yaml`, `package.json`,
  `babel.config.js`.
- **Consolidated smoke tests** with `tests/verify_all.py` runner.

### Removed

- `mobile-app-dev-ios/`
- `mobile-app-dev-android/`
- `mobile-app-dev-flutter/`
- `mobile-app-dev-react-native/`

All content merged into `mobile-app-dev/`. The deep-dive references
are kept under their original names (`compose_deep_dive.md`,
`flutter_state_management.md`, etc.) for back-compat with anyone who
linked to them externally.

## 0.1.0 -- 2026-08-06

Initial scaffold of the `mobile-app-dev-ios` skill, peer to `desktop-app-dev`.
