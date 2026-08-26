# iOS-only decision tree

If the user wants ONLY iOS / iPadOS / watchOS / visionOS (no Android),
walk through this tree before reading the cross-platform framework matrix.

## Q1. Swift experience?

- **Yes** -> continue.
- **No, but Objective-C** -> continue (Obj-C still works; UIKit / SwiftUI both callable).
- **No, neither** -> push back to cross-platform (Flutter / RN). iOS-native is not the right pick.

## Q2. Need any of these?

- ARKit / RealityKit
- WidgetKit / Live Activities / App Intents
- HealthKit / CareKit / ResearchKit
- CarPlay / Watch faces
- visionOS spatial UI
- Metal / custom GPU
- Custom share / action / file provider extensions

If **yes** -> **Swift / SwiftUI** is mandatory. Stop and use native.
If **no** -> continue.

## Q3. UIKit required?

- **Existing UIKit codebase** -> keep UIKit, optionally host SwiftUI via `UIHostingController`.
- **Brand-new app, iOS 16+** -> SwiftUI.
- **Need iOS 12-15 support** -> mostly UIKit; SwiftUI missing controls will be a struggle.
- **Vision Pro** -> SwiftUI mandatory (RealityKit / RealityView for 3D).

## Q4. Architecture choice

| Concern              | Choose                                       |
|----------------------|----------------------------------------------|
| Single iPhone app    | SwiftUI + SwiftData + NavigationStack        |
| iPhone + iPad + Mac  | SwiftUI (with `NavigationSplitView` / `WindowGroup`) |
| iPhone + Watch       | SwiftUI on both, `WatchConnectivity` for sync |
| visionOS             | SwiftUI + `RealityView` + `RealityKit`       |
| Existing UIKit code  | Keep UIKit, host SwiftUI screens incrementally |

## Q5. State management

| App scale             | Choose                                       |
|-----------------------|----------------------------------------------|
| One screen            | `@State`                                     |
| Multi-screen, simple  | `@Observable` (iOS 17+) or `ObservableObject` |
| App-wide shared       | `@Environment` + DI via `@Observable`        |
| Offline-first         | Above + SwiftData + repository pattern        |

## Q6. Persistence

| Need                      | Choose                              |
|---------------------------|--------------------------------------|
| Simple key-value          | `@AppStorage`                        |
| Per-scene restoration     | `@SceneStorage`                      |
| Relational                | SwiftData (iOS 17+) or Core Data    |
| Files / large blobs       | `FileManager` + iCloud Drive / CloudKit |

## Q7. Async

| Need                      | Choose                              |
|---------------------------|--------------------------------------|
| One-shot IO               | `Task` + `async let`                |
| Long-running actor state  | `actor`                              |
| Observable stream         | `AsyncStream` + `.task`             |
| Reactive UI binding       | `@Observable` + SwiftUI auto-binds |

## Q8. Networking

| Need                      | Choose                              |
|---------------------------|--------------------------------------|
| REST                      | `URLSession` + `Codable` + async    |
| GraphQL                   | `apollo-ios`                        |
| gRPC                      | `grpc-swift`                        |
| WebSocket                 | `URLSessionWebSocketTask`            |
| Server-Sent Events        | Custom `URLSession` async stream     |
| File upload with progress | `URLSession.upload(for:fromFile:)`  |

## Q9. Auth

| Need                      | Choose                              |
|---------------------------|--------------------------------------|
| Sign in with Apple         | `AuthenticationServices`             |
| OAuth (Google, etc.)      | `AppAuth`                            |
| Custom JWT                | Store in Keychain via `Security`     |
| Biometric                  | `LocalAuthentication`               |

## Q10. Distribution

| Need                      | Choose                              |
|---------------------------|--------------------------------------|
| Public release            | App Store + TestFlight              |
| Internal QA               | TestFlight (90-day expiry)          |
| Enterprise                | Apple Business Manager + MDM profile|
| Custom B2B                | Custom B2B App Store                |
| Sideload                  | Ad-hoc provisioning profile         |

## Q11. Build

| Need                      | Use                                  |
|---------------------------|---------------------------------------|
| Single-platform build    | `scripts/build_swift_ios.ps1`         |
| macOS host required?      | YES (Xcode is macOS-only)             |
| CI macOS runner?          | `macos-14` on GitHub Actions          |
| Code signing?             | `scripts/setup_ios_signing.ps1`       |
| Automated TestFlight?     | Fastlane `pilot upload`               |