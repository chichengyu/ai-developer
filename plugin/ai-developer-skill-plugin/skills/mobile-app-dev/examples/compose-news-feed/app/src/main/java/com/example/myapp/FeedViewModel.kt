package com.example.myapp

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import javax.inject.Inject

data class FeedItem(val id: String, val title: String, val summary: String)

sealed interface FeedUiState {
    data object Loading : FeedUiState
    data class Loaded(val items: List<FeedItem>) : FeedUiState
    data class Error(val message: String) : FeedUiState
}

interface FeedRepository {
    suspend fun fetch(): List<FeedItem>
}

class StubFeedRepository : FeedRepository {
    override suspend fun fetch(): List<FeedItem> = listOf(
        FeedItem(id = "1", title = "First",  summary = "Hello"),
        FeedItem(id = "2", title = "Second", summary = "World"),
    )
}

@HiltViewModel
class FeedViewModel @Inject constructor(
    private val repository: FeedRepository,
) : ViewModel() {
    private val _uiState = MutableStateFlow<FeedUiState>(FeedUiState.Loading)
    val uiState: StateFlow<FeedUiState> = _uiState.asStateFlow()

    init { refresh() }

    fun refresh() {
        viewModelScope.launch {
            _uiState.update { FeedUiState.Loading }
            runCatching { withContext(Dispatchers.IO) { repository.fetch() } }
                .onSuccess { items -> _uiState.update { FeedUiState.Loaded(items) } }
                .onFailure { e -> _uiState.update { FeedUiState.Error(e.message ?: "Unknown") } }
        }
    }
}
