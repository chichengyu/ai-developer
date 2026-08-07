# Task decomposition (Step 0 + Step 3 deep dive)

Concrete guidance for the two steps where most desktop projects go wrong:
digging past the literal ask, and turning the answer into verifiable work.

---

## Part 1: Requirements deep dive (Step 0)

### The six-bucket interrogation

Walk every desktop request through these six buckets. Do not skip a
bucket because the user said "it's simple".

#### 1. Functional -- literal

What the user explicitly asked for. Quote them. If their request is one
sentence ("make me a Notepad clone"), expand it into testable features
before coding.

#### 2. Functional -- implicit

Things they need but didn't say. Always check these:

| Implicit need | Default if user does not specify | Why it matters |
|---|---|---|
| Settings persistence | `%APPDATA%\<AppName>\config.json` | Without this, every launch loses user state |
| Error reporting to user | Modal dialog with copy-to-clipboard | Without this, silent failures |
| Logging | `%LOCALAPPDATA%\<AppName>\logs\app-YYYYMMDD.log` | Without this, no support tickets are solvable |
| Crash reporting | Local dump + opt-in upload | Without this, no post-mortem |
| Single instance | `Mutex` or named pipe | Without this, two processes corrupt state |
| Clean shutdown on logoff | Trap `WM_QUERYENDSESSION` / `Ctrl+C` | Without this, data loss |
| Graceful uninstall | Remove app data on uninstall (or offer to) | Without this, orphaned data |
| DPI awareness | Per-monitor v2 (`<dpiAwareness>PerMonitorV2</dpiAwareness>`) | Without this, blurry on multi-monitor |
| HiDPI icons | Provide 16, 24, 32, 48, 64, 128, 256 px | Without this, ugly in taskbar/start |
| Keyboard navigation | Tab order, Enter on focused button, Esc to cancel | Without this, inaccessible |
| Localizable strings | All user-facing text in a resource file | Without this, no future i18n |
| Time / date handling | `DateTimeOffset`, not `DateTime` (no DST bugs) | Without this, bugs near DST transitions |
| File path handling | `Path.Combine`, not string concat | Without this, broken on non-ASCII paths |

#### 3. Non-functional

| Metric | How to ask |
|---|---|
| Cold start budget | "After double-click, how many seconds before the window is interactive?" |
| Steady-state memory | "How much RAM is acceptable at idle?" |
| Steady-state CPU | "Background CPU usage when nothing is happening?" |
| Latency | "Click-to-feedback budget for the slowest action?" |
| Throughput | "How many records/rows/events per second?" |
| Offline behavior | "What works without network? What explicitly fails?" |
| Reliability | "Acceptable failure rate per year of use?" |
| Data sensitivity | "What data classification (public, internal, confidential, regulated)?" |

If the user does not know, default to:
- Cold start <= 2 s on a 5-year-old laptop
- Idle memory <= 200 MB
- Idle CPU <= 1%
- Click-to-feedback <= 100 ms for visible work, <= 3 s for background work
- Reliability: 99.9% per session

Record the defaults explicitly so they can be revised later.

#### 4. Distribution

| Question | Default |
|---|---|
| Portable EXE or installer? | Installer if recipients are non-technical, portable if power users |
| Per-user or per-machine install? | Per-user (no admin needed) unless the app needs system services |
| Code-signing cert available? | If no, budget $200-500/year and 1-2 weeks of lead time |
| Auto-update? | Yes for any app shipped to non-developers |
| Auto-update channel? | Velopack (multi-framework) for first choice |
| Store distribution? | MSIX + Microsoft Store if recipients are consumers |
| Elevation? | Avoid unless absolutely required; design around it |
| Uninstall | Standard Windows uninstall entry; offer to remove user data |

#### 5. Integration

Map every external dependency. For each, answer:
- What protocol / API?
- Authentication required?
- Failure behavior when unreachable?
- Rate limits?
- Cost (if paid)?

| Integration type | Common examples | Default behavior |
|---|---|---|
| Local file system | Read/write under `%USERPROFILE%`, `%APPDATA%` | Async, debounced, with rollback on error |
| Windows Registry | App config, file associations, MRU lists | Wrap in service class; never call `Reg*` from UI thread |
| Windows services | Background work, hardware access | Separate Windows Service project, not in the GUI app |
| COM / OLE | Office automation, legacy apps | Threading model matters; STA vs MTA |
| Hardware: USB / serial / Bluetooth | Custom devices, instruments | Use manufacturer SDK; never talk raw protocols |
| HTTP REST | Cloud APIs | `HttpClient` with retry, timeout, cancellation |
| WebSocket | Real-time updates | Reconnect with backoff |
| gRPC | Internal service mesh | Strongly typed; needs protobuf |
| Database (local) | SQLite, LiteDB, Realm | Connection pool, migrations |
| Database (server) | SQL Server, Postgres, MySQL | Connection pool, retry, fail-fast on auth |
| Cloud | S3, Azure Blob | Use SDK; never roll your own auth |

#### 6. Failure modes to design for

For each integration point, name the failure mode and the response:

| Failure | Default response |
|---|---|
| Target process not running | Show "target not found" message; auto-retry every N seconds |
| Network unreachable | Cache last successful state; show offline indicator |
| Disk full | Save to temp + warn user; do not silently lose data |
| Permission denied | Show actionable error ("right-click and Run as Administrator") |
| Concurrent modification | File lock or atomic rename; never read-modify-write without lock |
| Corrupt config file | Back up to `config.json.bak`, recreate with defaults |
| Recipient has wrong runtime | Bundle runtime (self-contained publish / PyInstaller) |
| Recipient has wrong OS version | Document minimum Win 10 21H2; refuse to run on older |
| Recipient's AV quarantines the binary | Submit false-positive; never ask recipient to disable AV |

---

### Three questions to always ask

These surface assumptions that the user may not realize they have:

1. **"What is the smallest thing this app must NOT do wrong?"** -- the
   showstopper. Whatever they name is the thing you protect at all costs
   and verify first. Often: "must not lose user data", "must not look
   unprofessional", "must not require admin".

2. **"How will recipients get updates?"** -- forces an answer about
   distribution. The answer "they'll redownload" is valid; it just
   changes the auto-update decision.

3. **"What does this app look like when nothing is happening?"** --
   idle behavior. Background work, tray icon, scheduled tasks, hotkeys
   still firing? This is where desktop apps leak resources.

If the user says "don't care" / "skip it", record that explicitly in
requirements.md with the literal phrase. "Don't care" today may matter
next week; the record is what protects you.

---

### Common omissions to flag

Things the user almost never thinks about but you must:

- Settings migration between app versions (if the schema changes)
- AV false-positive handling (any unsigned / packed binary gets flagged)
- Windows version skew (10 21H2 vs 22H2 vs 11 22H2 vs 11 23H2)
- DPI scaling on multi-monitor with mixed DPI
- Backup of user data (if the app stores anything important)
- Opt-in telemetry (consent UI + persistent setting)
- Crash dump generation (`WER_LOCAL_DUMP` registry key for Windows Error Reporting)
- Logging in production is hard to retrofit; design it in from day one
- Disk I/O contention if running on a slow laptop SSD
- Battery impact if the app runs on a laptop (avoid busy-loops; honor
  Windows power events)

---

## Part 2: Task decomposition (Step 3)

### Decomposition principles

Each task must be:
1. **Atomic** -- completable in one focused session (<= a few hours).
2. **Verifiable** -- has a concrete acceptance criterion that can be
   checked in <= 5 minutes.
3. **Independent** -- has zero or few dependencies on other tasks.
4. **Owned** -- has a single owner (you, in this case).
5. **Sized** -- S/M/L, not "big" or "small".

If a task is bigger than L, decompose further. If a task has no clear
acceptance criterion, it is not yet a task; it is a wish.

### Standard task order

```
T1  Project scaffold
T2  Core data model / persistence
T3  Core services
T4  UI shell
T5  Feature tasks (one per user-visible feature)
T6  Polish (logging, errors, settings migration, a11y)
T7  Integration (auto-update, telemetry, crash reporter)
T8  Packaging (EXE/installer build, code-sign, hash pinning)
T9  Documentation
```

#### T1 -- Project scaffold

What goes in:
- Repo with conventional layout (`src/`, `tests/`, `docs/`, `assets/`)
- Build system + lock file
- CI script that builds and runs tests
- Editor / IDE config (`.vscode/`, `.editorconfig`)
- License file
- README skeleton

Acceptance: `git clone && <build-command>` produces a runnable skeleton
on a clean machine.

#### T2 -- Core data model / persistence

What goes in:
- Settings schema (typed, with migration support)
- File format (if any) -- parser, serializer, schema validator
- Database schema + migrations
- Sample data for development

Acceptance: a unit test reads/writes round-trip; schema migration v1 -> v2
works without data loss.

#### T3 -- Core services

What goes in:
- Threading model (one worker pool, one UI bridge)
- File system watcher (if needed)
- HTTP client wrapper (if needed)
- IPC mechanism (if multiple processes)
- Logging service (file + optional ETW / console)
- Error reporting service

Acceptance: each service has at least one unit test that exercises the
failure path (network down, disk full, permission denied).

#### T4 -- UI shell

What goes in:
- Main window with proper DPI awareness
- Navigation (menu / sidebar / tabs)
- Theming (light + dark if cross-platform)
- Layout that survives window resize down to 800x600

Acceptance: app launches, shows the empty shell, resizes cleanly,
respects Windows theme.

#### T5 -- Feature tasks (one per feature)

Each user-visible feature is one task. Example for a "log viewer" app:

- T5.1 Open local log file (`File > Open` -> reads -> shows in grid)
- T5.2 Filter by level
- T5.3 Live tail (file watcher -> append rows)
- T5.4 Search across all open files
- T5.5 Export filtered view to CSV

Each has its own acceptance test (open the file, see the rows; filter
hides non-matching; etc.).

#### T6 -- Polish

- Settings migration
- Logging in production
- Error UI (not just console.WriteLine)
- Accessibility audit (tab order, screen reader labels, contrast)
- Keyboard shortcuts (Ctrl+S, Ctrl+O, F1 help)
- Localization hook (even if shipping one language, structure the strings)

Acceptance: app passes an a11y audit (NVDA / Narrator can read every
control); logs roll over after N MB; settings v1 schema migrates to v2.

#### T7 -- Integration

- Auto-update channel (Velopack / Squirrel / WinSparkle)
- Crash reporter (opt-in; local dump + upload if user opts in)
- Telemetry (opt-in; same)
- License check (if commercial)

Acceptance: install v1, publish v2 to channel, app updates on restart;
crash produces a dump; opt-in flow shows and persists choice.

#### T8 -- Packaging

- Build script (PyInstaller / dotnet publish / cargo tauri build)
- Code-sign (signtool + timestamp)
- Hash pinning (for auto-update integrity)
- Installer production (MSI / NSIS / MSIX)
- Verification on a clean Windows VM

Acceptance: `.uild.ps1` from a clean checkout produces a signed installer
that runs on a Windows 11 VM with no preinstalled runtime.

#### T9 -- Documentation

- User README (install, run, troubleshoot)
- Build instructions for maintainers
- Architecture overview (1 page)
- Known limitations + showstopper assumption from Step 0

Acceptance: a fresh developer can build and run from the README alone,
without asking you a question.

---

### Variations by app category

- **Game automation**: insert **T3.5 anti-cheat research spike** before
  T5 features. If standard SendInput works, T5 stays as planned. If the
  game's anti-cheat blocks it, T5 changes shape and you may need a
  different transport.
- **System tool**: T3 starts with a **Win32 capability survey** -- some
  APIs require elevation and you need to know that before T4.
- **Multimedia**: T4 includes **GPU device enumeration** and **asset
  pipeline**. T5 features depend on it.
- **Cross-platform desktop**: T8 includes **per-platform packaging**
  (MSI for Windows, DMG for macOS, deb/AppImage for Linux).

---

### Worked example: simple file converter

User ask: "I want a desktop app that converts Markdown files to PDF."

Step 0 fills out the checklist (settings persistence? where? does it
auto-update? etc.). Step 1: category B (productivity, no hardware input).
Step 2: C# WPF or Tauri (cross-platform not needed; pick by team skills).
Step 3 decomposes:

```
T1  Project scaffold            [S]  scaffold, CI, license, README
T2  Core data model             [S]  FileConverterSettings class + JSON persistence + migration
T3  Core services               [M]  markdown->HTML service, HTML->PDF service (via wkhtmltopdf or similar)
T4  UI shell                    [S]  single-window WPF shell with File>Open, File>Save As, status bar
T5.1 Open Markdown file         [S]  File>Open reads, displays in editor pane
T5.2 Live preview               [M]  editor + preview side-by-side, debounced re-render
T5.3 Convert to PDF             [S]  button -> render -> save dialog -> write
T5.4 Drag-and-drop input        [S]  accept .md files dropped on window
T5.5 Batch convert folder       [M]  File>Open Folder -> queue -> progress -> log
T6  Polish                      [M]  logging, error UI, recent files, settings, a11y
T7  Auto-update                 [M]  Velopack channel + first version published
T8  Packaging                   [S]  dotnet publish self-contained single-file + sign
T9  Documentation               [S]  user README + maintainer build instructions
```

DAG: T5.1..T5.5 all depend on T4; T6 depends on all T5.*; T7+T8 depend
on T6; T9 depends on T8.

Showstopper: T5.3 (PDF output is the entire reason for the app). Verify
that T5.3 works on a clean VM before declaring T1-T4 "done".

---

### Worked example: TLBB game bot

User ask: "Make me a bot for 天龙八部怀旧版 that auto-farms a dungeon."

Step 0 fills out the checklist -- anti-cheat research is bucket 6
(failure modes), and the showstopper question "what must NOT go wrong?"
is almost certainly "must not get the account banned".

Step 1: category A (game automation). Step 2: C# or C++ for SendInput;
pick by team familiarity. The matrix tilts toward C# for solo speed.

Step 3:

```
T1  Project scaffold            [S]
T2  Game data model             [M]  load dungeon/level/skill tables from local Helper/*.html
T3  Core services               [M]  window finder, foreground manager, key sender
T3.5 Anti-cheat research        [L]  spike: does the game block SendInput? check EAC / TP rules
T4  UI shell                    [M]  window picker + key map editor + log pane
T5.1 Window selection           [S]  dropdown of top-level windows (auto-refresh)
T5.2 Key map editor             [M]  bind any VK code to a logical action; save/load
T5.3 Loop engine                [L]  time-based loop with jitter, cancellable, logged
T5.4 Difficulty + dungeon flows [M]  code one dungeon flow end-to-end (普通 / 困难)
T5.5 Anti-detection measures    [M]  jitter, idle variation, error recovery
T6  Polish                      [M]  logging, error recovery, settings persistence
T7  Self-update                 [M]  Velopack channel for the recipient
T8  Packaging                   [S]  single-file EXE + sign + source embedded
T9  Documentation               [S]
```

T3.5 is `[showstopper]` -- if SendInput is blocked, the entire approach
fails and you re-plan. Verify T3.5 in the first hour, not the last.

Note: account safety drives many of the other tasks. T5.5 is not
optional; it is the core risk mitigation.

---

### Patterns for blocking work

When a task depends on something external (game version, hardware
delivery, third-party API), do not block waiting for it. Use a **spike**
(S/M task that ends with a decision, not code):

```
T-spike <Name>          [S]  answer the question "<thing> works / doesn't work"
                         deliverable: a 1-paragraph write-up + a decision
                         acceptance: I know whether to proceed with T-Next
```

If the spike answer is "no", you cancel T-Next and the project pivots
without sunk cost.

---

### Verification gates between phases

Do not move from Phase N to Phase N+1 until the gate is passed:

- Gate 0 -> 1: requirements.md is complete and signed off by the user
- Gate 1 -> 2: category + binding constraint are unambiguous
- Gate 2 -> 3: framework chosen with rejection reasons documented
- Gate 3 -> 4: every task has acceptance criteria; showstopper is tagged
- Gate 4 -> 5: every feature task has its acceptance test passing
- Gate 5 -> 6: integration tasks complete on a clean VM
- Gate 6 -> 7: full verification checklist passes; showstopper holds
- Gate 7: handoff doc reviewed by someone who has not seen the project
