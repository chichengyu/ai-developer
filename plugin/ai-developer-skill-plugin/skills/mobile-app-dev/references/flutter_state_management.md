# Flutter state management

The three options a real codebase will pick between: Riverpod, Bloc,
Provider. Plus sealed unions and AsyncValue as a pattern that works
with any of them.

---

## Riverpod 2.x (recommended)

### Why Riverpod

- Compile-time safety: missing provider is a build error, not a
  runtime crash.
- Testable: every provider is overridable per test.
- No `BuildContext` dependency (unlike Provider).
- Type inference works without `BuildContext` extension methods.

### Provider types

| Provider                | Use for                                        |
|-------------------------|------------------------------------------------|
| `Provider<T>`           | Immutable value (config, services, repo)       |
| `StateProvider<T>`      | Mutable simple value (toggle, slider)          |
| `FutureProvider<T>`     | One-shot async (fetch once)                    |
| `StreamProvider<T>`     | Continuous async (live updates)                |
| `NotifierProvider<N, T>`| Stateful with methods (current value is `T`)   |
| `AsyncNotifierProvider` | Stateful async (current value is `AsyncValue<T>`) |

### Code (with codegen)

```dart
@riverpod
class FeedNotifier extends _$FeedNotifier {
  @override
  Future<List<Item>> build() async {
    return ref.read(apiProvider).fetchFeed();
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => ref.read(apiProvider).fetchFeed());
  }
}

@riverpod
Api api(Ref ref) => LiveApi();

final feedProvider = AsyncNotifierProvider<FeedNotifier, List<Item>>(FeedNotifier.new);
```

### Manual (no codegen)

```dart
final apiProvider = Provider<Api>((ref) => LiveApi());

class FeedNotifier extends AsyncNotifier<List<Item>> {
  @override
  Future<List<Item>> build() async {
    return ref.read(apiProvider).fetchFeed();
  }

  Future<void> refresh() async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(() => ref.read(apiProvider).fetchFeed());
  }
}

final feedProvider = AsyncNotifierProvider<FeedNotifier, List<Item>>(FeedNotifier.new);
```

### AsyncValue patterns

```dart
// In a ConsumerWidget:
final async = ref.watch(feedProvider);
return async.when(
  loading: () => const Center(child: CircularProgressIndicator()),
  error: (e, st) => ErrorView(message: e.toString()),
  data: (items) => ListView.builder(
    itemCount: items.length,
    itemBuilder: (_, i) => ItemTile(items[i]),
  ),
);
```

### Family providers (parameterized)

```dart
@riverpod
Future<Item> item(Ref ref, String id) async {
  return ref.read(apiProvider).fetchItem(id);
}

// Use:
final item = ref.watch(itemProvider('abc'));
```

### Auto-dispose

```dart
@riverpod
Future<List<Item>> feed(Ref ref) async {
  // No listener -> notifier is disposed.
  return ref.read(apiProvider).fetchFeed();
}

// Keep alive:
@Riverpod(keepAlive: true)
```

### Test with override

```dart
testWidgets('shows items', (tester) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        apiProvider.overrideWithValue(StubApi(items: [Item(title: 'X')])),
      ],
      child: const App(),
    ),
  );
  expect(find.text('X'), findsOneWidget);
});
```

## Bloc

### Why Bloc

- Explicit events and states; easier to reason about complex flows.
- Great for state machines.
- Trade-off: more boilerplate.

### Code

```dart
sealed class FeedEvent {}
class FeedLoad extends FeedEvent {}
class FeedRefresh extends FeedEvent {}

sealed class FeedState {}
final class FeedInitial extends FeedState {}
final class FeedLoading extends FeedState {}
final class FeedLoaded extends FeedState { final List<Item> items; FeedLoaded(this.items); }
final class FeedError extends FeedState { final String message; FeedError(this.message); }

class FeedBloc extends Bloc<FeedEvent, FeedState> {
  FeedBloc(this.api) : super(FeedInitial()) {
    on<FeedLoad>(_onLoad);
    on<FeedRefresh>(_onRefresh);
  }
  final Api api;

  Future<void> _onLoad(FeedLoad event, Emitter<FeedState> emit) async {
    emit(FeedLoading());
    try {
      emit(FeedLoaded(await api.fetchFeed()));
    } catch (e) {
      emit(FeedError(e.toString()));
    }
  }

  Future<void> _onRefresh(FeedRefresh event, Emitter<FeedState> emit) async {
    add(FeedLoad());  // reuse handler
  }
}

// In widget:
class FeedView extends BlocBuilder<FeedBloc, FeedState> {
  @override
  Widget build(BuildContext context, FeedState state) {
    return switch (state) {
      FeedInitial() || FeedLoading() => const Center(child: CircularProgressIndicator()),
      FeedLoaded(:final items) => ListView.builder(
          itemCount: items.length,
          itemBuilder: (_, i) => ItemTile(items[i]),
        ),
      FeedError(:final message) => ErrorView(message: message),
    };
  }
}
```

## Provider (legacy)

### When to use

- Migrating from `provider` package.
- Codebase already uses `Consumer` + `Provider.of(context)`.

### Don't mix with Riverpod

Riverpod and Provider are mutually exclusive. Pick one per app.

## Sealed unions (works with any of the above)

```dart
sealed class FeedState {}
final class FeedLoading extends FeedState {}
final class FeedLoaded extends FeedState {
  final List<Item> items;
  FeedLoaded(this.items);
}
final class FeedError extends FeedState {
  final String message;
  FeedError(this.message);
}

// Use:
return switch (state) {
  FeedLoading() => const LoadingIndicator(),
  FeedLoaded(:final items) => ItemList(items),
  FeedError(:final message) => ErrorView(message: message),
};
```

The compiler enforces exhaustiveness. Adding a new state forces
every `switch` to handle it (compile error until you do).

## Anti-patterns

- **`setState` for anything that survives a rebuild.** Use a
  `StateProvider` or `Notifier`.
- **`Provider.of(context, listen: false)` deep in widget tree.**
  Pass via constructor instead.
- **A "global" mega-`ChangeNotifier` for the entire app.** One
  notifier per concern.
- **Mixing `Provider` + `Riverpod` + `Bloc`.** Pick one.
- **`BuildContext` across `await` gaps without checking
  `context.mounted`.** Stale-context bug.
- **Widgets rebuilding because parent rebuilds.** Wrap with
  `const`, `RepaintBoundary`, or extract to a sub-widget that takes
  only what it needs.
- **Side effects in `build()`.** Only `initState` / `didChangeDependencies`
  / `dispose` may perform IO or modify state.