# flutter-counter

Minimal Flutter counter demonstrating the `threading_flutter.dart` pattern
with `riverpod` for state.

## How to run

```bash
flutter pub get
flutter run
```

## Required dependencies (in pubspec.yaml)

```yaml
dependencies:
  flutter:
    sdk: flutter
  flutter_riverpod: ^2.5.1
dev_dependencies:
  flutter_test:
    sdk: flutter
```

## What it shows

- `ProviderScope` at the app root.
- `NotifierProvider` for state (instead of `StateNotifier`).
- `ConsumerWidget` to read state.
- `FilledButton` + `OutlinedButton` (Material 3).
- Loading button pattern via `state.isLoading`.

## Where to go from here

- Swap `loadFromNetwork` for a real `dio.get(...)` call.
- Add `go_router` for multi-screen navigation.
- Add `flutter_hooks` for `useState` / `useEffect` style.