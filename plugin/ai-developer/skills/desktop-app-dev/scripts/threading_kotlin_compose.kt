// Compose Multiplatform (Desktop) background work with cancellation +
// progress + safe UI bridge.
//
// Use Dispatchers.Default / Dispatchers.IO for the long job and
// Dispatchers.Main for UI callbacks. Compose Desktop needs the
// `kotlinx-coroutines-swing` artifact so Dispatchers.Main exists.
//
// Usage inside a Composable:
//   val scope = rememberCoroutineScope()
//   val controller = remember { JobController(scope) }
//   controller.start(
//       total = 100,
//       onProgress = { progressBarProgress = it },
//       onDone = { status = "done: $it" },
//       onError = { status = "error: ${it.message}" },
//       onCancel = { status = "cancelled" })
//   // later: controller.cancel()

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class JobController(private val scope: CoroutineScope) {
    private var job: Job? = null
    private var cancelled = false

    fun start(
        total: Int,
        onProgress: (Float) -> Unit,
        onDone: (Int) -> Unit,
        onError: (Throwable) -> Unit,
        onCancel: () -> Unit,
    ) {
        job?.cancel()
        cancelled = false
        job = scope.launch(Dispatchers.Default) {
            try {
                for (step in 1..total) {
                    if (cancelled) {
                        withContext(Dispatchers.Main) { onCancel() }
                        return@launch
                    }
                    val percent = step.toFloat() / total
                    withContext(Dispatchers.Main) { onProgress(percent) }
                    delay(50)
                }
                withContext(Dispatchers.Main) { onDone(total) }
            } catch (e: CancellationException) {
                throw e
            } catch (e: Throwable) {
                withContext(Dispatchers.Main) { onError(e) }
            }
        }
    }

    fun cancel() {
        cancelled = true
        job?.cancel()
    }
}
