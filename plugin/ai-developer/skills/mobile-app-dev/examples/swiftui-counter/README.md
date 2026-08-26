# swiftui-counter

Minimal SwiftUI counter demonstrating the `threading_swiftui.swift` pattern.

## How to run

1. Open Xcode 15+ -> File -> New -> Project -> App -> SwiftUI lifecycle.
2. Replace `ContentView.swift` + `MyApp.swift` with `CounterApp.swift`.
3. Cmd-R on an iPhone 15 simulator.

## What it shows

- `@MainActor @Observable` model (iOS 17+).
- `Task` + `.task` modifier for async work.
- `Button + ProgressView` state binding.
- `NavigationStack` + `.navigationTitle` for the title bar.
- Dynamic Type friendly (`accessibilityLabel`).