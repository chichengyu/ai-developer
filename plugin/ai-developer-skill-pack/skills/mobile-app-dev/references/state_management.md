# State management

Side-by-side patterns for each framework. Pick one per layer; do not mix
Redux + Riverpod + @State for the same store.

---

## SwiftUI

### Local state

```swift
struct CounterView: View {
    @State private var count = 0

    var body: some View {
        VStack {
            Text("\(count)")
            Button("Increment") { count += 1 }
        }
    }
}
```

### Shared screen state (iOS 17+ Observation)

```swift
@Observable
class FeedModel {
    var items: [Item] = []
    var isLoading = false

    func load() async {
        isLoading = true
        defer { isLoading = false }
        items = await api.fetchFeed()
    }
}

struct FeedView: View {
    @State private var model = FeedModel()

    var body: some View {
        List(model.items) { item in /* ... */ }
            .task { await model.load() }
    }
}
```

### Pre-iOS 17 ObservableObject pattern

```swift
final class FeedModel: ObservableObject {
    @Published var items: [Item] = []
    @Published var isLoading = false

    func load() async { /* ... */ }
}

struct FeedView: View {
    @StateObject private var model = FeedModel()

    var body: some View {
        List(model.items) { /* ... */ }
            .task { await model.load() }
    }
}
```

### Cross-tree state via Environment

```swift
@main
struct MyApp: App {
    @State private var session = Session()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(session)
        }
    }
}

struct DeepView: View {
    @Environment(Session.self) private var session
    // ...
}
```

### Persistence

- `@AppStorage("key")` for simple user defaults (String, Int, Bool, Double, URL, Data).
- `@SceneStorage("key")` for per-scene restoration (Int, String, Bool, Double, URL, Data).
- `SwiftData` for structured local DB (replaces Core Data in most cases).

```swift
@Model
final class Item {
    var title: String
    var createdAt: Date
    init(title: String) {
        self.title = title
        self.createdAt = Date()
    }
}
```

---

## Compose

### Local state

```kotlin
@Composable
fun Counter() {
    var count by remember { mutableStateOf(0) }
    Column {
        Text("$count")
        Button(onClick = { count++ }) { Text("Increment") }
    }
}
```

### Screen state with ViewModel + StateFlow

```kotlin
class FeedViewModel(
    private val repo: FeedRepository
) : ViewModel() {
    private val _uiState = MutableStateFlow(FeedUiState.Loading)
    val uiState: StateFlow<FeedUiState> = _uiState.asStateFlow()

    fun load() {
        viewModelScope.launch {
            _uiState.value = FeedUiState.Loading
            _uiState.value = runCatching { repo.fetchFeed() }
                .fold(
                    onSuccess = FeedUiState::Loaded,
                    onFailure = { FeedUiState.Error(it) }
                )
        }
    }
}

@Composable
fun FeedScreen(viewModel: FeedViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    FeedContent(state, onRefresh = viewModel::load)
}
```

### Shared state via Hilt

```kotlin
@HiltAndroidApp
class MyApp : Application()

@HiltViewModel
class FeedViewModel @Inject constructor(
    private val repo: FeedRepository
) : ViewModel()

@Composable
fun FeedScreen(viewModel: FeedViewModel = hiltViewModel()) { /* ... */ }
```

### Cross-tree state via CompositionLocal

```kotlin
val LocalSession = compositionLocalOf<Session> { error("no Session") }

@Composable
fun App(session: Session) {
    CompositionLocalProvider(LocalSession provides session) {
        RootContent()
    }
}

@Composable
fun DeepView() {
    val session = LocalSession.current
    // ...
}
```

### Persistence

- `DataStore` for typed prefs (replaces SharedPreferences).
- `Room` for relational DB.
- `Proto DataStore` for protobuf-serialised state.

```kotlin
val Context.userStore by dataStore("user.json", serializer = UserSerializer)
```

---

## Flutter

### Local state (`setState`)

```dart
class Counter extends StatefulWidget {
    @override
    State<Counter> createState() => _CounterState();
}

class _CounterState extends State<Counter> {
    int _count = 0;
    @override
    Widget build(BuildContext context) {
        return Column(children: [
            Text('$_count'),
            ElevatedButton(
                onPressed: () => setState(() => _count++),
                child: const Text('Increment'),
            )
        ]);
    }
}
```

### Riverpod (recommended)

```dart
final feedProvider = AsyncNotifierProvider<FeedNotifier, List<Item>>(
    FeedNotifier.new,
);

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

// In widget:
class FeedView extends ConsumerWidget {
    @override
    Widget build(BuildContext context, WidgetRef ref) {
        final asyncFeed = ref.watch(feedProvider);
        return asyncFeed.when(
            loading: () => const CircularProgressIndicator(),
            error: (e, st) => Text('Error: $e'),
            data: (items) => ListView(children: [for (final i in items) Text(i.title)]),
        );
    }
}
```

### Bloc (alternative for large apps)

```dart
class FeedBloc extends Bloc<FeedEvent, FeedState> {
    FeedBloc(this.api) : super(const FeedInitial()) {
        on<FeedLoad>(_onLoad);
    }
    final Api api;
    Future<void> _onLoad(FeedLoad event, Emitter<FeedState> emit) async {
        emit(const FeedLoading());
        try {
            emit(FeedLoaded(await api.fetchFeed()));
        } catch (e) {
            emit(FeedError(e));
        }
    }
}
```

### Persistence

- `shared_preferences` for simple.
- `hive` for fast typed boxes.
- `drift` for relational.
- `isar` for object DB.

---

## React Native

### Local state (`useState`)

```tsx
function Counter() {
    const [count, setCount] = useState(0);
    return (
        <>
            <Text>{count}</Text>
            <Button title="Increment" onPress={() => setCount(c => c + 1)} />
        </>
    );
}
```

### zustand (recommended)

```tsx
import { create } from 'zustand';
import { useShallow } from 'zustand/react/shallow';

type FeedStore = {
    items: Item[];
    isLoading: boolean;
    load: () => Promise<void>;
};

const useFeedStore = create<FeedStore>((set) => ({
    items: [],
    isLoading: false,
    load: async () => {
        set({ isLoading: true });
        const items = await api.fetchFeed();
        set({ items, isLoading: false });
    },
}));

function FeedView() {
    const { items, isLoading, load } = useFeedStore(
        useShallow(s => ({ items: s.items, isLoading: s.isLoading, load: s.load }))
    );
    useEffect(() => { load(); }, [load]);
    // render items
}
```

### Redux Toolkit (alternative for large apps)

```tsx
const feedSlice = createSlice({
    name: 'feed',
    initialState: { items: [], isLoading: false } as FeedState,
    reducers: {
        loadStart: (s) => { s.isLoading = true; },
        loadSuccess: (s, a: PayloadAction<Item[]>) => {
            s.items = a.payload;
            s.isLoading = false;
        },
    },
});

function FeedView() {
    const { items, isLoading } = useSelector((s: RootState) => s.feed);
    const dispatch = useDispatch();
    useEffect(() => {
        dispatch(loadStart());
        api.fetchFeed().then(items => dispatch(loadSuccess(items)));
    }, [dispatch]);
}
```

### Persistence

- `AsyncStorage` for simple.
- `react-native-mmkv` for fast synchronous storage.
- `WatermelonDB` for relational.
- `Realm` for object DB.

---

## Choosing between patterns

| Scale                              | Recommended                              |
|------------------------------------|------------------------------------------|
| Single screen, local only          | `useState` / `@State` / `remember`       |
| Screen with async data             | zustand / Riverpod / `ViewModel` / `@Observable` |
| Multi-screen, same domain          | Above + a route param / `Environment`    |
| App-wide (auth, theme, locale)      | Above + provider / DI / `CompositionLocal` |
| Offline-first, large dataset       | Above + repository pattern + local DB    |
| Real-time collaboration            | Above + CRDT (Yjs, Automerge)            |
| Time-travel debugging              | Redux + Redux DevTools / Riverpod        |

## Common anti-patterns

- **Multiple sources of truth.** The same item ID stored both in
  React state and in zustand -- choose one.
- **Storing derived data.** Compute `fullName` from `firstName` and
  `lastName`; do not store it.
- **Mixing local + remote state in one store.** Keep `isLoading`,
  `error`, `data` in a state-machine pattern (AsyncValue in Riverpod,
  AsyncState in zustand, sealed class in Kotlin, Result in Swift).
- **Triggering network on every render.** Use `useEffect` /
  `.task` / `LaunchedEffect` with stable deps, or a query library
  (`@tanstack/react-query`, `riverpod`, `LiveData`).