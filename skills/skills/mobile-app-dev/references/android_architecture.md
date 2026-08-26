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
