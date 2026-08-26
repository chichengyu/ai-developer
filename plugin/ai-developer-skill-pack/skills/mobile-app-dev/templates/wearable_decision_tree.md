# Wearable and immersive decision tree

Use this when the target includes watchOS, visionOS, or Wear OS.

## Q1. Which platforms?

- watchOS only -> Swift + SwiftUI, WatchKit complications.
- visionOS only -> Swift + SwiftUI + RealityKit / RealityView.
- Wear OS only -> Kotlin + Compose for Wear, tiles, complications.
- Watch + iPhone -> one Xcode project; WatchConnectivity for sync.
- Wear + Android phone -> one Android project; separate Wear app
  module.

## Q2. What runs on the wearable?

- Notifications / glanceable info -> complications or tiles.
- Quick actions -> app UI with minimal screens.
- Continuous sensor capture -> native HealthKit / Sensor APIs.
- Real-time 3D / spatial -> visionOS RealityKit, not a web wrapper.

## Q3. What stays on the phone?

- Full data sync, onboarding, account settings, heavy media.
- The wearable should be a thin client that reads from a shared
  store, not a second server.

## Q4. Hard constraints

- HealthKit, Workout, Watch face, visionOS spatial UI, Wear OS tile,
  and Android Auto force native implementations.

## Build and verify

- watchOS / visionOS: `scripts/build_swift_ios.ps1` with the watch or
  vision scheme.
- Wear OS: `scripts/build_kotlin_android.ps1` with the wear module.
- Verify on a real wearable; simulators miss battery, sensors, and
  glance UI behavior.
