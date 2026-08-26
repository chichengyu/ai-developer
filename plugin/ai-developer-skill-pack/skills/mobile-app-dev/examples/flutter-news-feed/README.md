# flutter-news-feed

A more substantial Flutter example than `examples/flutter-counter/`.
Demonstrates:

- Riverpod `AsyncNotifier` with explicit `refresh` action.
- `ProviderContainer` overrides for test injection.
- Material 3 with `colorSchemeSeed`.
- `RefreshIndicator` for pull-to-refresh.
- `ListView.builder` for efficient list rendering.
- Unit tests with `flutter_test` + `ProviderContainer`.

## How to run

```bash
flutter create .
cp -r examples/flutter-news-feed/lib/* lib/
cp -r examples/flutter-news-feed/test/* test/
flutter pub get
flutter run
flutter test
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

## What to change for production

- Replace `LiveFeedApi` with a `Dio`-backed implementation.
- Add Dio interceptors for auth + logging.
- Add a `Repository` layer between the API and the notifier.
- Persist last successful fetch via `Hive` / `Drift`.
- Add go_router for multi-screen navigation.
- Add `freezed` for `FeedItem` / state unions.
