# Gradle Kotlin DSL patterns

The complete reference for a production-grade `app/build.gradle.kts`,
version catalog, signing config, ProGuard, and baseline profiles.

---

## Version catalog (libs.versions.toml)

Single source of truth at `gradle/libs.versions.toml`:

```toml
[versions]
agp = "8.5.0"
kotlin = "2.0.21"
compose-bom = "2024.09.03"
hilt = "2.52"
room = "2.6.1"
retrofit = "2.11.0"
coroutines = "1.8.1"

[libraries]
androidx-core-ktx = { module = "androidx.core:core-ktx", version = "1.13.1" }
androidx-activity-compose = { module = "androidx.activity:activity-compose", version = "1.9.2" }
androidx-lifecycle-runtime-compose = { module = "androidx.lifecycle:lifecycle-runtime-compose", version = "2.8.6" }
compose-bom = { module = "androidx.compose:compose-bom", version.ref = "compose-bom" }
compose-ui = { module = "androidx.compose.ui:ui" }
compose-ui-tooling = { module = "androidx.compose.ui:ui-tooling" }
compose-material3 = { module = "androidx.compose.material3:material3" }
hilt-android = { module = "com.google.dagger:hilt-android", version.ref = "hilt" }
hilt-compiler = { module = "com.google.dagger:hilt-compiler", version.ref = "hilt" }
room-runtime = { module = "androidx.room:room-runtime", version.ref = "room" }
room-ktx = { module = "androidx.room:room-ktx", version.ref = "room" }
retrofit = { module = "com.squareup.retrofit2:retrofit", version.ref = "retrofit" }
kotlinx-coroutines-android = { module = "org.jetbrains.kotlinx:kotlinx-coroutines-android", version.ref = "coroutines" }

[bundles]
compose = ["compose-ui", "compose-ui-tooling", "compose-material3"]
lifecycle = ["androidx-lifecycle-runtime-compose"]

[plugins]
android-application = { id = "com.android.application", version.ref = "agp" }
kotlin-android = { id = "org.jetbrains.kotlin.android", version.ref = "kotlin" }
kotlin-compose = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
hilt = { id = "com.google.dagger.hilt.android", version.ref = "hilt" }
ksp = { id = "com.google.devtools.ksp", version = "2.0.21-1.0.27" }
```

## settings.gradle.kts

```kotlin
pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "MyApp"
include(":app")
```

## app/build.gradle.kts (complete)

```kotlin
import java.util.Properties
import java.io.FileInputStream

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

val keystoreProperties = Properties().apply {
    val f = rootProject.file("key.properties")
    if (f.exists()) load(FileInputStream(f))
}

android {
    namespace = "com.example.myapp"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.example.myapp"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
        vectorDrawables.useSupportLibrary = true

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        flavorDimensions += "environment"
        productFlavors {
            create("dev") {
                dimension = "environment"
                applicationIdSuffix = ".dev"
                versionNameSuffix = "-dev"
                buildConfigField("String", "API_BASE_URL", "\"https://dev.api.example.com/\"")
            }
            create("staging") {
                dimension = "environment"
                applicationIdSuffix = ".staging"
                buildConfigField("String", "API_BASE_URL", "\"https://staging.api.example.com/\"")
            }
            create("production") {
                dimension = "environment"
                buildConfigField("String", "API_BASE_URL", "\"https://api.example.com/\"")
            }
        }
    }

    signingConfigs {
        create("release") {
            if (keystoreProperties.isNotEmpty()) {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = if (keystoreProperties.isNotEmpty())
                signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += setOf(
                "/META-INF/{AL2.0,LGPL2.1}",
                "/META-INF/DEPENDENCIES",
                "/META-INF/LICENSE*",
                "/META-INF/NOTICE*"
            )
        }
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = true
        checkReleaseBuilds = true
    }
}

dependencies {
    val composeBom = platform(libs.compose.bom)
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)

    implementation(libs.bundles.compose)
    implementation(libs.bundles.lifecycle)
    debugImplementation(libs.compose.ui.tooling)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp("androidx.room:room-compiler:2.6.1")

    implementation(libs.retrofit)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
    testImplementation("app.cash.turbine:turbine:1.1.0")
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
}
```

## Baseline profile module

```kotlin
// benchmark/build.gradle.kts
plugins {
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    alias(libs.plugins.kotlin.compose) apply false
}

android {
    namespace = "com.example.myapp.benchmark"
    compileSdk = 34
    targetProjectPath = ":app"
    experimentalProperties["android.experimental.r8.dex-startup-optimization"] = true
}

dependencies {
    implementation("androidx.test.uiautomator:uiautomator:2.3.0")
    implementation("androidx.benchmark:benchmark-macro-junit4:1.3.0")
}

androidComponents {
    beforeVariants { variant ->
        // Skip non-release variants for baseline profile gen.
        if (variant.name != "productionRelease") enable = false
    }
}
```

Generate the profile:

```kotlin
@RunWith(AndroidJUnit4::class)
class BaselineProfileGenerator {
    @get:Rule val rule = BaselineProfileRule()

    @Test
    fun startup() = rule.collect(
        packageName = "com.example.myapp.production",
        maxIterations = 5,
        stableIterations = 3,
    ) {
        // Critical user journeys
        pressHome()
        startActivityAndWait()
        // Wait for splash
        device.waitForIdle()
        // Tap into a list item
        device.findObject(By.text("First item")).click()
        device.waitForIdle()
    }
}
```

## R8 / ProGuard rules

`proguard-rules.pro`:

```proguard
# Hilt
-keepattributes Signature
-keep class * extends dagger.hilt.android.HiltAndroidApp
-keepclasseswithmembernames class * { @dagger.hilt.android.* <methods>; }

# kotlinx.serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class **$$serializer { *; }
-keepclasseswithmembers class * { kotlinx.serialization.KSerializer serializer(...); }

# Retrofit
-keepattributes Signature, Exceptions
-keep,allowobfuscation interface retrofit2.http.*

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# Room
-keep class * extends androidx.room.RoomDatabase

# Keep Compose
-keep class androidx.compose.** { *; }
```

## Configuration cache

Enable once in `gradle.properties`:

```
org.gradle.caching=true
org.gradle.configuration-cache=true
org.gradle.parallel=true
org.gradle.jvmargs=-Xmx4g -XX:MaxMetaspaceSize=1g -Dfile.encoding=UTF-8
```

Compatibility caveats:

- Don't use `project.buildDir` at config time (use `layout.buildDirectory`).
- Don't use `Project.getProperties()` outside of `tasks.register {}`.
- Tests must use `TestKit` and declare inputs explicitly.

## Build variants matrix

| Variant       | Use case              | Application ID             |
|---------------|----------------------|----------------------------|
| devDebug      | Local development    | com.example.myapp.dev.debug |
| devRelease    | TestFlight / QA      | com.example.myapp.dev       |
| stagingDebug  | Staging local        | com.example.myapp.staging.debug |
| stagingRelease| Staging internal     | com.example.myapp.staging  |
| productionRelease | Play Store       | com.example.myapp          |

Build:

```bash
./gradlew :app:assembleDevDebug
./gradlew :app:bundleProductionRelease
./gradlew :app:bundleStagingRelease
```

## Common build failures

| Symptom                                   | Cause                              | Fix |
|-------------------------------------------|-------------------------------------|-----|
| `Could not find :app:`                     | settings.gradle.kts missing include | Add `include(":app")` |
| `Manifest merger failed`                   | library adds permission you forbid   | Add `tools:node="remove"` to manifest |
| `Hilt error: @AndroidEntryPoint requires` | missing `@HiltAndroidApp`           | Add annotation to Application class |
| `R8: missing class java.lang.invoke.StringConcatFactory` | Old desugaring                 | Add `coreLibraryDesugaringEnabled = true` + `coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")` |
| `OutOfMemoryError at R8`                   | R8 needs more heap                 | `org.gradle.jvmargs=-Xmx4g` |
