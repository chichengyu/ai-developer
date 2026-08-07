# mobile-app-dev

Consultative Codex skill for shipping mobile applications across
iOS, iPadOS, Android, watchOS, visionOS, and Wear OS. **Step 1.5
auto-selects the most appropriate language and framework from your
requirements**, so you do not have to compare 9 frameworks by hand.

Peer to `desktop-app-dev`. Use this when the deliverable is a real
mobile app that will run on a phone, tablet, or watch.

## Entry point

`SKILL.md` -- read this first. It defines the 8-step workflow
(requirements -> classify -> **auto-select** -> decompose -> patterns
-> package -> verify -> hand off) plus the "When NOT to use"
anti-trigger.

## When to use

Reach for this skill whenever the user asks for:

- A new iOS, iPadOS, Android, watchOS, visionOS, or Wear OS app.
- A rewrite / port of an existing app to native or cross-platform mobile.
- "Pick the right mobile framework" (Step 1.5 does this).
- Adding push notifications, deep linking, in-app purchase, biometric auth.
- Shipping to the App Store, Play Store, TestFlight, internal track,
  or enterprise MDM.
- Migrating from one mobile framework to another.

## When NOT to use

- CLI tools, libraries, servers, embedded firmware.
- Windows / macOS / Linux desktop GUI.
- Web apps / SPAs / browser extensions.
- Game engines (Unity, Unreal, Godot) -- those have their own pipelines.
- Single-purpose scripts under ~200 lines.
- Build-only fixes in an existing mobile app -- go straight to the
  relevant `build_*.ps1` and `references/distribution_playbook.md`.

## Layout

```
SKILL.md                          8-step workflow + When-NOT-to-use
README.md                         this file
CHANGELOG.md                      what changed and when
LICENSE                           MIT
pyproject.toml                    ruff + mypy config
.gitignore                        skill-internal ignores
agents/openai.yaml                skill display metadata

references/
  auto_selection.md               Step 1.5 decision tree (canonical)
  framework_matrix.md             pros / cons / IDE setup per framework
  task_decomposition.md           Step 0+3 deep dive, worked examples
  distribution_playbook.md        per-framework packaging, signing, Fastlane
  signing_certificates.md         iOS cert types, Android keystore
  lifecycle_patterns.md           iOS scene / Android lifecycle, state restore
  state_management.md             SwiftUI / Compose / Flutter / RN
  restricted_network_playbook.md  offline builds, vendoring, mirrors

  ios_deep_dive.md                Swift + SwiftUI patterns
  android_deep_dive.md            Kotlin + Compose + Hilt + Room
  flutter_deep_dive.md            Dart + Riverpod / Bloc + go_router
  react_native_deep_dive.md       RN New Arch + zustand + Reanimated
  maui_deep_dive.md               .NET MAUI + XAML
  kmp_deep_dive.md                Kotlin Multiplatform + shared logic

  compose_deep_dive.md            (folded into android_deep_dive -- kept for back-compat)
  android_architecture.md         (folded into android_deep_dive -- kept for back-compat)
  gradle_kts_patterns.md          (folded into android_deep_dive -- kept for back-compat)
  flutter_state_management.md     (folded into flutter_deep_dive -- kept for back-compat)
  flutter_performance.md          (folded into flutter_deep_dive -- kept for back-compat)
  new_architecture.md             (folded into react_native_deep_dive -- kept for back-compat)
  rn_state_management.md          (folded into react_native_deep_dive -- kept for back-compat)
  capacitor_deep_dive.md          Capacitor thin-shell patterns
  tauri_mobile_deep_dive.md       Tauri Mobile Rust + WebView patterns
  security_hardening.md           secrets, attestation, data at rest

templates/
  requirements_checklist.md       Step 0 fill-in (includes team profile)
  task_card.md                    one per atomic task in Step 2
  Info.plist.xml                  minimal iOS plist
  AndroidManifest.xml             minimal Android manifest
  build.gradle.kts                module-level Kotlin DSL
  verification_report.md          Step 5 device checklist
  wearable_decision_tree.md       watchOS / visionOS / Wear OS picker
  ci/                             GitHub Actions / GitLab / Bitrise templates

scripts/
  build_swift_ios.ps1             xcodebuild + archive + export
  build_kotlin_android.ps1        gradle assembleRelease / bundleRelease
  build_flutter.ps1               flutter build ipa / appbundle
  build_react_native.ps1          RN build-ios + Android bundle
  build_dotnet_maui.ps1           dotnet publish -f net8.0-ios / android
  build_kmp.ps1                   Xcode + Gradle for KMP module
  build_capacitor.ps1             cap sync + native build
  build_tauri_mobile.ps1          Tauri mobile build
  setup_ios_signing.ps1           Fastlane match-based cert minting
  setup_android_signing.ps1       keytool upload keystore minting
  threading_swiftui.swift         Task + @MainActor bridge
  threading_compose.kt            coroutine + StateFlow bridge
  threading_flutter.dart          riverpod AsyncNotifier
  threading_react_native.tsx      useQuery + Suspense
  select_framework.py             Step 1.5 auto-selection CLI
  plan_project.py                 requirements + task DAG generator
  scaffold_project.py             project skeleton generator
  generate_store_metadata.py      store metadata drafts
  verify_mobile.ps1               smoke checks + verification report

examples/                         minimal runnable projects
  swiftui-counter/                SwiftUI + @Observable + Task
  compose-counter/                Jetpack Compose + ViewModel + Flow
  flutter-counter/                Flutter + riverpod Notifier
  react-native-counter/           RN + zustand
  compose-news-feed/              Compose + Hilt + StateFlow + Repository
  flutter-news-feed/              Riverpod + AsyncNotifier + overrides
  rn-news-feed/                   zustand + FlatList + RefreshControl + a11y
  capacitor-starter/              Capacitor thin shell
  tauri-starter/                  Tauri Mobile starter
  watchos-starter/                watchOS SwiftUI starter
  visionos-starter/               visionOS RealityKit starter
  wearos-starter/                 Wear OS Compose starter

tests/                            smoke-test fixtures + runners
  test_plist_parse.py             Info.plist.xml well-formed
  test_gradle_config.py           build.gradle.kts has required entries
  test_requirements_parse.py      requirements.json schema OK
  test_compose_module_parse.py    compose-news-feed structure OK
  test_flutter_module_parse.py    flutter-news-feed uses Riverpod
  test_rn_module_parse.py         rn-news-feed uses zustand + a11y
  test_no_bom.py                  no BOM / U+FEFF in text files
  test_references_exist.py        documented paths resolve
  test_select_framework.py        decision tree smoke tests
  test_plan_project.py            requirements/tasks generation
  test_scaffold_project.py        scaffold generation
  test_store_metadata.py          store metadata generation
  verify_all.py                   runs all tests + reports
  fixtures/                       Info.plist.xml, build.gradle.kts,
                                  requirements.json, libs.versions.toml,
                                  pubspec.yaml, analysis_options.yaml,
                                  package.json, babel.config.js
```

## Quick recipe -- I do not know which framework to pick

1. Fill `templates/requirements_checklist.md` (seven-bucket interrogation
   + team profile).
2. Run Step 1.5 from `SKILL.md` (the auto-select algorithm).
   - For full decision tree, see `references/auto_selection.md`.
   - Or automate: `python scripts/select_framework.py requirements.json`.
3. Once the framework is picked, jump to its deep-dive reference:
   - `references/ios_deep_dive.md` (Swift + SwiftUI)
   - `references/android_deep_dive.md` (Kotlin + Compose)
   - `references/flutter_deep_dive.md` (Flutter + Riverpod)
   - `references/react_native_deep_dive.md` (React Native)
   - `references/maui_deep_dive.md` (.NET MAUI)
   - `references/kmp_deep_dive.md` (Kotlin Multiplatform)
4. Decompose tasks with `templates/task_card.md`.
   - Or automate: `python scripts/plan_project.py --requirements
     requirements.json --output-dir plan`.
5. Drop in `scripts/threading_<framework>` for the async bridge.
6. Generate a starter with `python scripts/scaffold_project.py
   --framework <framework> --name MyApp`, or package with
   `scripts/build_<framework>_*.ps1`.
7. Sign with `scripts/setup_<os>_signing.ps1`.
8. Or point at the matching `examples/<framework>-counter/` to start.

## Quick recipe -- I already picked the framework

Same as above, but skip Step 1.5 and go straight to the framework's
deep-dive reference (see step 3 in the previous recipe).

## Conventions in this skill

- Step numbering is 0-6; do not skip Step 0, 1.5, or 2.
- Every task card has explicit acceptance criteria and a verification
  method that is testable on a real device or simulator.
- Every build script has a documented `param` block and validates the
  host/tooling before running a real build.
- Every threading template shows the right async primitive for that
  framework.
- Examples mirror the threading templates in `scripts/`; keep the
  snippets in sync when a template changes.

## Linting

```powershell
pip install ruff mypy
ruff check .
ruff format --check .
mypy tests/*.py
```

## Related skills

- `desktop-app-dev` -- Windows desktop GUI, peer skill.
- `mac-app-dev` -- planned, not yet built.
- `linux-app-dev` -- planned, not yet built.
- A web-app skill -- for browser-delivered apps.
- A game-engine skill -- for Unity / Unreal / Godot.
