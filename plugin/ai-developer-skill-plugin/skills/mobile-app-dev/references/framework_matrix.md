# Framework matrix (deep dive)

Detailed pros, cons, project templates, and IDE setup for every framework in
the main SKILL.md matrix. Read this when the user has narrowed the choice to
two or three candidates and needs to commit.

---

## Swift + SwiftUI (iOS 16+ / iPadOS / watchOS / visionOS)

- **Best for**: pure-Apple deliverables, App Store-first apps, anything that
  uses Live Activities, WidgetKit, App Intents, HealthKit, ARKit, CarPlay,
  or visionOS volumes.
- **Pros**: best performance, full API access, smallest binary, day-one
  OS features, SwiftUI declarative UI keeps screens short.
- **Cons**: iOS-only; Apple Developer Program required ($99/yr); Xcode
  is the only IDE; macOS host required for device builds.
- **Cold start**: ~0.3 s on iPhone 12.
- **Binary size**: ~5-15 MB per architecture.
- **Project template**: Xcode -> "App" -> SwiftUI lifecycle, iOS 16+.
- **Recommended libs**: SwiftData (persistence, replaces Core Data in many
  cases), Swift Concurrency (built-in), Swift Charts, TipKit,
  Observation framework (`@Observable` macro).
- **Packaging**: `xcodebuild archive` -> `xcodebuild -exportArchive` ->
  `xcrun altool --upload-app` OR `fastlane pilot upload`.

## Swift + UIKit

- **Best for**: legacy apps, custom UI not expressible in SwiftUI, apps
  supporting iOS 12-15, performance-critical drawing (CADisplayLink).
- **Pros**: every iOS feature is reachable; mature; custom transitions
  easy.
- **Cons**: more boilerplate; no @State / @Observable; manual lifecycle.
- **Project template**: Xcode -> "App" -> UIKit App Delegate.
- **Use SwiftUI in UIKit and vice versa** via `UIHostingController` /
  `UIViewControllerRepresentable`. This is the modern migration path.

## Kotlin + Jetpack Compose (Android 8+ / Wear OS / Android TV)

- **Best for**: pure-Android deliverables, Play Store-first apps, anything
  that uses Compose Material 3, Wear OS tiles, Android Auto, Foldables.
- **Pros**: best performance, full API access, smallest APK, day-one OS
  features, Kotlin is concise.
- **Cons**: Android-only; Gradle build can be slow; Android Studio is
  the primary IDE.
- **Cold start**: ~0.5 s on Pixel 6a.
- **Binary size**: ~5-20 MB.
- **Project template**: Android Studio -> "Empty Compose Activity".
- **Recommended libs**: Compose BOM, Hilt (DI), Room (DB), Retrofit (HTTP),
  Coil (image), DataStore (prefs).
- **Packaging**: `gradle :app:assembleRelease` -> `.aab` via
  `bundleRelease` -> `bundletool build-apks` for sideload OR
  Play Console upload.

## Kotlin + Views (XML)

- **Best for**: legacy Android apps, custom views, accessibility-first
  apps where TalkBack ordering is more controllable than Compose.
- **Pros**: every Android feature is reachable; ViewModel + LiveData /
  StateFlow are still canonical.
- **Cons**: XML layouts are verbose; no `Modifier` semantics; harder to
  share with iOS.

## Flutter (Dart 3, all platforms)

- **Best for**: cross-platform apps with custom UI / animation / canvas
  work, fast iteration via hot reload, single codebase for iOS + Android.
- **Pros**: Skia-rendered UI looks identical on both platforms; near-
  native performance for most apps; huge package ecosystem.
- **Cons**: extra runtime (~5-15 MB); occasional native bridge pain;
  Material 3 is great, Cupertino is OK; native bridge code (Swift / Kotlin)
  must be written for deep system features.
- **Cold start**: ~0.6 s on iPhone 12, ~0.7 s on Pixel 6a.
- **Binary size**: ~20-40 MB per platform.
- **Project template**: `flutter create --platforms=ios,android my_app`.
- **Recommended libs**: `riverpod`, `go_router`, `dio`, `drift` (DB),
  `freezed` (codegen), `flutter_hooks`.
- **Packaging**: `flutter build ipa` and `flutter build appbundle`.

## React Native (TypeScript, all platforms)

- **Best for**: cross-platform apps where the team is web-first, or the
  app needs a huge JS library (Stripe, Mapbox, Auth0).
- **Pros**: biggest JS ecosystem; React Native New Architecture (Fabric +
  TurboModules + JSI) closes the perf gap with native.
- **Cons**: JS engine overhead; native bridge debugging is harder; hot
  reload sometimes lies.
- **Cold start**: ~0.7-1.0 s on iPhone 12, ~0.8-1.2 s on Pixel 6a.
- **Binary size**: ~25-50 MB per platform (Hermes shrinks it ~30%).
- **Project template**: `npx @react-native-community/cli init my_app`
  OR Expo (`npx create-expo-app`).
- **Recommended libs**: `zustand` or `redux-toolkit`, React Navigation v7,
  `react-native-mmkv` (storage), `react-native-reanimated` (animations),
  `react-native-maps`, Stripe RN SDK.
- **Packaging**: `npx react-native build-ios` (or `eas build` for Expo)
  + Gradle for Android.

## .NET MAUI (C#)

- **Best for**: cross-platform apps where the team is .NET-first and the
  app is mainly LOB / productivity.
- **Pros**: single C# codebase, XAML reuse across platforms, MVU /
  MVVM patterns, Visual Studio tooling.
- **Cons**: smaller mobile ecosystem than Flutter/RN; some native API
  gaps; WinUI 3 desktop is more mature.
- **Cold start**: ~0.8-1.2 s on iPhone 12.
- **Binary size**: ~30-60 MB per platform (Mono runtime included).
- **Project template**: `dotnet new maui -n MyApp`.
- **Packaging**: `dotnet publish -f net8.0-ios -c Release` +
  `-f net8.0-android`.

## Kotlin Multiplatform (Kotlin)

- **Best for**: sharing business logic / data layer across iOS + Android
  while keeping native UI on each.
- **Pros**: shared code without UI lock-in; access to Compose
  Multiplatform for shared UI when wanted.
- **Cons**: still evolving; smaller community than Flutter/RN; some
  iOS-only APIs need careful abstraction.
- **Project template**: Android Studio -> "Kotlin Multiplatform App".
- **Packaging**: Xcode for iOS (CocoaPods + `.xcframework`), Gradle for
  Android (`assembleRelease`).

## Capacitor (JS / TS)

- **Best for**: when a PWA already exists and a thin native shell is
  enough; OR when the team is web-only.
- **Pros**: reuses existing web app; smallest "mobile" effort.
- **Cons**: WebView rendering -> no platform-native look without effort;
  no 120 Hz ProMotion polish; app store reviewers will notice.
- **Project template**: `npm init @capacitor/app`.
- **Packaging**: `npx cap sync` + Xcode / Gradle as usual.

## Tauri Mobile (Rust + WebView)

- **Best for**: Rust-first teams that want a small binary; web UI as
  a thin layer.
- **Pros**: tiny binaries (~5 MB), Rust backend, system WebView.
- **Cons**: still maturing; less mature than Capacitor for production
  apps.

## When to NOT use cross-platform

If the app must do any of the following, default to native:

- Widgets, Live Activities, App Intents (iOS)
- Glanceable tiles (Wear OS)
- Custom share extensions, action extensions, file providers
- ARKit (Apple) / ARCore (Google) deep features
- HealthKit / Google Fit with sensor fusion
- CarPlay / Android Auto
- Camera with manual ISO / shutter / RAW
- visionOS spatial UI
- Background audio with AirPlay 2 / car Bluetooth routing

For these, the "one codebase" win is offset by months of platform-
specific code anyway. Use native.

## Per-platform CI considerations

- **iOS**: requires a macOS runner (`macos-14` for Xcode 15+). Use
  GitHub Actions / Bitrise / CircleCI macOS.
- **Android**: any Linux runner with JDK 17 + Android SDK.
- **Flutter / RN / MAUI / KMP**: any Linux runner; iOS still needs macOS
  for the final archive + signing.

This is the main reason to not blindly choose Flutter on a Windows-only
team: the iOS archive step still requires a Mac, and the Fastlane lane
needs App Store Connect API key auth.