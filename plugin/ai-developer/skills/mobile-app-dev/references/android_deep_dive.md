# Android deep dive (Kotlin + Compose + Hilt + Gradle)

Read this when Step 1.5 has picked Kotlin / Compose (single-platform
Android or the Android side of a cross-platform build) and you need
platform-specific patterns. For the workflow + framework comparison,
see the main SKILL.md.

This file consolidates three sub-topics:

1. Jetpack Compose patterns (state, side effects, theming, performance).
2. Android architecture (Hilt + Room + DataStore + Repository + nav).
3. Gradle Kotlin DSL (version catalog, signing, R8, baseline profiles).

---
# Jetpack Compose deep dive

Read this when you're about to write a screen, a list, or a custom
component. Patterns here are the ones that show up in every real
Compose codebase.

---

## Stateless vs stateful composables

### Stateless (default)

```kotlin
@Composable
fun CounterButton(count: Int, onIncrement: () -> Unit) {
    Button(onClick = onIncrement) {
        Text("Count: $count")
    }
}
```

No `remember`, no `mutableStateOf`. The function is a pure projection
of its inputs. Trivially testable, trivially hoistable.

### Stateful (only when nothing else makes sense)

```kotlin
@Composable
fun RememberableToggle() {
    var checked by remember { mutableStateOf(false) }
    Switch(checked = checked, onCheckedChange = { checked = it })
}
```

Stateful composables are for leaf nodes where the state is purely
local and lifting it up adds ceremony. Toggle, text field, animation
state -- OK. Anything that talks to the network -- never.

## State hoisting

The rule: every stateful composable either owns private state, or
accepts state + callbacks from a parent. Never both.

```kotlin
// Good: hoist state to ViewModel
@Composable
fun FeedScreen(viewModel: FeedViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    FeedContent(state, onRefresh = viewModel::load)
}

// Bad: state lives in a Composable that also does IO
@Composable
fun FeedScreen() {
    var items by remember { mutableStateOf(emptyList<Item>()) }
    LaunchedEffect(Unit) {
        items = api.fetchFeed()  // NO
    }
}
```

## Recomposition triggers

A composable recomposes when:

- A `mutableState` it read changes.
- Its parent recomposes with new parameters.
- An unstable parameter changes (rare; usually structural equality).

Compose tracks reads via the snapshot system. Reading `state.count`
inside `Button { Text("$state.count") }` registers a read; changing
`count` triggers a recomposition of the smallest enclosing scope.

### Stable vs unstable parameters

```kotlin
// Unstable: List<T> is not @Stable; default behavior is structural
// equality check on every recomposition.
@Composable
fun Feed(items: List<Item>) { /* ... */ }

// Stable: ImmutableList<T> from kotlinx.collections.immutable.
@Composable
fun Feed(items: ImmutableList<Item>) { /* ... */ }
```

Use `ImmutableList` / `ImmutableMap` (kotlinx-collections-immutable)
for any large collection passed across composable boundaries. The
compiler then skips equality checks.

## remember vs rememberSaveable

| Use case                    | Choice                       |
|-----------------------------|------------------------------|
| Scroll position, selected tab | `@SceneStorage` equivalent not in Compose; use `rememberSaveable` |
| API state                   | ViewModel (not Compose)      |
| Form input                  | `rememberSaveable`           |
| Animation / transient       | `remember`                   |
| Process death survival      | `rememberSaveable`           |

```kotlin
@Composable
fun SearchScreen() {
    var query by rememberSaveable { mutableStateOf("") }
    OutlinedTextField(value = query, onValueChange = { query = it })
}
```

After process death, `query` is restored from the saved bundle.

## derivedStateOf

When the value is a function of other state, AND the recomposition
should only trigger on changes in the derived value:

```kotlin
@Composable
fun FeedList(items: List<Item>) {
    val sorted by remember(items) {
        derivedStateOf { items.sortedBy { it.title } }
    }
    LazyColumn { items(sorted, key = { it.id }) { ... } }
}
```

Without `derivedStateOf`, the sort runs on every recomposition even
if `items` did not change.

## Side effects

| Side effect                | API                                  |
|----------------------------|--------------------------------------|
| One-shot on first composition | `LaunchedEffect(Unit) { ... }`     |
| On key change              | `LaunchedEffect(key) { ... }`        |
| Cleanup on dispose         | `DisposableEffect(key) { onDispose { ... } }` |
| Coroutine producing state  | `produceState(initial, key) { ... }` |
| Animations                 | `animate*AsState`                   |
| Layout-driven state        | `BoxWithConstraints`                 |

```kotlin
@Composable
fun Timer() {
    var seconds by remember { mutableStateOf(0) }
    LaunchedEffect(Unit) {
        while (true) {
            delay(1000)
            seconds++
        }
    }
    Text("$seconds s")
}
```

Don't forget to cancel: `LaunchedEffect` cancels its coroutine when
the composable leaves composition.

## Theming

### Material 3 dynamic color (Android 12+)

```kotlin
val dynamicColor = supportsDynamicColor()
val colorScheme = when {
    dynamicColor && isSystemInDarkTheme() -> dynamicDarkColorScheme(LocalContext.current)
    dynamicColor -> dynamicLightColorScheme(LocalContext.current)
    isSystemInDarkTheme() -> DarkColors
    else -> LightColors
}
MaterialTheme(colorScheme = colorScheme) { /* ... */ }
```

### Custom design system

```kotlin
@Immutable
data class MyColors(
    val brand: Color,
    val onBrand: Color,
    val surface: Color,
    val onSurface: Color,
)

val LocalMyColors = staticCompositionLocalOf<MyColors> { error("no MyColors") }

@Composable
fun MyAppTheme(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalMyColors provides myColors) {
        MaterialTheme { content() }
    }
}

// In a Composable:
val colors = LocalMyColors.current
Text(color = colors.brand)
```

## Performance

### Skippable composables

A composable is skippable when all parameters are stable. The
compiler emits code that compares old vs new params; if equal,
recomposition is skipped entirely.

Stable = primitive, immutable data class, or marked `@Stable` /
`@Immutable`. `List<T>` is **not** stable.

### LazyColumn with `key`

```kotlin
LazyColumn {
    items(items = feed, key = { it.id }) { item ->
        FeedRow(item)
    }
}
```

The `key` lets Compose track item identity across recompositions.
Without it, scrolling glitches and recomposition is wasted.

### Baseline profiles

```kotlin
// In app/build.gradle.kts:
androidComponents {
    onVariants { variant ->
        // Generate baseline profile via benchmark module
    }
}
```

Baseline profiles tell the AOT compiler which methods to pre-compile.
Result: cold start 30-50% faster on first launch.

### Layout Inspector + Composition Tracing

In Android Studio: View -> Tool Windows -> Layout Inspector.
Shows the composition tree, recomposition counts, and skip counts.

For non-studio tracing, add `-P` to the gradle.properties and run
`androidx.tracing` -- emits a `.perfetto-trace` file.

## Common bugs

- **`derivedStateOf` reading outside lambda**: state reads must
  happen inside the lambda passed to `derivedStateOf`.
- **`LaunchedEffect(Unit)` for one-shot work that should be in
  ViewModel**: ViewModel scope is correct for "load on view ready".
- **Long-lived state in `remember`**: survives recomposition only.
  Process death loses it. Use `rememberSaveable`.
- **Side effect in composable body**: every side effect must be
  inside `LaunchedEffect` / `DisposableEffect` / `produceState`.
- **Passing `MutableState<T>` directly to child**: child reads it
  via `state.value`, parent can replace the reference. Prefer
  passing `T` + setter.

## Testing

### Unit test ViewModel

```kotlin
class FeedViewModelTest {
    @get:Rule val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `load emits Loaded state`() = runTest {
        val vm = FeedViewModel(api = StubApi(items = listOf(item1, item2)))
        vm.load()
        val state = vm.uiState.first { it is FeedUiState.Loaded }
        assertEquals(2, (state as FeedUiState.Loaded).items.size)
    }
}
```

`MainDispatcherRule` sets `Dispatchers.Main` to a `TestDispatcher`.

### Compose UI test

```kotlin
@get:Rule val rule = createComposeRule()

@Test
fun counter_increments() {
    rule.setContent { CounterButton(0) {} }
    rule.onNodeWithText("Count: 0").assertIsDisplayed()
    rule.onNodeWithRole(Role.Button).performClick()
    rule.onNodeWithText("Count: 1").assertIsDisplayed()
}
```

Use `testTag` on Composables you want to query; never query by text
if the screen has localized text.

---

# Android architecture patterns

The canonical architecture for a production-grade Android app:

```
+---------------------------------+
|            UI (Compose)         |
+---------------------------------+
                |
                v
+---------------------------------+
|       ViewModel (Hilt)          |
+---------------------------------+
                |
                v
+---------------------------------+
|        Repository               |
+---------------------------------+
       |                  |
       v                  v
+--------------+   +--------------+
|  Remote API |   | Local DB     |
|  (Retrofit) |   | (Room)       |
+--------------+   +--------------+
```

Each layer depends only on the one below. UI never talks to API or
DB directly. Repository is the single source of truth.

---

## ViewModel + StateFlow

```kotlin
@HiltViewModel
class FeedViewModel @Inject constructor(
    private val feedRepository: FeedRepository,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {

    private val _uiState = MutableStateFlow<FeedUiState>(FeedUiState.Loading)
    val uiState: StateFlow<FeedUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            feedRepository.feed()
                .catch { e ->
                    _uiState.value = FeedUiState.Error(e.message ?: "Unknown")
                }
                .collect { items ->
                    _uiState.value = FeedUiState.Loaded(items)
                }
        }
    }

    fun refresh() {
        viewModelScope.launch {
            _uiState.value = FeedUiState.Loading
            feedRepository.refresh()
        }
    }
}

sealed interface FeedUiState {
    data object Loading : FeedUiState
    data class Loaded(val items: List<Item>) : FeedUiState
    data class Error(val message: String) : FeedUiState
}
```

UI:

```kotlin
@Composable
fun FeedScreen(viewModel: FeedViewModel = hiltViewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    FeedContent(state, onRefresh = viewModel::refresh)
}
```

## Repository pattern

```kotlin
@Singleton
class FeedRepository @Inject constructor(
    private val api: FeedApi,
    private val dao: FeedDao,
    @ApplicationScope private val scope: CoroutineScope,
) {
    fun feed(): Flow<List<Item>> = flow {
        emitAll(dao.all())  // local first
        try {
            val remote = api.fetchFeed()
            dao.upsertAll(remote)
            emitAll(dao.all())  // then fresh
        } catch (e: IOException) {
            // offline; emit nothing more
        }
    }
}
```

Two patterns:

- **Single source of truth = local DB**: API writes to DB; UI
  reads from DB. DB is the only thing that emits. The `flow { }`
  builder above is the wrong pattern for this.
- **Single source of truth = remote**: API is the source; UI reads
  via Flow from a StateFlow. Easier but offline is harder.

The local-DB-as-source pattern is the one Google now recommends
("Offline-first"). It uses Room's `Flow<List<Item>>`:

```kotlin
@Dao
interface FeedDao {
    @Query("SELECT * FROM items ORDER BY ts DESC")
    fun all(): Flow<List<ItemEntity>>

    @Upsert
    suspend fun upsertAll(items: List<ItemEntity>)
}

@Singleton
class FeedRepository @Inject constructor(
    private val api: FeedApi,
    private val dao: FeedDao,
) {
    @ApplicationScope val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    val items: Flow<List<Item>> = dao.all()
        .map { it.map(ItemEntity::toDomain) }

    suspend fun refresh() {
        try {
            val remote = api.fetchFeed()
            dao.upsertAll(remote.map(ItemDto::toEntity))
        } catch (e: IOException) {
            // offline; UI sees stale data
        }
    }

    init {
        scope.launch { refresh() }
    }
}
```

## Hilt setup

### App

```kotlin
@HiltAndroidApp
class MyApp : Application()
```

### Modules

```kotlin
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides @Singleton
    fun retrofit(client: OkHttpClient): Retrofit =
        Retrofit.Builder()
            .baseUrl("https://api.example.com/")
            .client(client)
            .addConverterFactory(Json.asConverterFactory("application/json".toMediaType()))
            .build()

    @Provides @Singleton
    fun feedApi(retrofit: Retrofit): FeedApi =
        retrofit.create(FeedApi::class.java)
}

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides @Singleton
    fun database(@ApplicationContext ctx: Context): AppDatabase =
        Room.databaseBuilder(ctx, AppDatabase::class.java, "app.db")
            .addMigrations(MIGRATION_1_2, MIGRATION_2_3)
            .build()

    @Provides
    fun feedDao(db: AppDatabase): FeedDao = db.feedDao()
}
```

### Scopes

| Scope              | Lifetime                                  |
|--------------------|-------------------------------------------|
| SingletonComponent | App process                               |
| ActivityComponent  | Activity                                  |
| FragmentComponent  | Fragment                                  |
| ViewModelComponent | ViewModel                                 |
| ServiceComponent   | Service                                   |

## Navigation with type-safe routes

```kotlin
@Serializable data object Feed
@Serializable data class Detail(val itemId: String)
@Serializable data class Settings(val section: String? = null)

@Composable
fun AppNavHost(navController: NavHostController = rememberNavController()) {
    NavHost(navController, startDestination = Feed) {
        composable<Feed> {
            FeedScreen(onItemClick = { id ->
                navController.navigate(Detail(itemId = id))
            })
        }
        composable<Detail> { entry ->
            val args = entry.toRoute<Detail>()
            DetailScreen(itemId = args.itemId)
        }
        composable<Settings> { entry ->
            val args = entry.toRoute<Settings>()
            SettingsScreen(section = args.section)
        }
    }
}
```

Requires Kotlin 2.0+ for the type-safe navigation APIs.

## Background work

```kotlin
// Foreground service (Android 14+ requires foregroundServiceType)
class AudioService : Service() {
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(
            NOTIF_ID,
            buildNotification(),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
        )
        return START_STICKY
    }
}

// WorkManager for deferrable work
class RefreshWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        api.refresh()
        return Result.success()
    }
}

val refreshRequest = PeriodicWorkRequestBuilder<RefreshWorker>(15, TimeUnit.MINUTES)
    .setConstraints(Constraints.Builder()
        .setRequiredNetworkType(NetworkType.UNMETERED)
        .build())
    .build()
WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
    "refresh", ExistingPeriodicWorkPolicy.KEEP, refreshRequest
)
```

## Anti-patterns

- **ViewModel calls Activity/Fragment methods directly.** Use a
  SharedFlow or a UI-event sealed class.
- **Repository returns `LiveData`.** Always `Flow` + `StateFlow`.
- **DAO returns `LiveData<List<X>>`.** Same: `Flow<List<X>>`.
- **`lateinit var` on injection.** Use Hilt constructor injection.
- **Singleton in DI scope.** Default to SingletonComponent, narrow
  only when memory profile justifies.
- **Compose state holding `Date` / `Instant`.** Unstable type;
  recomposes constantly. Wrap in a data class with `@Immutable`.
- **Mixing LiveData and Flow in the same screen.** Pick one. Flow.

---

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
