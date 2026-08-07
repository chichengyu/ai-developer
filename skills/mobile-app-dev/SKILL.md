---
name: mobile-app-dev
description: Consultative Codex skill for shipping mobile applications across iOS, iPadOS, Android, watchOS, visionOS, Wear OS via an 8-step workflow: (0) deep requirements analysis; (1) app classification into utility / productivity / social / media / finance / system / IoT; (1.5) auto-select framework based on requirements + team + existing codebase; (2) decompose into tasks; (3) apply platform patterns; (4) package; (5) verify on device; (6) handoff. Frameworks covered: Swift/SwiftUI, Kotlin/Compose, Flutter, React Native, .NET MAUI, Kotlin Multiplatform, Capacitor, Tauri Mobile. Ships with multi-language threading templates, PowerShell build scripts for xcodebuild / Gradle / Flutter / RN / MAUI / KMP, signing helpers, framework deep dives, requirements + task-card templates, smoke-test fixtures.
---

# Mobile App Dev

A consultative Codex skill for shipping mobile applications. The agent that
uses this skill behaves like a mobile architect: it **first** deeply analyzes
the requirements, **then automatically selects the most appropriate language
and framework**, **then** decomposes the work into verifiable tasks, **then**
builds, **then** verifies on a real device or simulator, **then** hands off.

The auto-selection is not magic: it is a deterministic decision tree over
the seven-bucket requirements checklist (see Step 0 + Step 1.5 below). You
can always override its recommendation; if you do, document why in the
`showstoppers` field of `templates/requirements_checklist.md`.

## The 8-step workflow (apply in order)

| #     | Step                                  | Output                              |
|-------|---------------------------------------|-------------------------------------|
| 0     | Deep requirements analysis            | requirements.md                     |
| 1     | Classify the app                      | category (A/B/C/D/E/F/G/H)          |
| **1.5** | **Auto-select framework**           | **selected framework + rationale**   |
| 2     | Decompose into atomic tasks           | tasks.md (DAG with acceptance)      |
| 3     | Apply platform patterns               | project scaffold + core code        |
| 4     | Package                               | archive / bundle / installable      |
| 5     | Verify                                | verification report                 |
| 6     | Hand off                              | user-facing README + rollout notes  |

**Step 1.5 is the distinguishing feature of this skill.** The decision
tree runs against the requirements checklist (Step 0 output) and the team
profile, and returns one of:

- A single platform + framework (e.g., "Swift + SwiftUI", "Kotlin + Compose").
- Two platform + framework pairs (e.g., "Swift + SwiftUI for iOS, Kotlin + Compose for Android").
- A cross-platform framework (e.g., "Flutter", "React Native").
- A "platform-AND-native-UI" pattern (e.g., "Kotlin Multiplatform with native UI").
- A native-only or web-wrapper variant (e.g., "Capacitor / Tauri").

See `references/auto_selection.md` for the full decision tree.

---

## Scope and limits

### In scope

Mobile applications that target **iOS / iPadOS / Android / watchOS / visionOS / Wear OS**
on the following architectures:

- **arm64**   (default for all Apple silicon and 99%+ of modern Android)
- **arm64e**  (newer iPhone SoCs, special builds only)
- **x86_64**  (simulator / emulator builds on Intel/AMD hosts)
- **armv7**   (legacy Android only; explicit user request)

Per-architecture notes:

- `build_swift_ios.ps1` accepts `-Arch arm64|x86_64` (default `arm64`
  for devices, `x86_64` for simulators). Android Gradle builds choose
  ABIs through the Android build system, not through these scripts.
- Flutter / RN / MAUI produce universal binaries for App Store (single IPA
  with arm64 slice). TestFlight and Play Store tracks are split via
  Fastlane lanes, not via separate archives.
- Background work on iOS must use `Task`, `async let`, or `DispatchQueue`
  -- never raw pthreads detached to the OS. Android can use coroutines,
  WorkManager, or `JobScheduler`.

### Out of scope

Explicitly **not** covered. Do not pretend these are part of this skill.

| Domain                  | Why out of scope                              | Use instead                        |
|-------------------------|-----------------------------------------------|------------------------------------|
| Windows desktop GUI     | Win32 / SendInput / MSIX                      | `desktop-app-dev` skill            |
| macOS apps              | Code signing, notarization, DMG               | `mac-app-dev` skill (planned)      |
| Linux desktop           | Different packaging, no App Store             | `linux-app-dev` skill (planned)    |
| Web apps / SPAs         | Browser sandbox, no native shell              | a web framework skill              |
| Browser extensions      | MV3 specifics                                 | a web-extension skill              |
| CLI tools / libraries   | No UI lifecycle, no app store                 | a CLI-design skill                 |
| Server / backend        | No touch UI, no sandbox                       | a backend skill                    |
| Embedded firmware       | Bare-metal, RTOS, no SDK UI                   | a firmware skill                   |
| Game engines (Unity / Unreal / Godot) | Engine-specific build pipeline  | a game-engine skill                |

If a request falls under any "Out of scope" row, **stop and tell the user**
rather than silently producing a mobile answer.

---

## When NOT to use this skill

This skill is for shipping a mobile application. Do not reach for it if
any of the following is true:

- **The deliverable is a desktop GUI, web app, CLI, or backend.** Each has
  its own dedicated skill.
- **The deliverable is a single-purpose script under ~200 lines.** The
  8-step workflow is overkill. Skip the skill and write the script.
- **The user is researching which framework to use and wants only a
  comparison.** Hand them `references/framework_matrix.md` directly.
- **The user only wants to fix a build error in an existing mobile app.**
  Read the relevant `build_*.ps1` and `references/distribution_playbook.md`
  section, do not run the full workflow.
- **There is no real device / simulator / emulator available.** Step 5
  cannot pass; tell the user before starting.

---

## Step 0 -- Deep requirements analysis

Before picking a framework, interrogate the request across **seven buckets**.
Copy `templates/requirements_checklist.md` and fill every box; do not
paraphrase. Items marked "critical" block the workflow if unanswered.

### 0.1 Functional

- What does the app do (1 paragraph, no jargon)?
- Which screens / tabs / modals exist?
- What user actions mutate state?
- What data is read-only vs user-generated vs sync'd?
- Are there offline-first requirements? (Yes by default on mobile.)

### 0.2 Non-functional

- Cold-start budget (ms) -- mobile default <= 1.5 s on mid-tier device.
- Memory ceiling (MB) -- mobile default <= 150 MB resident.
- Battery / radio budget (mAh/hour, MB/hour) -- push/poll cadence.
- Accessibility (Dynamic Type / VoiceOver / TalkBack / contrast).
- Localization scope and RTL handling.
- Dark mode, dynamic color, system fonts.

### 0.3 Distribution **[critical]**

- **App Store / Play Store public release** -- fastest path, highest review
  friction. Required for in-app purchase, push, Sign in with Apple.
- **TestFlight / internal testing** -- fast lane, 90-day expiry on iOS,
  unlimited on Play internal track.
- **Enterprise / MDM** -- Apple Business Manager, Android Enterprise.
- **Sideload / direct APK / ad-hoc IPA** -- for unreleased or private apps.
- **PWA / TWA** -- when the user only needs a web wrapper, push the user
  to a web skill instead.

### 0.4 Integration

- Backend API surface (REST / GraphQL / gRPC, auth scheme).
- Required OS frameworks (push, location, camera, microphone, Bluetooth,
  NFC, HealthKit, ARKit, CallKit, CarPlay, etc.).
- Required third-party SDKs (analytics, ads, crash, auth, payments).
- Required hardware (minimum OS version, min RAM, sensors).

### 0.5 Failure modes

- What happens when offline? (Read-only, queued, dead-end?)
- What happens when a permission is denied? (Graceful degradation vs crash?)
- What happens when a deep link target is missing?
- What happens when the OS kills the app in the background?
- What happens on jailbroken / rooted devices? (Sensitive data only.)

### 0.6 Compliance **[critical for finance / health / kids]**

- App Store Review Guidelines (privacy nutrition labels, ATT, account
  deletion, in-app purchase disclosure).
- Play Store policy (target API level, data safety form, permissions).
- GDPR / CCPA / China PIPL / region-specific privacy.
- COPPA if the app is "directed to children under 13".
- Export compliance / encryption registration (most apps exempt, but
  HTTPS-only apps still need a CCATS in some regions).

### 0.7 Ops

- Crash reporting backend (Crashlytics / Sentry / Bugsnag / BugSight).
- Analytics backend (Firebase / Amplitude / Mixpanel / self-hosted).
- Feature flag / remote config (LaunchDarkly / Firebase RC / ConfigCat).
- CI/CD lane (GitHub Actions / Bitrise / GitLab CI / Fastlane lanes).
- Version cadence (semver, internal build number, store build number).
- Rollback plan (phased release, staged rollout, kill switch).

---

## Step 1 -- Classify the app

Map the requirements to one category. Each category has a default
framework and a default distribution plan; the user can override.

| Category | Examples                          | Default stack                          | Distribution          |
|----------|-----------------------------------|----------------------------------------|-----------------------|
| **A. Utility / tools**     | Calculator, QR scanner, unit converter | Native (SwiftUI / Compose)        | App Store / Play      |
| **B. Productivity / LOB**  | CRM, ERP, internal tools          | Cross-platform (Flutter / RN / MAUI)  | MDM / TestFlight      |
| **C. Social / community**  | Chat, forum, dating, feed         | Native or RN with realtime backend    | App Store / Play      |
| **D. Game / interactive**  | Puzzle, arcade, AR                | Game engine (Unity / Unreal)          | Both stores           |
| **E. Media / content**     | Player, podcast, e-reader         | Native (AVFoundation / Media3)        | Both stores           |
| **F. Finance / health**    | Banking, fitness, medical         | Native (security + sensors)           | Both stores + review  |
| **G. System / shell**      | Keyboard, launcher, automation    | Native with extensions                | Both stores + sandbox |
| **H. IoT / hardware**      | BLE bridge, camera remote         | Native + Core Bluetooth / GATT        | Both stores           |

If the request fits D (game), **stop and tell the user** -- game engines
have their own pipelines and out of scope here.

For everything else, the classification drives Step 1.5.

---

## Step 1.5 -- Auto-select framework (the key step)

This step **deterministically** picks the framework from the
requirements checklist. Read `references/auto_selection.md` for the
detailed decision tree; the short version:

### Algorithm

```
INPUT: requirements checklist (Step 0) + team profile
OUTPUT: one of { framework, framework pair, pattern }

1. HARD CONSTRAINTS (must satisfy first):
   1.1 If category == D (game) -> STOP, route to game-engine skill.
   1.2 If requirement includes any of:
         iOS Widget / Live Activity / App Intent / CarPlay /
         HealthKit / ARKit / RealityKit / CallKit / Watch face /
         visionOS spatial UI / Metal /
         Android Wear OS tile / Android Auto / foreground service
         with foregroundServiceType /
         hardware-backed keychain or keystore (Secure Enclave / StrongBox)
       -> MUST be native. Two codebases if both platforms.
   1.3 If "single-platform Apple" (iOS-only or watchOS-only):
       -> Swift + SwiftUI. Stop.

2. CROSS-PLATFORM CRITERIA (if cross-platform is acceptable):
   2.1 Both platforms required (iOS + Android) AND
       custom UI / heavy animation / canvas drawing needed
       -> Flutter.
   2.2 Both platforms required AND
       team is web-first OR huge JS library surface (Stripe, Mapbox)
       -> React Native.
   2.3 Both platforms required AND
       team is .NET-first OR existing C# codebase to reuse
       -> .NET MAUI.
   2.4 Both platforms required AND
       native UI mandated by design (no compromise on look & feel)
       -> Kotlin Multiplatform (shared business logic, native UI).
   2.5 Existing web app to wrap as thin native shell
       -> Capacitor or Tauri Mobile.

3. TEAM / EXISTING CODEBASE OVERRIDES:
   3.1 No Swift team available AND selected framework was Swift ->
       swap to Flutter or React Native.
   3.2 No Kotlin team available AND selected framework was Kotlin ->
       swap to Flutter or React Native or .NET MAUI.
   3.3 Existing TypeScript / React codebase ->
       swap to React Native.
   3.4 Existing C# / XAML codebase ->
       swap to .NET MAUI.
   3.5 Existing Dart / Flutter codebase ->
       swap to Flutter.

4. SINGLE-PLATFORM DELIVERY:
   4.1 iOS / iPadOS / watchOS / visionOS only ->
       Swift + SwiftUI (modern) or UIKit (legacy). Default SwiftUI iOS 16+.
   4.2 Android / Wear OS / Android TV only ->
       Kotlin + Compose. Default Compose Material 3.

5. If 1-4 produce no clear winner:
   -> Default: Flutter for category B/C, native per-platform for
      category A/E/F/G/H. Document the choice and rationale in
      `showstoppers` and `notes`.
```

### Output format

```
Selected framework: Swift + SwiftUI
Rationale:
  - Single-platform Apple (iOS 16+) per requirement 3.1.
  - Live Activity required (requirement 0.4) per hard constraint 1.2.
  - Team has Swift experience (team profile 1).
Alternative considered: Kotlin Multiplatform (rejected because
  iOS-only delivery does not justify KMP setup cost).
Confidence: HIGH.
```

If the user wants to override, document why in
`templates/requirements_checklist.md` under "showstoppers" so the next
run of the workflow respects it.

### Confidence levels

| Level      | When                                                      |
|------------|-----------------------------------------------------------|
| **HIGH**   | Hard constraint matched (must-be-native).                 |
| **MEDIUM** | Cross-platform criterion matched + team OK.               |
| **LOW**    | Multiple frameworks tie; pick one and document why.       |

A LOW confidence triggers a follow-up question to the user before
proceeding to Step 2.

Automated helper: `python scripts/select_framework.py requirements.json`
applies the same decision tree and prints a JSON result.

---

## Step 2 -- Decompose into atomic tasks

Use `templates/task_card.md` for each card. The DAG has:

- one node per **deliverable** (a screen, a model, a build artifact).
- one edge per **dependency** (UI needs model, build needs tests).
- an **acceptance criterion** that is *testable on device* for every node.
- a **verification method** (simulator, real device, screenshot, log).

A 4-screen app usually decomposes into 12-20 cards. Keep them small:
no card should exceed ~1 engineer-day of effort. Larger cards get split.

`references/task_decomposition.md` has worked examples for each
category.

Automated helper: `python scripts/plan_project.py --requirements
requirements.json --output-dir plan` writes `requirements.md` and a
task DAG in `tasks.md`.

---
## Step 3 -- Apply platform patterns

The pattern set depends on which framework Step 1.5 picked. Each
framework has its own deep-dive reference (load on demand, do not
load all at once).

### 3.1 Lifecycle and async

| Framework                          | Reference                              | Key primitive                    |
|------------------------------------|----------------------------------------|----------------------------------|
| Swift / SwiftUI                    | `references/lifecycle_patterns.md`     | `Task`, `async let`, `@MainActor`, `@Observable` |
| Kotlin / Compose                   | `references/lifecycle_patterns.md`     | `viewModelScope.launch`, `StateFlow`, `collectAsStateWithLifecycle` |
| Flutter                            | `references/lifecycle_patterns.md`     | `AsyncNotifier`, `Future`, `compute()` |
| React Native                       | `references/lifecycle_patterns.md`     | `useEffect`, `useQuery`, `AppState` |
| .NET MAUI                          | `references/lifecycle_patterns.md`     | `CommunityToolkit.Mvvm`, async/await |
| Kotlin Multiplatform               | `references/lifecycle_patterns.md`     | Per-platform + shared `Flow`     |

### 3.2 Threading / non-blocking UI

Templates in `scripts/`:

- `threading_swiftui.swift` -- `Task` + `@MainActor` bridge.
- `threading_compose.kt` -- coroutine scope + `collectAsState`.
- `threading_flutter.dart` -- `riverpod` AsyncNotifier.
- `threading_react_native.tsx` -- `useQuery` + `Suspense`.

Mobile rule: **all IO, JSON parsing, image decode, and database reads
must be off the main thread / main isolate**. The OS will jank the
app if any one of these runs there.

### 3.3 State management

See `references/state_management.md` for full side-by-side patterns.
The short version:

- **SwiftUI**: `@State` (local), `@Observable` (shared, iOS 17+),
  `@Environment` (global).
- **Compose**: `remember { ... }` (local), `ViewModel` + `StateFlow`
  (screen), `CompositionLocal` (cross-tree).
- **Flutter**: `riverpod` (recommended), `bloc`, `provider`.
- **React Native**: `zustand` (recommended), `redux-toolkit`.

### 3.4 Navigation

- **SwiftUI**: `NavigationStack` (iOS 16+) -- `NavigationView` is
  deprecated. Use `.navigationDestination(for: Route.self)`.
- **Compose**: `androidx.navigation:navigation-compose` with type-safe
  routes (Kotlin 2.0+). `NavHost` + `composable<Route>`.
- **Flutter**: `go_router` (recommended), `auto_route` for codegen.
- **React Native**: React Navigation v7 + Expo Router (if Expo).
- **MAUI**: Shell navigation with `FlyoutItem` / `Tab`.

### 3.5 Framework-specific deep dives

When you need more depth for the framework Step 1.5 picked:

- Swift / SwiftUI / UIKit -> `references/ios_deep_dive.md` (also
  `templates/ios_decision_tree.md` for the iOS-only picker).
- Kotlin / Compose / Gradle -> `references/android_deep_dive.md`.
- Flutter / Dart -> `references/flutter_deep_dive.md`.
- React Native / Expo -> `references/react_native_deep_dive.md`.
- .NET MAUI -> `references/maui_deep_dive.md`.
- Kotlin Multiplatform -> `references/kmp_deep_dive.md`.

### 3.6 Permissions and privacy

- **iOS**: `NSUsageDescription` keys in Info.plist **must** match any
  API call (`NSCameraUsageDescription`, etc.). Use `AVCaptureDevice`
  `authorizationStatus` before requesting. `ATT` prompt only via
  `AppTrackingTransparency` framework.
- **Android**: runtime permissions for dangerous APIs (location,
  camera, mic, contacts, storage). `requestPermission` flow must
  handle denial gracefully; never `finish()` the app on deny.
- **Play Store data safety form** and **App Store privacy nutrition
  labels** must match actual data collection. Mismatches get rejected.

### 3.7 Sandbox and storage

- **iOS**: app sandbox only; Documents / Library / Caches / tmp. Use
  `FileManager` with `URL(fileURLWithPath:isDirectory:)`. Never
  write to `/var` or `/private`. `App Group` for shared data
  between app and extension.
- **Android**: scoped storage (API 30+); `MediaStore` for shared
  media, app-private dir for app-only. `requestLegacyExternalStorage`
  on `targetSdk` 29 only.

### 3.8 Push notifications

- **iOS**: APNs via `UIApplication.shared.registerForRemoteNotifications`
  + entitlements. Token rotation is normal -- refresh server-side.
- **Android**: FCM is the de-facto standard; HMS for Huawei devices
  (AppGallery requires HMS Core).

### 3.9 Signing and certificates

Detailed in `references/signing_certificates.md`. Short version:

- **iOS**: Apple Developer account ($99/yr). Development cert + ad-hoc
  provisioning profile for device. Distribution cert + App Store
  provisioning profile for store. Manage via Xcode automatic signing
  OR Fastlane match + Git for CI. Never commit `.p12` to git.
- **Android**: upload key + key store. Play App Signing requires the
  upload key; Google keeps the app signing key. `keytool -genkey`
  to mint the upload keystore. Never commit `.jks` to git.

---

## Step 4 -- Package

### 4.1 Per-framework build scripts (PowerShell, callable from CI)

- `scripts/build_swift_ios.ps1` -- `xcodebuild archive` + `xcodebuild -exportArchive`; upload commands are printed as next steps.
- `scripts/build_kotlin_android.ps1` -- `gradle assemble*/bundle*` + artifact copy.
- `scripts/build_flutter.ps1` -- `flutter build ipa` + `flutter build appbundle`.
- `scripts/build_react_native.ps1` -- `npx react-native build-ios` + config-aware Gradle bundle for Android.
- `scripts/build_dotnet_maui.ps1` -- `dotnet publish -f net8.0-ios -c Release` + `dotnet publish -f net8.0-android -c Release`.
- `scripts/build_kmp.ps1` -- Xcode for iOS, Gradle for Android (shared KMP module).
- `scripts/build_capacitor.ps1` -- `npx cap sync` + Xcode / Gradle build.
- `scripts/build_tauri_mobile.ps1` -- `npx tauri ios build` / `npx tauri android build`.

Common flags across all build scripts:
- `-SkipTests` -- skips the framework unit test pass.
- `-OutputDir` -- where the produced archive / bundle is copied.

Script-specific flags:

| Script | Key flags |
|---|---|
| `build_swift_ios.ps1` | `-Workspace`, `-Project`, `-Scheme`, `-Configuration`, `-Arch` |
| `build_kotlin_android.ps1` | `-ProjectDir`, `-Flavor`, `-BuildType`, `-OutputFormat`, `-Offline` |
| `build_flutter.ps1` | `-Platform`, `-Flavor`, `-BuildMode`, `-Offline` |
| `build_react_native.ps1` | `-Platform`, `-Configuration`, `-ProjectDir`, `-UseEas`, `-Offline` |
| `build_dotnet_maui.ps1` | `-Platform`, `-Configuration`, `-TargetFramework`, `-ProjectDir` |
| `build_kmp.ps1` | `-Platform`, `-Configuration`, `-SharedModule`, `-IosScheme`, `-AndroidModule` |

### 4.2 Signing

`scripts/setup_ios_signing.ps1` -- interactively creates development +
distribution certs, provisioning profiles via Fastlane match.
`scripts/setup_android_signing.ps1` -- mints upload keystore via
`keytool`, writes `key.properties` consumed by Gradle.

### 4.3 Fastlane

`references/distribution_playbook.md` includes a Fastlane `Fastfile`
skeleton with these lanes:
- `lane :test` -- runs unit + UI tests, fails on any failure.
- `lane :beta` -- TestFlight + Play internal track.
- `lane :release` -- App Store + Play production, screenshots auto-gen.
- `lane :promote` -- promote internal build to production.

### 4.4 Continuous distribution

- **TestFlight**: up to 100 internal testers, 90-day expiry per build,
  groups for QA / stakeholder / beta.
- **Play internal track**: unlimited testers via email allow-list or
  Firebase App Distribution.
- **App Store phased release**: 1% / 2% / 5% / 10% / 20% / 50% / 100%
  over 7 days. Use `phased_release` lane.
- **Play staged rollout**: any % per day, can be paused or rolled back.

---

## Step 5 -- Verify

The universal checklist -- run before handing back:

Automated smoke pass: `pwsh scripts/verify_mobile.ps1 -Framework <framework>
-ProjectDir <project>` writes `verification_report.md`.

- [ ] App launches on a **clean simulator** (iOS Simulator wipe / Android
      emulator factory reset) in <= 1.5 s.
- [ ] App launches on a **real mid-tier device** (iPhone 12 / Pixel 6a)
      in <= 2.0 s.
- [ ] All interactive elements respond within 16 ms (60 Hz) / 8.3 ms
      (120 Hz ProMotion). Use Instruments / Android Studio Profiler to
      verify, do not eyeball.
- [ ] Every permission request shows the system dialog with a friendly
      rationale string before the system prompt.
- [ ] Every screen is readable with Dynamic Type / font scale 200%.
- [ ] Dark mode / light mode / high contrast all look correct.
- [ ] All deep links resolve correctly when the app is fresh-installed.
- [ ] All deep links resolve correctly when the app is backgrounded.
- [ ] Backgrounding then resuming preserves scroll position and form
      state (or explicitly resets if that is the design).
- [ ] Cold start with airplane mode on does not crash.
- [ ] Cold start with denied permission does not crash.
- [ ] All animations run on the render thread, not the main thread.
- [ ] No `print()` / `NSLog()` / `Log.d()` left in release builds.
- [ ] Release build is signed with the correct cert / keystore.
- [ ] Archive / bundle uploads successfully to App Store Connect / Play
      Console (or to internal track at minimum).
- [ ] Crash reporting SDK is wired and a synthetic crash is recorded.
- [ ] Analytics events fire for the documented user actions.

---

## Step 6 -- Hand off

Produce a user-facing README that includes:
- One-paragraph description of what the app does.
- How to install on a device (TestFlight link or APK sideload steps).
- How to build from source (exact commands per framework).
- Where logs and crash reports are stored.
- How to report a bug (Jira / GitHub / Linear template).
- Known limitations and the **showstopper assumption** recorded in
  Step 0 (e.g., "assumes iOS 16+ and Android 13+; earlier versions
  fall back to a degraded screen").
- The Step 1.5 selection + confidence + rationale, so the next dev
  can re-evaluate if requirements change.

---

## Deep references (read on demand)

### Workflow & decision
- `references/auto_selection.md` -- full decision tree (load this
  when running Step 1.5).
- `references/framework_matrix.md` -- pros / cons / IDE setup per
  framework.
- `references/task_decomposition.md` -- worked examples per category.
- `references/restricted_network_playbook.md` -- offline builds,
  vendoring, mirrors.

### Platform-specific deep dives
- `references/ios_deep_dive.md` -- Swift + SwiftUI patterns.
- `references/android_deep_dive.md` -- Kotlin + Compose patterns.
- `references/flutter_deep_dive.md` -- Flutter / Dart patterns.
- `references/react_native_deep_dive.md` -- RN + Expo + TurboModules.
- `references/maui_deep_dive.md` -- .NET MAUI + XAML.
- `references/kmp_deep_dive.md` -- Kotlin Multiplatform + shared logic.
- `references/capacitor_deep_dive.md` -- Capacitor thin shell patterns.
- `references/tauri_mobile_deep_dive.md` -- Tauri Mobile Rust + WebView.

### Cross-cutting
- `references/distribution_playbook.md` -- packaging + signing +
  Fastlane lanes + CI snippets.
- `references/signing_certificates.md` -- iOS cert types + Android
  keystore + Play Integrity.
- `references/lifecycle_patterns.md` -- iOS scene / Android lifecycle
  + Flutter / RN patterns side by side.
- `references/state_management.md` -- SwiftUI / Compose / Flutter /
  RN state patterns side by side.
- `references/security_hardening.md` -- secrets, attestation, data at rest.

## Templates (copy-paste starting points)

- `templates/requirements_checklist.md` -- Step 0 fill-in
  (includes team profile fields for Step 1.5).
- `templates/task_card.md` -- one per atomic task in Step 2.
- `templates/Info.plist.xml` -- minimal iOS plist with required keys.
- `templates/AndroidManifest.xml` -- minimal Android manifest with
  required permissions and queries.
- `templates/build.gradle.kts` -- module-level Kotlin DSL.
- `templates/ios_decision_tree.md` -- second-level tool picker for
  pure iOS (only relevant if Step 1.5 picks Swift).
- `templates/wearable_decision_tree.md` -- watchOS / visionOS / Wear OS picker.
- `templates/verification_report.md` -- Step 5 device checklist.
- `templates/ci/` -- GitHub Actions / GitLab CI / Bitrise skeletons.

## Examples (minimal runnable projects; mirror the `scripts/` threading templates)

### Counter apps (4 framework starters)
- `examples/swiftui-counter/` -- SwiftUI + @Observable + Task.
- `examples/compose-counter/` -- Jetpack Compose + ViewModel + Flow.
- `examples/flutter-counter/` -- Flutter + riverpod Notifier.
- `examples/react-native-counter/` -- RN + zustand.

### Real-looking apps (3 production-shaped starters)
- `examples/compose-news-feed/` -- Compose + Hilt + StateFlow +
  Repository pattern (Android production shape).
- `examples/flutter-news-feed/` -- Riverpod + AsyncNotifier +
  ProviderContainer overrides (Flutter production shape).
- `examples/rn-news-feed/` -- zustand + FlatList + RefreshControl
  + accessibility (RN production shape).
- `examples/capacitor-starter/` -- thin WebView shell.
- `examples/tauri-starter/` -- Rust + WebView mobile starter.
- `examples/watchos-starter/` -- watchOS SwiftUI starter.
- `examples/visionos-starter/` -- visionOS RealityKit starter.
- `examples/wearos-starter/` -- Wear OS Compose starter.

## Tests (fixtures only; no live device calls)

- `tests/README.md` -- how to run the embedded `__main__` smoke tests.
- `tests/fixtures/Info.plist.xml` -- sample plist for plist-parse test.
- `tests/fixtures/build.gradle.kts` -- sample gradle config.
- `tests/fixtures/requirements.json` -- sample requirements doc.
- `tests/fixtures/libs.versions.toml` -- version catalog sample.
- `tests/fixtures/pubspec.yaml` -- Flutter pubspec sample.
- `tests/fixtures/analysis_options.yaml` -- Flutter lint sample.
- `tests/fixtures/package.json` -- RN npm config sample.
- `tests/fixtures/babel.config.js` -- RN babel + Reanimated sample.
