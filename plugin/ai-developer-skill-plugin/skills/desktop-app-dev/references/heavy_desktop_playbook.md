# Heavy desktop playbook (重型桌面端)

A deep-dive for data-heavy, multi-window, long-lived desktop applications.
It applies to Category B (productivity / business), Category C (system /
DevOps), and Category D (multimedia / creative) when the app exceeds
simple-tool scale. Read it after SKILL.md Steps 0-3 and pair it with
`references/threading_playbook.md`, `references/ui_hard_requirements.md`,
and `references/distribution_playbook.md`.

## When an app is heavy

An app is heavy when any two of these are true:

- 10+ feature modules or a plugin surface.
- 100k+ rows in one grid, or 1M+ records in a local database.
- 5+ windows, dockable panels, MDI, or a workspace-style shell.
- Long-running background jobs that survive minutes or hours.
- Cold start under 2 seconds while loading more than one subsystem.
- Server-backed integration with retry, offline, and multi-user behavior.
- Enterprise deployment with settings migration and crash reporting.

For these apps, "it works on my machine" is not acceptance. The
architecture, data path, threading, memory, and startup behavior must be
designed and measured.

## 1. Layered architecture

### 1.1 The five layers

1. **UI layer** -- XAML / controls / widgets; no business logic.
2. **ViewModel / Controller** -- state, commands, formatting, validation.
3. **Service layer** -- use cases, orchestration, business rules.
4. **Data access layer** -- repositories, SQL, cache, migration.
5. **Infrastructure** -- logging, settings, IPC, crash reporting, DI.

Rules:

- Views never call repositories or the database directly.
- Services never touch controls or dispatchers.
- Data access returns domain objects, not grid rows.
- Feature code lives in feature modules, not one giant "utils" folder.

### 1.2 Framework mapping

| Layer | WPF / WinUI | Qt | PySide6 | Tauri / Electron |
|---|---|---|---|---|
| UI | XAML views | QML / widgets | QWidgets / QML | HTML / webview |
| State | MVVM ViewModel | QObject / model | model / controller | store / state |
| Service | C# service class | C++ QObject service | Python service | Rust / Node service |
| Data | EF Core / Dapper / SQLite | Qt SQL / QAbstractItemModel | sqlite3 / SQLAlchemy | SQLite / tauri-plugin-store |
| Infra | Serilog + DI | spdlog + factory | logging module + manual DI | tracing / logger |

### 1.3 Dependency injection

- Use constructor injection. Resolve the graph once at the **composition
  root** (App startup); never resolve inside a view.
- .NET: `Microsoft.Extensions.DependencyInjection`. For NativeAOT and
  trimming, prefer compile-safe registration or source generators; avoid
  reflection-heavy containers at startup.
- Kotlin Compose: Koin or manual factories. Go: `wire` / `dig` or a
  manual composition root. Python: manual composition root. Rust: pass
  dependencies through constructors or a service struct.
- Register services by interface, not concrete classes, so tests can
  replace them.

### 1.4 Module boundaries

- One folder per feature: `src/<Feature>/` with `ui/`, `viewmodel/`,
  `services/`, `data/`.
- A feature exposes one public interface; other features depend on that
  interface, not internal classes.
- Use an event aggregator or message bus for decoupled communication
  (WPF `EventAggregator`, Qt signals, Python `pubsub`, Tauri events).
- Never allow feature A to reach into feature B's XAML or widgets.

### 1.5 Plugin system

- Define a plugin contract: interface, versioned API, discovery folder,
  manifest, and load order.
- Load plugins in an isolated context where possible; a broken plugin
  must not crash the host.
- Validate plugin manifests before loading; log load failures with the
  exact reason.
- Keep plugin-facing APIs stable and marked with version numbers.

## 2. Data-heavy UI

### 2.1 Virtualization or paging

Never bind the full dataset into the UI at once. Long lists and grids
must be virtualized or paged, or both:

- The UI renders only the visible page or viewport.
- The data layer owns filtering, sorting, and aggregation.
- Search is debounced (250-400 ms) and cancellable.
- Large result sets use keyset or offset pagination, never "load all
  rows then paginate in memory".

### 2.2 Framework virtualization matrix

| Framework | Primary technique |
|---|---|
| WPF | `DataGrid` + `EnableRowVirtualization`, `VirtualizingStackPanel`, deferred scrolling, `ObservableCollection` only for the visible page |
| WinUI 3 | `ItemsRepeater` / `ListView` + `IncrementalLoadingCollection`, virtualizing data source |
| WinForms | `DataGridView.VirtualMode` + `CellValueNeeded` |
| Qt / QML | `QAbstractItemModel` + `canFetchMore` / `fetchMore`, `QSortFilterProxyModel`, `QTableView` lazy model |
| PySide6 | `QAbstractTableModel` + `QTableView`, lazy fetch, batched `modelReset` |
| tkinter | `ttk.Treeview` + pagination only; never 100k rows in one widget |
| Tauri / Electron | virtual list (TanStack Virtual / react-window), bounded DOM nodes, batched IPC |
| Go Fyne / Gio | custom list widget with item recycling / lazy data |

### 2.3 Data layer rules

- Push filtering, sorting, grouping, and aggregation into SQL or the
  repository layer.
- Index columns used by search and sort.
- Use parameterized queries; never build SQL by string concatenation.
- Cache only stable reference data; invalidate by version or event.
- Keep row-to-object mapping outside the UI layer.

### 2.4 Rendering rules

- Update only the visible page; batch model changes into one notification.
- Throttle progress and status updates (see threading playbook).
- Avoid per-cell bindings for thousands of cells; use templates with
  shared converters and minimal property notifications.
- Reuse control templates; do not recreate heavy controls on every refresh.
- Measure 100k-row scroll and render latency in Step 6.

## 3. Long-running work

- Use `references/threading_playbook.md` worker / pool templates for every
  background job; never block the UI thread.
- Give each long job a state machine:
  `pending -> running -> paused/cancelled -> completed/failed`.
- Persist job state in SQLite (`scripts/task_queue.py`) or the app
  database so restarts can resume or show history.
- Aggregate progress with total / done / failed counts, bytes, speed,
  ETA, and a per-item error list.
- Cancel pending work first, then ask running work to stop cooperatively,
  then wait with a timeout and flush logs.
- COM work runs on a dedicated STA thread with its own apartment; never
  call COM from a random thread-pool thread.

## 4. Startup and memory

### 4.1 Startup budget

- Lazy-load feature modules; show the main shell first.
- Defer non-critical initialization (telemetry, update checks, heavy
  indexes) until after the first frame.
- Use a splash or skeleton only when cold start exceeds the Step 0 budget.
- Record cold start on the same clean VM used for acceptance.

### 4.2 .NET

- Prefer NativeAOT / trimming when the UI stack allows; otherwise keep
  single-file compression on and use `ReadyToRun` only when cold start
  demands it.
- Use `dotnet-counters`, PerfView / EventPipe, and a startup trace to find
  slow module loads.
- Avoid reflection-heavy DI and `Activator.CreateInstance` in hot paths.

### 4.3 Python

- Import heavy libraries lazily inside functions; keep `pandas`, `numpy`,
  and GUI backends out of module scope when possible.
- Use `tracemalloc` and `py-spy dump` to find leaks and blocking frames.
- Keep PyInstaller excludes current; add only what the app really imports.

### 4.4 Qt / C++

- Use precompiled headers, lazy plugin loading, and compiled QML.
- Prefer static Qt when size allows; profile with Qt Creator Profiler.
- Keep `QTimer` and event-loop work off the render path.

### 4.5 Web-based desktop

- Lazy-load routes and heavy JS chunks; keep the DOM bounded with a
  virtual list.
- Batch IPC payloads; never send one event per row.
- Keep the webview on the visible page only; unload hidden windows.

### 4.6 Memory leak rules

- Unsubscribe events / handlers when a view or window closes.
- Dispose timers, dispatchers, DB connections, `HttpClient`, and file
  streams.
- Avoid static collections that grow with user activity; use weak
  references or bounded caches.
- Take two memory snapshots (after launch and after a 1-hour workload);
  growth beyond the Step 0 budget is a release blocker.

## 5. Stability and production readiness

- Enforce **single instance** with a named mutex / named pipe; a second
  launch activates the existing window.
- Register an unhandled-exception handler and write a crash dump
  (`WER_LOCAL_DUMP` on Windows, `~/.local/share/<App>/crash` elsewhere).
- Rotate logs and keep the last N days; every log line has a timestamp,
  level, feature, and correlation id.
- Implement settings migration (`v1 -> v2`) before users hit it.
- Wrap database writes in transactions and back up user data before
  schema migration.
- Define behavior for offline, disk full, permission denied, and server
  retry with backoff.
- Run `templates/security_checklist.md` before release.

## 6. Multi-window and navigation

- Own windows through a window manager; each window gets its own
  ViewModel lifetime.
- Decide MDI vs tabbed vs docked panels from the workflow, not fashion.
- Persist window bounds, splitter positions, column widths, and the
  active page.
- Use per-monitor DPI awareness (`templates/dpi_manifest.xml`) and re-test
  on mixed-DPI setups.

## 7. Performance acceptance

| Metric | Budget source | How to measure |
|---|---|---|
| Cold start | Step 0 | `scripts/heavy_desktop_verify.ps1 -AppPath <exe> -SampleSeconds 60` |
| Idle memory | Step 0 | same report, `AvgWorkingSetMB` after workload completes |
| Idle CPU | Step 0 | same report, `CpuPercent` |
| 100k-row scroll / render | Step 0 | manual or UI test on the target grid |
| Click-to-feedback | Step 0 | manual timing or automated UI test |
| 1-hour memory growth | Step 0 | two snapshots, growth in `AvgWorkingSetMB` |

Acceptance defaults from `references/task_decomposition.md`:

- Cold start <= 2 s on a 5-year-old laptop.
- Idle memory <= 200 MB.
- Idle CPU <= 1%.
- Click-to-feedback <= 100 ms visible work / <= 3 s background work.

## Mapping to existing skill assets

- Threading: `references/threading_playbook.md` + `scripts/threading_*`
- Persistence queue: `scripts/task_queue.py`
- UI hard requirements: `references/ui_hard_requirements.md`
- Deep UI implementation: `references/desktop_ui_playbook.md`
- Packaging / size / memory: `references/distribution_playbook.md`
- Build helpers: `scripts/build_*.ps1` with `-BackupSource`
- Verification: `scripts/heavy_desktop_verify.ps1` +
  `templates/heavy_desktop_acceptance.md`
