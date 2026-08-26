package com.example.myapp

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun FeedScreen(
    modifier: Modifier = Modifier,
    viewModel: FeedViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    FeedContent(state = state, modifier = modifier, onRefresh = viewModel::refresh)
}

@Composable
fun FeedContent(
    state: FeedUiState,
    modifier: Modifier = Modifier,
    onRefresh: () -> Unit,
) {
    Column(modifier = modifier.fillMaxSize()) {
        when (state) {
            is FeedUiState.Loading -> LoadingIndicator()
            is FeedUiState.Loaded -> FeedList(state.items)
            is FeedUiState.Error -> ErrorView(message = state.message, onRetry = onRefresh)
        }
    }
}

@Composable
private fun LoadingIndicator() {
    Row(
        modifier = Modifier.fillMaxSize(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        CircularProgressIndicator(
            modifier = Modifier.semantics { contentDescription = "Loading" },
        )
    }
}

@Composable
private fun FeedList(items: List<FeedItem>) {
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        items(items, key = { it.id }) { item ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(text = item.title, style = MaterialTheme.typography.titleMedium)
                    Text(text = item.summary, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}

@Composable
private fun ErrorView(message: String, onRetry: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(text = "Couldn't load feed")
        Text(text = message, style = MaterialTheme.typography.bodySmall)
        // OutlinedButton(onClick = onRetry) { Text("Retry") }  // uncomment in real app
    }
}

@Preview(showBackground = true)
@Composable
private fun PreviewFeedLoaded() {
    FeedContent(
        state = FeedUiState.Loaded(
            items = listOf(
                FeedItem(id = "1", title = "First", summary = "Hello"),
                FeedItem(id = "2", title = "Second", summary = "World"),
            )
        ),
        modifier = Modifier,
        onRefresh = {},
    )
}
