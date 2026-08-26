// compose-counter/ -- minimal Compose counter app demonstrating the
// threading_compose.kt pattern. Drop into a fresh Android Studio project.

package com.example.compose_counter

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme {
                CounterScreen()
            }
        }
    }
}

class CounterViewModel : ViewModel() {
    private val _count = MutableStateFlow(0)
    val count: StateFlow<Int> = _count.asStateFlow()

    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    fun increment() = _count.update { it + 1 }
    fun reset() = _count.update { 0 }

    fun loadFromNetwork() {
        viewModelScope.launch {
            _isLoading.update { true }
            try {
                withContext(Dispatchers.IO) { delay(300) }
                _count.update { (1..100).random() }
            } finally {
                _isLoading.update { false }
            }
        }
    }
}

@Composable
fun CounterScreen(viewModel: CounterViewModel = viewModel()) {
    val count by viewModel.count.collectAsStateWithLifecycle()
    val isLoading by viewModel.isLoading.collectAsStateWithLifecycle()
    CounterContent(count, isLoading,
        onIncrement = viewModel::increment,
        onReset = viewModel::reset,
        onLoad = viewModel::loadFromNetwork)
}

@Composable
fun CounterContent(
    count: Int,
    isLoading: Boolean,
    onIncrement: () -> Unit,
    onReset: () -> Unit,
    onLoad: () -> Unit,
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = count.toString(),
                fontSize = 96.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.semantics { contentDescription = "Count: $count" }
            )
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                OutlinedButton(onClick = onReset) { Text("Reset") }
                Button(onClick = onIncrement) { Text("Increment") }
            }
            Button(onClick = onLoad, enabled = !isLoading) {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.size(20.dp))
                } else {
                    Text("Load from network")
                }
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
fun Preview() {
    MaterialTheme {
        CounterContent(
            count = 42,
            isLoading = false,
            onIncrement = {}, onReset = {}, onLoad = {},
        )
    }
}
