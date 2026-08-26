// Compose Multiplatform (Desktop) bounded parallel pool.
//
// Every task runs on Dispatchers.Default under a concurrency semaphore;
// aggregate progress and completion callbacks hop back to Dispatchers.Main.
// Use the same controller from any Composable:
//   val controller = remember { ParallelJobController(scope) }
//   controller.start(total = 100, onProgress = { progress = it }, onDone = { ... })
//   // later: controller.cancel()

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import java.util.concurrent.atomic.AtomicInteger

class ParallelJobController(private val scope: CoroutineScope) {
    private var job: Job? = null
    @Volatile
    private var cancelled = false

    fun start(
        total: Int,
        maxConcurrency: Int = 4,
        onProgress: (Float) -> Unit,
        onDone: (List<Int>) -> Unit,
        onError: (Throwable) -> Unit,
        onCancel: () -> Unit,
    ) {
        job?.cancel()
        cancelled = false
        job = scope.launch(Dispatchers.Default) {
            val completed = AtomicInteger(0)
            val results = arrayOfNulls<Int>(total)
            val semaphore = Semaphore(maxConcurrency.coerceAtLeast(1))
            try {
                coroutineScope {
                    (0 until total).map { index ->
                        async(Dispatchers.Default) {
                            semaphore.withPermit {
                                if (cancelled) throw CancellationException("cancelled")
                                for (step in 1..10) {
                                    if (cancelled) throw CancellationException("cancelled")
                                    delay(50)
                                }
                                results[index] = index * 2
                                val done = completed.incrementAndGet()
                                withContext(Dispatchers.Main) {
                                    onProgress(done.toFloat() / total)
                                }
                            }
                        }
                    }.awaitAll()
                }
                withContext(Dispatchers.Main) { onDone(results.filterNotNull()) }
            } catch (e: CancellationException) {
                if (cancelled) {
                    withContext(Dispatchers.Main) { onCancel() }
                } else {
                    withContext(Dispatchers.Main) { onError(e) }
                }
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
