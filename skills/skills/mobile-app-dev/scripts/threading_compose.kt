// threading_compose.kt -- canonical async + UI bridge for Compose.
//
// Use ViewModel + StateFlow + collectAsStateWithLifecycle. All IO on
// Dispatchers.IO; UI on Dispatchers.Main via collectAsState.

package com.example.myapp.threading

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.SavedStateHandle
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.update

// MARK: - UI state sealed class

sealed interface FeedUiState {
    data object Loading : FeedUiState
    data class Loaded(val items: List<Item>) : FeedUiState
    data class Error(val message: String) : FeedUiState
}

// MARK: - Data model

data class Item(val id: String, val title: String, val summary: String)

// MARK: - Repository / API interface

interface FeedAPI {
    suspend fun fetchFeed(): List<Item>
}

class LiveFeedAPI : FeedAPI {
    override suspend fun fetchFeed(): List<Item> {
        // Real implementation: Retrofit + OkHttp + kotlinx.serialization.
        // This example returns a hard-coded stub so the smoke test can run
        // without network access.
        delay(10)
        return listOf(
            Item("1", "First", "Hello"),
            Item("2", "Second", "World"),
        )
    }
}

private suspend fun delay(ms: Long) =
    kotlinx.coroutines.delay(ms)

// MARK: - ViewModel

class FeedViewModel(
    private val api: FeedAPI = LiveFeedAPI(),
    private val io: CoroutineDispatcher = Dispatchers.IO,
) : ViewModel() {

    private val _uiState = MutableStateFlow<FeedUiState>(FeedUiState.Loading)
    val uiState: StateFlow<FeedUiState> = _uiState.asStateFlow()

    init {
        load()
    }

    fun load() {
        viewModelScope.launch {
            _uiState.update { FeedUiState.Loading }
            runCatching { withContext(io) { api.fetchFeed() } }
                .onSuccess { items -> _uiState.update { FeedUiState.Loaded(items) } }
                .onFailure { t ->
                    _uiState.update { FeedUiState.Error(t.message ?: "Unknown") }
                }
        }
    }

    fun retry() = load()
}

// MARK: - Compose entry

@Composable
fun FeedScreen(viewModel: FeedViewModel = viewModel()) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    FeedContent(state, onRetry = viewModel::retry)
}

@Composable
fun FeedContent(state: FeedUiState, onRetry: () -> Unit) {
    when (state) {
        is FeedUiState.Loading -> LoadingIndicator()
        is FeedUiState.Loaded -> ItemList((state as FeedUiState.Loaded).items)
        is FeedUiState.Error -> ErrorView(
            message = (state as FeedUiState.Error).message,
            onRetry = onRetry,
        )
    }
}

@Composable
fun LoadingIndicator() { /* ... */ }
@Composable
fun ItemList(items: List<Item>) { /* ... */ }
@Composable
fun ErrorView(message: String, onRetry: () -> Unit) { /* ... */ }

// MARK: - Smoke test (no Compose; pure VM)

fun smokeTest() {
    val vm = FeedViewModel()
    // State machine is Loading until coroutine completes.
    assert(vm.uiState.value is FeedUiState.Loading)
    // For a real test, use kotlinx-coroutines-test Main dispatcher rule.
    println("[OK] threading_compose smoke")
}