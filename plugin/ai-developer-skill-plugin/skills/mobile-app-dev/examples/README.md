# examples/

Four minimal runnable projects that demonstrate the skill's threading
templates in real (non-toy) contexts. Each one mirrors the canonical
templates in `../scripts/`; keep the snippets in sync when a template
changes.

| Folder                   | Framework                          | Demonstrates                           |
|--------------------------|------------------------------------|-----------------------------------------|
| `swiftui-counter/`       | Swift + SwiftUI (iOS 17+)          | `threading_swiftui.swift` + Task       |
| `compose-counter/`       | Kotlin + Compose (Android 8+)      | `threading_compose.kt` + StateFlow      |
| `flutter-counter/`       | Flutter + Riverpod                 | `threading_flutter.dart` + Notifier     |
| `react-native-counter/`  | React Native + zustand             | `threading_react_native.tsx` + zustand  |

## Why minimal?

These are not production apps. They are the smallest examples that
demonstrate the threading bridge correctly -- which is the easiest
pattern to get wrong on mobile.

## How to run

### swiftui-counter

```bash
# Open Xcode 15+ -> New Project -> App -> SwiftUI
# Replace ContentView.swift + MyApp.swift with CounterApp.swift
# Cmd-R on iPhone 15 simulator
```

### compose-counter

```bash
# Android Studio -> File -> New -> New Project -> Empty Compose Activity
# Replace MainActivity.kt with MainActivity.kt from this folder
# Run on API 26+ emulator
```

### flutter-counter

```bash
flutter create .
cp -r examples/flutter-counter/lib/* lib/
flutter pub get
flutter run
flutter test
```

### react-native-counter

```bash
# Bare RN
npx @react-native-community/cli init Counter --skip-install
cp examples/react-native-counter/App.tsx Counter/
cp examples/react-native-counter/App.test.tsx Counter/
cd Counter && npm install zustand && npm test

# Expo
npx create-expo-app Counter
cp examples/react-native-counter/App.tsx Counter/
cd Counter && npx expo install zustand && npm test
```

## Where to go from here

- Add a real network call to one of the "Load from network" buttons.
- Add a list screen using the threading pattern.
- Add a settings screen persisted with `@AppStorage` / `DataStore` /
  `shared_preferences` / `AsyncStorage`.
- Wire up deep linking.
## Real-looking apps (production shape)

| Folder                   | Framework         | Demonstrates                                            |
|--------------------------|-------------------|---------------------------------------------------------|
| `compose-news-feed/`     | Kotlin + Compose  | Hilt + StateFlow + Repository + LazyColumn w/ keys.     |
| `flutter-news-feed/`     | Flutter + Riverpod| AsyncNotifier + ProviderContainer overrides + Material 3. |
| `rn-news-feed/`          | React Native      | zustand + FlatList + RefreshControl + accessibility.    |
