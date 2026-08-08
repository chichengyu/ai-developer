# Threading playbook

Deep reference for every background-work decision in this skill. Read this
when Step 4.1 applies, before writing a worker, and again during Step 6.
The one-sentence rule from `SKILL.md` stays the same: **never block the UI
thread and never mutate UI from a worker.**

## 1. The worker contract

Every `scripts/threading_*` template follows the same contract so a job can
be ported between frameworks without redesigning its interface:

| Concern | Contract |
|---|---|
| Start | `start()` runs exactly one job; a second `start()` while running throws or is rejected. |
| Cancel | `cancel()` requests cooperative cancellation; the job checks between units of work. |
| Progress | `progress(value)` delivers 0..1 or a framework-native progress object. |
| Done | `done(result)` runs exactly once on the UI thread. |
| Error | `error(exception)` runs on the UI thread and never leaves the worker alive. |
| Cancel callback | `onCancel` is optional but recommended so the UI can clear "working" state. |
| UI bridge | All callbacks cross the thread boundary through the framework's dispatcher/event API. |

Templates that do not expose a literal `start()`/`cancel()` pair (for
example the Rust channel helpers) document the equivalent call names.

## 2. Core invariants

1. **UI thread affinity.** A desktop UI owns its controls on one thread.
   Every update must be marshalled to that thread: `Dispatcher.Invoke`,
   `Control.BeginInvoke`, `root.after`, queued Qt signals, `Platform.runLater`,
   `MainThread.BeginInvokeOnMainThread`, `fyne.Do`, `RunSafe`,
   `webContents.send`, `upgrade_in_event_loop`, `request_repaint`, or a
   `ReceivePort`.
2. **Cooperative cancellation.** Cancellation is a request, not a kill.
   Check `CancellationToken`, `Task.isCancelled`, `cancel_` flags, or channel
   messages at every loop iteration and long I/O boundary.
3. **Error isolation.** Catch job exceptions in the worker, marshal them to
   the UI thread, and let the UI decide whether to show a dialog, log, or
   retry. Do not let a worker exception crash the process.
4. **Progress is cheap to call and expensive to render.** Throttle or batch
   progress events when the job emits more often than the UI can repaint
   (typically > 60 Hz).
5. **Ownership beats locking.** Move shared mutable state into the worker
   and send immutable snapshots back, instead of locking a shared object
   from two threads.
6. **Graceful shutdown.** Cancel workers before the window closes, wait for
   them with a bounded timeout, and do not leave daemon threads doing file
   or network writes.

## 3. Template map

| Framework | Template | Background primitive | UI bridge | Cancellation |
|---|---|---|---|---|
| WPF | `scripts/threading_wpf.cs` | `Task.Run` | WPF `Dispatcher.Invoke` | `CancellationTokenSource` |
| WinUI 3 | `scripts/threading_winui.cs` | `Task.Run` | `DispatcherQueue.TryEnqueue` | `CancellationTokenSource` |
| WinForms | `scripts/threading_winforms.cs` | `Task.Run` | `Control.BeginInvoke` | `CancellationTokenSource` |
| Avalonia | `scripts/threading_avalonia.cs` | `Task.Run` | `Dispatcher.UIThread.Post` | `CancellationTokenSource` |
| .NET MAUI | `scripts/threading_maui.cs` | `Task.Run` | `MainThread.BeginInvokeOnMainThread` | `CancellationTokenSource` |
| Qt 6 (C++) | `scripts/threading_qt.cpp` | `QThread` | queued signals | `std::atomic_bool` |
| Tauri (Rust) | `scripts/threading_tauri.rs` | `spawn_blocking` / tokio | `AppHandle.emit` | `AtomicBool` |
| Electron | `scripts/threading_electron.ts` + `threading_electron_worker.ts` | `worker_threads` | `webContents.send` | worker cancel message |
| Python tkinter | `scripts/threading_tkinter.py` | `threading.Thread(daemon=True)` | `root.after(0, cb)` | `threading.Event` |
| Python PySide6 | `scripts/threading_pyside6.py` | `QThread` + worker | Signal/slot | `CancelToken` |
| Python GTK | `scripts/threading_glib.py` | `threading.Thread(daemon=True)` | `GLib.idle_add` | `threading.Event` |
| Swift / SwiftUI | `scripts/threading_dispatch.swift` | `Task.detached` | `@MainActor` | `Task.cancel()` |
| Java / JavaFX | `scripts/threading_javafx.java` | `Task` | `Platform.runLater` / Task properties | `Task.cancel()` |
| Kotlin Compose | `scripts/threading_kotlin_compose.kt` | coroutine `Dispatchers.Default` | `Dispatchers.Main` | `Job.cancel()` + flag |
| Flutter Desktop | `scripts/threading_flutter.dart` | `Isolate.spawn` | `ReceivePort` | cancel port message |
| Go / Wails | `scripts/threading_go_wails.go` | goroutine | `runtime.EventsEmit` | `atomic.Bool` |
| Go / Fyne | `scripts/threading_go_fyne.go` | goroutine | `fyne.Do` | `atomic.Bool` |
| Go / walk | `scripts/threading_go_walk.go` | goroutine | `window.RunSafe` | `atomic.Bool` |
| Rust / egui | `scripts/threading_rust_egui.rs` | `std::thread` | `ctx.request_repaint()` + channel | cancel channel |
| Rust / Slint | `scripts/threading_rust_slint.rs` | `std::thread` | `upgrade_in_event_loop` | cancel channel |
| Win32 / C | `scripts/threading_win32.c` | `CreateThread` | `PostMessage` (UI messages only) | `InterlockedExchange` flag |

### 3.1 Bounded pool templates

When the job set is independent and must run with a concurrency limit, use
the pool templates instead of starting N single workers by hand. They all
provide aggregate progress, per-item errors, and a single `cancel()` that
stops pending and running work cooperatively.

| Framework | Template | Concurrency primitive | UI bridge |
|---|---|---|---|
| Python (any UI) | `scripts/threading_pool.py` | `ThreadPoolExecutor` + retry | caller-supplied framework bridge |
| Python / tkinter | `scripts/threading_pool_tkinter.py` | `threading_pool.WorkerPool` | `root.after(0, cb)` |
| Python / PySide6 | `scripts/threading_pool_pyside6.py` | `QThreadPool` + `QRunnable` | queued Qt signals |
| C# / .NET | `scripts/threading_pool_csharp.cs` | `Parallel.ForEachAsync` | `uiMarshaler` (`Dispatcher` / `BeginInvoke` / `MainThread`) |
| Rust / Tauri | `scripts/threading_pool_tauri.rs` | `JoinSet` + `Semaphore` | `AppHandle.emit` |
| Kotlin / Compose | `scripts/threading_pool_kotlin_compose.kt` | coroutine `Semaphore` + `async` | `Dispatchers.Main` |
| TypeScript / Electron | `scripts/threading_pool_electron.ts` + `threading_pool_electron_worker.ts` | bounded `worker_threads` | `webContents.send` |

Neutralino.js and TornadoFX intentionally have no separate template:
Neutralino runs on the JS event loop (spawn OS processes instead of
threading), and TornadoFX uses JavaFX `runAsync` with the same rules as
`threading_javafx.java`.

## 4. Patterns

### 4.1 Single cancellable worker

The default. One job, one `start()`, one `cancel()`, callbacks on the UI
thread. Every template above is this pattern.

### 4.2 Worker pool with a limit

Use when jobs are independent and bounded. The pool must have all of:
a concurrency limit, cooperative cancellation, aggregate progress, an
error callback per item, and one completion callback for the whole batch.

Ready-made pool templates:

- Python: `threading_pool.py` / `threading_pool_tkinter.py` /
  `threading_pool_pyside6.py`
- C#: `threading_pool_csharp.cs` (`Parallel.ForEachAsync` + retry)
- Rust / Tauri: `threading_pool_tauri.rs` (`JoinSet` + `Semaphore`)
- Kotlin / Compose: `threading_pool_kotlin_compose.kt`
- Electron: `threading_pool_electron.ts` (bounded `worker_threads`)

When no template fits (Qt, Go, Flutter), the native primitives are
`QThreadPool` / `QtConcurrent::run`, a buffered channel plus
`sync.WaitGroup`, and `Future.wait` over `Isolate.run` chunks.

Never resize the UI from pool workers; send one aggregated progress event.
If jobs can fail transiently, use the pool's retry policy instead of
writing retry loops in every job.

### 4.3 Sequential queue

For download/transcode/publish pipelines, persist the queue (see
`scripts/task_queue.py`) and run one worker at a time. A UI worker should
read the next task, run it, post progress, and then request the next task
from the UI thread so cancellation points stay visible.

### 4.4 Parallel fan-out with aggregation

Split work into chunks, run them in parallel, and combine results after all
chunks complete:

- Use `Task.WhenAll`, `JoinSet::join_next`, `sync.WaitGroup`, or
  `as_completed`.
- Report overall progress as `(completed / total)` from the aggregation
  point, not per-chunk.
- Cancel all children when one fatal error occurs.

### 4.5 Progress throttling

Do not call the UI bridge more than ~30-60 times per second. Common
strategies:

- C#: `IProgress<T>.Report` is already marshalled; batch inside the job.
- Python tkinter/GTK: compare elapsed time before `after`/`idle_add`.
- Electron: coalesce messages with `requestAnimationFrame` in the renderer.
- Rust/Go: send progress at `max(1, total / 100)` steps.

### 4.6 Thread-safe state handoff

Preferred handoff order:

1. Pass immutable input to the worker.
2. Worker produces immutable result/error.
3. UI thread applies result to controls and local state.

If two threads must share mutable state, confine it behind a lock
(`lock`/`Mutex`/`sync.Mutex`/`threading.Lock`) or use an actor/channel and
document which thread owns each field.

### 4.7 COM / Win32 apartment rules

- STA components (many shell/Office/COM objects) must stay on an STA thread.
- A UI thread is STA in WPF/WinForms/WinUI; background threads are MTA by
  default.
- Do not marshal a raw COM pointer between apartments; use COM marshalling
  or run the COM work on a dedicated STA thread with its own apartment
  initialized.

### 4.8 Dispatcher lifetime

- Capture the dispatcher/window before starting the worker, not inside it.
- WinUI: `DispatcherQueue.GetForCurrentThread()` must be captured on the UI
  thread.
- Tauri/Slint: keep `AppHandle`/`Weak<AppWindow>` clones for worker callbacks.
- Before posting from a worker, check that the window/control is still
  alive (`IsDisposed`, `isDestroyed`, `upgrade()`).

### 4.9 Aggregate progress

Pool callbacks must report `(completed, total, succeeded, failed)` or an
equivalent snapshot, never per-item percent alone. Throttle aggregate
events to the UI repaint budget (about 10-30 per second is enough for a
progress bar). The Python pool exposes `BatchProgress`; the C# and
Electron templates emit `PoolProgress`; Qt and Compose emit the same
snapshot through their own signal/callback types.

### 4.10 Retry with backoff

Retry belongs in the pool, not in every UI job:

- Python: `RetryPolicy(max_attempts, delay_seconds, backoff)` on
  `WorkerPool`.
- C#: `ParallelJobRunner(maxAttempts: 3, retryDelay: TimeSpan...)`.
- Electron: `startParallelJob(..., maxAttempts, retryDelayMs)`.
- Qt: re-enqueue a failed `QRunnable` after `QTimer::singleShot`.
- Go/Rust: keep an attempt counter on the task struct and re-queue with
  `time.After` / `tokio::time::sleep`.

Do not retry cancellation or permanent validation errors. Use
`fail_fast` / `failFast` only when one failure makes every other task
useless.

### 4.11 Backpressure

The pool is the backpressure boundary. Queue tasks first, then start a
bounded number of workers; never submit unbounded futures directly from a
UI click handler. For very large batches, add an explicit queue length
limit and show "queued" in the UI so the user can cancel before thousands
of tasks are submitted.

### 4.12 Cancellation fan-out

One `cancel()` must:

1. Set a shared cancellation flag/event/token.
2. Cancel futures that have not started.
3. Ask running tasks to stop at their next checkpoint.
4. Wait for the pool with a bounded timeout on window close.
5. Invoke `on_cancel` exactly once after the batch settles.

The pool templates implement this contract. Do not terminate threads or
kill isolates; cooperative cancellation is the only portable option.

## 5. Anti-patterns

- Blocking the UI thread with `Thread.Sleep`, `time.sleep`, sync sockets,
  DB queries, or large file reads.
- Mutating controls from a worker thread "because it usually works".
- Using `PostMessage`/`SendMessage` for keyboard or mouse input (input must
  use `SendInput` / `CGEventPost` / `XTestFakeInputEvent`).
- Cancelling by killing the thread or isolate; always cooperate.
- Ignoring exceptions inside the worker so the UI waits forever.
- Creating unbounded worker pools for UI-triggered jobs.
- Keeping an unbounded task queue and submitting every task at once.
- Reimplementing retry inside each job instead of using a pool policy.
- Updating progress 10,000 times per second and repainting each time.
- Updating the UI per item when an aggregate progress event is enough.
- Waiting on the UI thread for a worker (`Join()` in a click handler).
- Sharing mutable collections between threads without ownership or locks.
- Starting a new job without cancelling the previous one.

## 6. Step 6 threading checklist

- [ ] No clickable handler blocks: all sleep/IO/CPU work is in a worker.
- [ ] Every worker callback crosses the UI bridge; no direct control writes.
- [ ] `cancel()` is cooperative and checked at every loop iteration.
- [ ] Start is single-flight: repeated start cannot spawn parallel jobs.
- [ ] Progress is throttled and can be disabled.
- [ ] Errors are marshalled and logged/shown; the worker state resets.
- [ ] Worker pool concurrency is bounded.
- [ ] Pool reports aggregate progress and the UI throttles it.
- [ ] Pool `cancel()` cancels pending futures and asks running tasks to stop.
- [ ] Retry/backoff is configured at the pool level for transient failures.
- [ ] Window close cancels jobs and waits with a bounded timeout.
- [ ] Shared mutable state has a clear owner or lock.
- [ ] Threading template matches the framework in the template map above.
