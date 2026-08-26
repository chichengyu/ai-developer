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