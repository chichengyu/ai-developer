# Kotlin Multiplatform deep dive

Read this when Step 1.5 has picked Kotlin Multiplatform and you need
platform-specific patterns. For the workflow + framework comparison,
see the main `SKILL.md`.

---

## When KMP is the right pick

- Both iOS + Android delivery is required.
- Native UI is mandated by design (no compromise on look-and-feel).
- Shared business logic (data layer, networking, validation) is the
  bulk of the codebase.
- Team has Kotlin experience.

KMP is **not** "Flutter but in Kotlin". KMP shares the business logic
and lets each platform draw its own UI. For shared UI across both
platforms, look at **Compose Multiplatform** (still maturing) or pick
Flutter.

## Project structure (KMP)

```
MyApp/
  shared/                          Kotlin Multiplatform module
    src/
      commonMain/kotlin/
        data/
          FeedRepository.kt
          FeedItem.kt
        network/
          ApiClient.kt
        domain/
          FeedUseCase.kt
      androidMain/kotlin/
        Android-specific impls
      iosMain/kotlin/
        iOS-specific impls
      commonTest/kotlin/
        Tests for common code
    build.gradle.kts
  androidApp/                      Android app (Kotlin + Compose)
    src/main/kotlin/
      ui/feed/FeedScreen.kt
      ui/feed/FeedViewModel.kt
    build.gradle.kts
  iosApp/                          iOS app (Swift / SwiftUI)
    Sources/
      FeedScreen.swift
      FeedViewModel.swift
    MyApp.xcodeproj
```

The `shared` module produces:
- Android: `.aar` consumed by `androidApp`.
- iOS: `.xcframework` consumed by `iosApp`.

## shared module Gradle DSL

`shared/build.gradle.kts`:

```kotlin
plugins {
    kotlin("multiplatform") version "2.0.21"
    id("com.android.library")
    kotlin("plugin.serialization") version "2.0.21"
}

kotlin {
    androidTarget()
    iosX64()
    iosArm64()
    iosSimulatorArm64()

    sourceSets {
        val commonMain by getting
        val commonTest by getting
        val androidMain by getting
        val iosX64Main by getting
        val iosArm64Main by getting
        val iosSimulatorArm64Main by getting
    }
}

android {
    namespace = "com.example.myapp.shared"
    compileSdk = 34
    defaultConfig {
        minSdk = 26
    }
}

dependencies {
    commonMain {
        implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
        implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.2")
    }
    androidMain {
        implementation("io.ktor:ktor-client-android:2.3.12")
    }
    iosMain {
        implementation("io.ktor:ktor-client-darwin:2.3.12")
    }
}
```

## Shared business logic (commonMain)

```kotlin
package com.example.myapp.shared

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

data class FeedItem(val id: String, val title: String, val summary: String)

interface FeedApi {
    suspend fun fetch(): List<FeedItem>
}

class FeedRepository(private val api: FeedApi) {
    private val _items = MutableStateFlow<List<FeedItem>>(emptyList())
    val items: StateFlow<List<FeedItem>> = _items

    suspend fun refresh() {
        _items.value = api.fetch()
    }
}
```

## Android consumer

```kotlin
package com.example.myapp.androidApp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.myapp.shared.FeedRepository
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class FeedViewModel(private val repo: FeedRepository) : ViewModel() {
    val items: StateFlow<List<FeedItem>> = repo.items
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    init {
        viewModelScope.launch { repo.refresh() }
    }
}
```

## iOS consumer (Swift)

```swift
import shared

@MainActor
@Observable
final class FeedViewModel {
    private let repo: FeedRepository
    private var itemsTask: Task<Void, Never>?

    var items: [FeedItem] = []

    init(repo: FeedRepository = FeedRepository(api: LiveFeedApi())) {
        self.repo = repo
    }

    func start() {
        itemsTask = Task { [weak self] in
            guard let self else { return }
            for await items in self.repo.items {
                self.items = items
            }
        }
    }

    func refresh() async {
        try? await repo.refresh()
    }
}
```

`shared` is consumed as a Swift package; Swift sees it as regular
Swift types (with `FeedItem` mapped to a Swift struct).

## Build the shared framework

```bash
cd shared
./gradlew :shared:assembleXCFramework
```

This produces `shared/build/XCFrameworks/release/shared.xcframework`,
which `iosApp` consumes.

## Compose Multiplatform (shared UI)

If you want shared UI in addition to shared logic:

```kotlin
// commonMain/kotlin
@Composable
fun FeedScreen(items: List<FeedItem>, onRefresh: () -> Unit) {
    Column {
        items.forEach { item -> Text(item.title) }
        Button(onClick = onRefresh) { Text("Refresh") }
    }
}
```

Compose Multiplatform on iOS is **still in alpha as of 2025**; use
with caution. For production iOS UI, prefer native SwiftUI even in
KMP projects.

## When to leave KMP

- One platform only -> native.
- Animation / canvas heavy -> Flutter or native.
- Team is web-first -> React Native.
- No Kotlin experience and no time to learn -> Flutter / RN.

## Resources

- [Kotlin Multiplatform docs](https://kotlinlang.org/docs/multiplatform.html)
- [KMP Compose Multiplatform](https://www.jetbrains.com/lp/compose-multiplatform/)
- [KMP samples](https://github.com/Kotlin/kotlin-multiplatform-templates)