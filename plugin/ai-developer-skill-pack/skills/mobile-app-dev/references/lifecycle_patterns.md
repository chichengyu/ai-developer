# Lifecycle patterns

iOS and Android each have their own way of telling your app "you are now
backgrounded", "the user came back", "the system needs your resources",
etc. This reference shows the canonical patterns for each framework.

Read this before writing any screen that mutates state, fetches data,
or renders anything that depends on the user's session.

---

## iOS / SwiftUI

### Scene phases (SwiftUI lifecycle)

```swift
@main
struct MyApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @State private var model = AppModel.shared

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
        }
        .onChange(of: scenePhase) { _, newPhase in
            switch newPhase {
            case .active:
                model.resume()        // resume timers, sockets, location
            case .inactive:
                model.pause()         // pause animations, video
            case .background:
                model.snapshot()      // save state, drain queues
            @unknown default:
                break
            }
        }
    }
}
```

### State restoration

```swift
@main
struct MyApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
        // Per-scene restoration:
        // - @SceneStorage("selectedTab") in views
        // - NSUserActivity for handoff / Spotlight
    }
}
```

In views:

```swift
struct FeedView: View {
    @SceneStorage("feed.scrollOffset") private var scrollOffset: Double = 0
    @AppStorage("settings.darkMode")    private var darkMode: Bool = false

    var body: some View {
        ScrollView { /* ... */ }
        .background(scrollableOffsetReader($scrollOffset))
    }
}
```

### Deep links (Universal Links)

```swift
// In Info.plist:
<key>Associated Domains</key>
<array>
    <string>applinks:myapp.example.com</string>
</array>

// In SwiftUI:
struct RootView: View {
    @State private var path = NavigationPath()
    var body: some View {
        NavigationStack(path: $path) {
            HomeView()
                .navigationDestination(for: Route.self) { route in
                    switch route {
                    case .detail(let id): DetailView(id: id)
                    }
                }
        }
        .onOpenURL { url in
            guard let route = Route(url: url) else { return }
            path.append(route)
        }
    }
}
```

### Background tasks

```swift
// BGTaskScheduler for periodic refresh (info.plist: BGTaskSchedulerPermittedIdentifiers)
func registerBackgroundTask() {
    BGTaskScheduler.shared.register(
        forTaskWithIdentifier: "com.example.myapp.refresh",
        using: nil
    ) { task in
        handleRefresh(task: task as! BGAppRefreshTask)
    }
    scheduleNextRefresh()
}

func scheduleNextRefresh() {
    let request = BGAppRefreshTaskRequest(identifier: "com.example.myapp.refresh")
    request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60)
    try? BGTaskScheduler.shared.submit(request)
}
```

### Push registration

```swift
func application(_ app: UIApplication,
                 didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
    let tokenString = token.map { String(format: "%02x", $0) }.joined()
    api.registerDevice(token: tokenString)
}

func application(_ app: UIApplication,
                 didFailToRegisterForRemoteNotificationsWithError error: Error) {
    logger.error("APNs registration failed: \(error)")
}
```

(SwiftUI app lifecycle: use `UIApplicationDelegateAdaptor`.)

### URL scheme handling

```swift
.onOpenURL { url in
    // myapp://settings/account
    handleDeepLink(url)
}
```

---

## Android / Compose

### Process lifecycle

```kotlin
class MyApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        ProcessLifecycleOwner.get().lifecycle.addObserver(AppLifecycleObserver())
    }
}

class AppLifecycleObserver : DefaultLifecycleObserver {
    override fun onStart(owner: LifecycleOwner) { /* app in foreground */ }
    override fun onStop(owner: LifecycleOwner)  { /* app in background */ }
}
```

### Compose state hoisting

```kotlin
@Composable
fun FeedScreen(viewModel: FeedViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    FeedContent(state)
}

class FeedViewModel : ViewModel() {
    val uiState: StateFlow<FeedUiState> = repo.feedStream
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), FeedUiState.Loading)
}
```

### State restoration with SavedStateHandle

```kotlin
class DetailViewModel(savedStateHandle: SavedStateHandle) : ViewModel() {
    private val itemId: String = savedStateHandle["itemId"]!!
    val item: StateFlow<Item> = repo.observe(itemId)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), Item.Loading)
}
```

### Process death survival

- `SavedStateHandle` is the canonical mechanism.
- For long-form state, persist via `DataStore` on `onStop` and
  restore on `ViewModel` init.

### Deep links

```xml
<!-- AndroidManifest.xml -->
<activity android:name=".MainActivity" android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.VIEW" />
        <category android:name="android.intent.category.DEFAULT" />
        <category android:name="android.intent.category.BROWSABLE" />
        <data android:scheme="https" android:host="myapp.example.com" />
    </intent-filter>
</activity>
```

```kotlin
// MainActivity
override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    handleDeepLink(intent.data)
}

private fun handleDeepLink(uri: Uri?) {
    uri?.let { navController.navigate(Route.fromUri(it)) }
}
```

### Background work

```kotlin
// Short work: viewModelScope.launch
viewModelScope.launch(Dispatchers.IO) {
    val data = api.fetchItems()
    _uiState.value = data
}

// Deferrable / guaranteed work: WorkManager
val request = OneTimeWorkRequestBuilder<RefreshWorker>()
    .setConstraints(
        Constraints.Builder()
            .setRequiredNetworkType(NetworkType.UNMETERED)
            .build()
    )
    .build()
WorkManager.getInstance(this).enqueue(request)
```

### Foreground services

For tasks that must run while the user is in another app (audio
playback, location tracking, file upload):

```kotlin
val serviceIntent = Intent(this, AudioPlaybackService::class.java)
ContextCompat.startForegroundService(this, serviceIntent)
```

Foreground services must declare a `foregroundServiceType` in
AndroidManifest.xml as of Android 14 (API 34).

### Push notifications (FCM)

```kotlin
class MyFirebaseMessagingService : FirebaseMessagingService() {
    override fun onNewToken(token: String) {
        api.registerDevice(token)
    }
    override fun onMessageReceived(message: RemoteMessage) {
        // Data messages only -- notification messages auto-display
        val data = message.data
        handlePush(data)
    }
}
```

---

## Flutter

### App lifecycle (`AppLifecycleState`)

```dart
class _MyAppState extends State<MyApp> with WidgetsBindingObserver {
    @override
    void initState() {
        super.initState();
        WidgetsBinding.instance.addObserver(this);
    }

    @override
    void didChangeAppLifecycleState(AppLifecycleState state) {
        switch (state) {
        case AppLifecycleState.resumed:
            ref.read(appStateProvider.notifier).resume();
            break;
        case AppLifecycleState.inactive:
            ref.read(appStateProvider.notifier).pause();
            break;
        case AppLifecycleState.paused:
            ref.read(appStateProvider.notifier).suspend();
            break;
        case AppLifecycleState.detached:
            ref.read(appStateProvider.notifier).dispose();
            break;
        case AppLifecycleState.hidden:
            ref.read(appStateProvider.notifier).hide();
            break;
        }
    }
}
```

### State restoration

```dart
// PageStorageBucket for scroll position, selected tab, etc.
PageStorage(
    bucket: bucket,
    child: ListView(...)
)

// SharedPreferences (simple) or Hive (typed) for persistent state
await SharedPreferences.getInstance().then((prefs) {
    prefs.setInt('selectedTab', 2);
});
```

### Deep links

```dart
// In pubspec.yaml:
// dependencies:
//   app_links: ^6.0.0

final appLinks = AppLinks();
appLinks.uriLinkStream.listen((uri) {
    router.go(uri.toString());
});
```

### Background work

```dart
// Foreground: just an async function
final data = await api.fetchItems();

// Background isolate: compute() for CPU-bound
final result = await compute(parseLargeJson, rawString);

// Background work that survives: flutter_workmanager
Workmanager().registerOneOffTask('refresh', 'refreshTask');
```

---

## React Native

### AppState

```tsx
import { AppState } from 'react-native';

useEffect(() => {
    const sub = AppState.addEventListener('change', next => {
        if (next === 'active') refetch();
        if (next === 'background') flush();
    });
    return () => sub.remove();
}, []);
```

### State restoration

```tsx
// AsyncStorage for simple
await AsyncStorage.setItem('selectedTab', String(tab));

// react-native-mmkv for fast (sync) storage
const storage = new MMKV();
storage.set('user', JSON.stringify(user));
```

### Deep links

```tsx
import { Linking } from 'react-native';

useEffect(() => {
    const sub = Linking.addEventListener('url', ({ url }) => {
        router.navigate(parseUrl(url));
    });
    return () => sub.remove();
}, []);
```

For Expo: `expo-linking` + `Linking.parseInitialURLAsync()` for the cold-start case.

### Background work

```tsx
// Foreground: any async function
const data = await fetch(url).then(r => r.json());

// Background: react-native-background-actions OR Expo TaskManager
import * as TaskManager from 'expo-task-manager';
TaskManager.defineTask('background-fetch', async () => fetch(url));

// Background JS: react-native-jsi-worker or expo-modules-core
```

---

## Common cross-platform mistakes

1. **Doing heavy work on app launch in `main()` / `Application.onCreate()`.**
   Defer to lazy providers so cold start is fast.
2. **Holding strong references to a `UIViewController` / `Activity` past
   its lifecycle.** Memory leak.
3. **Subscribing to a stream in `onCreate` but never unsubscribing.**
   Use `viewModelScope` (Android) or `Task` cancellation (iOS).
4. **Assuming `viewDidLoad` / `onCreate` runs once per app lifetime.**
   On rotation, configuration change, or process recreate, they can
   fire again. Use `SavedStateHandle` (Android) or `@State` in SwiftUI
   to survive.
5. **Forgetting to handle cold-start deep links.** The URL arrives
   before any view is mounted; handle it in `MainActivity.onCreate`
   (Android) or `application(_:didFinishLaunchingWithOptions:)`
   (UIKit) or via `Linking.parseInitialURLAsync` (Expo).