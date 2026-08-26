# compose-news-feed

A more substantial Android example than `examples/compose-counter/`.
Demonstrates:

- `@HiltAndroidApp` + `@HiltViewModel` injection.
- `StateFlow` + `collectAsStateWithLifecycle`.
- Sealed `FeedUiState` for exhaustive when-branches.
- LazyColumn with stable `key`.
- Preview function for Compose UI.
- Unit test with JUnit (no Robolectric needed for VM tests).

## How to run

1. Android Studio -> New Project -> Empty Activity.
2. Replace `MainActivity.kt` + add `FeedScreen.kt` + `FeedViewModel.kt`.
3. Add the dependencies from `references/gradle_kts_patterns.md`.
4. Run on API 26+ emulator.

## What to change for production

- Replace `StubFeedRepository` with a real Retrofit + Room implementation.
- Add error retry button to `ErrorView`.
- Add `strings.xml` localization.
- Add `proguard-rules.pro` for your libs.
- Add `baselineprofile` generation module for cold-start gains.
