# compose-counter

Minimal Jetpack Compose counter demonstrating the `threading_compose.kt` pattern.

## How to run

1. Android Studio -> File -> New -> New Project -> Empty Compose Activity.
2. Replace `MainActivity.kt` with `MainActivity.kt` from this folder.
3. Pick an API 26+ emulator and Run.

## Required dependencies

In `app/build.gradle.kts`:

```kotlin
dependencies {
    implementation("androidx.compose.material3:material3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose")
    implementation("androidx.lifecycle:lifecycle-runtime-compose")
    implementation("androidx.activity:activity-compose")
}
```

## What it shows

- `ViewModel` + `StateFlow` for state.
- `collectAsStateWithLifecycle()` (not plain `collectAsState`) so collection
  pauses when the activity is stopped.
- `viewModelScope.launch` for async work.
- `rememberSaveable` for state restoration (used implicitly via ViewModel).