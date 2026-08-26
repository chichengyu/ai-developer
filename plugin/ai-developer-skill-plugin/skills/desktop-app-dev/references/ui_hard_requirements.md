# UI hard requirements (界面硬性要求)

Canonical implementation checklist behind the `界面硬性要求` table in
`SKILL.md`. Every desktop GUI built with this skill must pass
UI-01..UI-19 unless the user explicitly waives an item in
requirements.md. Waived items must still be recorded with the reason.

## Scope

Applies to the whole app surface: navigation, tables, forms, dialogs,
menus, toolbars, status bars, theme center, log center, and every
popup / tooltip. Do not apply these rules to only one page.
Deep implementation guidance (tokens, theming, controls, keyboard,
state management, accessibility, UI performance):
`references/desktop_ui_playbook.md`.

## UI-01 全局主题与配色统一 (Global theme and color consistency)

- Use one token source for colors. Navigation, table, forms, dialogs,
  menus, toolbars, and status bars read the same background, text,
  border, accent, and semantic tokens.
- If the user does not specify a theme, imitate the Codex desktop UI:
  neutral dark surfaces, light gray text, one visible accent color,
  visible borders between panels.
- Every button, icon, link, and selected row must be visibly different
  from its background in normal, hover, pressed, and disabled states.
  A control that disappears into the background is a release blocker.
- The app-wide theme (light / dark / custom) is one setting, not
  separate per-widget settings.

Example Codex-like dark token set (use the framework equivalent):

| Token | Value | Use |
|---|---|---|
| bg-app | #1e1f24 | window / page background |
| bg-panel | #26282e | nav, table header, toolbar |
| bg-elevated | #2f323a | dialogs, menus, dropdowns |
| bg-input | #141519 | inputs, search, editors |
| border | #3d414a | separators, control borders |
| text-primary | #eceff4 | main labels and cell text |
| text-secondary | #a8adb8 | hints, metadata |
| accent | #7c8cf8 | selected nav, primary buttons, focus |
| accent-hover | #94a1ff | hover state |
| danger | #e5484d | destructive / error |
| warning | #f5a524 | warnings |
| success | #30a46c | success |
| info | #4cc2ff | informational |

## UI-02 全局控件样式统一 (Global control style consistency)

- Right-click (context) menus, dropdowns, input placeholders,
  scrollbars, buttons, pagination, dialogs, and editors share the same
  styling system: same tokens, same radii, same spacing.
- Default dropdown selection in pagination, search, and edit-form
  controls uses the same selected-item style everywhere.
- All dialogs share the same header, body, footer, button order, and
  color tokens; do not mix framework default styling with custom pages.
- Input placeholders use a consistent muted color and are not the only
  label; each field has a visible label or example.

## UI-03 文字对比度 (Contrast)

- Normal text vs background >= 4.5:1.
- Large text, icons, and interactive glyphs >= 3:1.
- Disabled controls remain distinguishable from enabled controls
  (different border / opacity, not invisible text).
- Verify contrast against the selected theme before shipping; do not
  rely on "it looks fine on my monitor".

## UI-04 布局对齐与溢出 (Layout alignment and overflow)

- Row heights, column widths, paddings, margins, and vertical baselines
  are consistent across left nav, right tables, toolbars, and dialogs.
- Fixed-height areas use scrollbars; text that can exceed a cell uses
  wrapping or truncation with a full-text tooltip (UI-08).
- No page element may be clipped without a visible scrollbar or wrap.
- Table hints and status text must not share one line with the search
  bar; put them on a separate row, allow wrapping, and add vertical
  scroll when content exceeds the viewport.

## UI-05 每页单表格 (One table per page)

- A right-side page shows one management table. If the feature needs a
  second table, open a separate page / view instead of stacking two
  tables side by side.

## Loading states (all buttons and lists)

- Every action button that starts a background job shows a visible busy
  state: disabled plus a text suffix or spinner-equivalent progress.
- Every list / table that is loading shows a visible progress bar. When
  the background job reports progress, the bar renders 0-100%; when no
  percentage is available it stays indeterminate. The bar and disabled
  state are restored only after the job settles (done / failed /
  cancelled).
- Busy state is per control and reference-counted, so two simultaneous
  jobs never clear a loading state early.
- No job starts a button/table loading state without a matching settle
  path; failures also restore controls and log the reason.

## Startup loading screen (packaged EXE)

- Every packaged EXE shows a startup window with animation and a visible
  progress bar before the main window opens; a blank window during startup
  is not acceptable.
- The startup screen may fade in, animate a logo / title, or cycle status
  text. If initialization can report progress, the bar renders 0-100%.
- Startup work stays non-blocking enough to repaint the animation; when
  initialization finishes, the splash hides and the main window appears.
- Startup failures go to the crash log / log center and the splash shows a
  readable error instead of freezing forever.

## UI-06 页面标题不重复 (No duplicated page title)

- When the left navigation already shows the menu name, the right table
  page must not repeat that name in a heading or toolbar. Keep a unique
  page description / action bar only.

## UI-07 列表分页 (Pagination)

- Management lists have bottom pagination: total count, page size
  selector, page numbers or compact pager, previous / next.
- Pagination uses the global control style and persists the selected
  page size with the saved settings (UI-12).

## UI-08 截断文本完整提示 (Full-text tooltips)

- Any text truncated with an ellipsis shows a hover tooltip / popover
  with the complete value. Applies to table cells, tree nodes, tabs,
  menus, and form fields.
- For icons, tooltips also explain the action.

## UI-09 行级自动刷新间隔 (Per-row auto-refresh interval)

- Platform-management tables expose "设置自动刷新时间间隔" in both the
  row action column and the row right-click menu.
- The interval is saved per list (or globally when the user chooses)
  and restored on next launch.
- Provide at least: off / 5 s / 10 s / 30 s / 60 s / custom. Start only
  one timer per list; a refresh in progress must not start a duplicate.

## UI-10 主题中心与下载地址 (Theme center and download URL)

- Ship at least 3 built-in themes.
- The theme center shows the source URL / download address for every
  online theme; a theme without an address is not shown as installable.
- "刷新" fetches from the online theme library / 在线主题库. Handle timeout / network
  failure with a visible error, a retry action, and a cached result.
- Download button states: "下载" -> "下载中..." -> "应用". After the
  download completes the same button becomes "应用"; do not show
  duplicate install / apply options.
- Applied theme is persisted (UI-12).
- Suggested built-in themes: `codex-dark` (default), `system`, `light`,
  plus a high-contrast variant when accessibility is needed.
- Theme library refresh uses a manifest contract so every framework can
  implement it identically (see below).

Useful online theme libraries (validate availability before wiring into
the app):

| Source | URL |
|---|---|
| Fluent 2 design system | https://fluent2.microsoft.design/ |
| Microsoft WinUI color and theme docs | https://learn.microsoft.com/windows/apps/design/style/color |
| QDarkStyleSheet (Qt / PySide6) | https://github.com/ColinDuquesnoy/QDarkStyleSheet |
| Catppuccin (cross-platform palettes) | https://github.com/catppuccin/catppuccin |
| Dracula (cross-platform palettes) | https://github.com/dracula/dracula-theme |
| Nord (cross-platform palettes) | https://github.com/arcticicestudio/nord |
| Material Theme Builder | https://m3.material.io/theme-builder |
| adw-gtk3 (GTK) | https://github.com/lassekongo83/adw-gtk3 |

### 主题库刷新契约 (Theme library refresh contract)

```json
{
  "version": 1,
  "source": "https://example.com/themes",
  "updated_at": "2026-08-08T00:00:00Z",
  "themes": [
    {
      "id": "catppuccin",
      "name": "Catppuccin",
      "url": "https://github.com/catppuccin/catppuccin",
      "preview": "https://example.com/catppuccin.png",
      "colors": {
        "bg": "#1e1e2e",
        "text": "#cdd6f4",
        "accent": "#89b4fa"
      }
    }
  ]
}
```

Rules:
- `id` is the dedupe key; duplicate ids are ignored.
- `url` must be shown in the theme center and is the download address.
- Invalid entries (missing `id`, `name`, or `url`) are not displayed.
- Refresh timeout and failure are surfaced; the previous cached list
  remains usable.

## UI-11 选项去重 (No duplicate options)

- Menus, dropdowns, filters, theme lists, and edit-form selectors never
  contain duplicate labels. Build options from one canonical source and
  de-duplicate by id + label.
- Deduplicate imported / refreshed theme entries before display.

## UI-12 配置持久化 (Settings persistence)

- Save and restore: theme, accent, layout, column widths / visibility,
  page size, auto-refresh intervals, window size / position, language,
  and active filters.
- Save on user action or immediately after a setting changes; the app
  must reopen with the saved configuration.
- Corrupt or missing config falls back to defaults with a visible error;
  schema migration is supported between versions.

## UI-13 日志中心 (Log center)

- Left navigation includes a log entry / column.
- Log center lists all success and failure logs with level, time,
  source, and summary.
- Each failure log opens a detail view: what failed, why it failed,
  and the suggested fix / next step.
- Logs persist and rotate; users can copy / export a failure detail.

## UI-14 语义色 (Semantic colors)

- danger = red, warning = orange / amber, success = green,
  info = blue. Use the same tokens in tables, dialogs, logs, and badges.
- Never invent a second red or second orange outside the token set.

## UI-15 表单示例 (Form examples and defaults)

- Edit forms, search controls, pagination selectors, and editors show
  sensible default values and example placeholders (for example
  `192.168.1.1`, `3000`, `2026-08-08`).
- Example text uses placeholder style, not real data, and is localized.

## UI-16 滚动条与图标 (Scrollbars and icons)

- Left navigation and right content both show scrollbars when content
  overflows.
- Scrollbars are visibly styled (thumb, track, hover state) and match
  the theme; they are not transparent or background-colored.
- Nav icons must always render; a collapsed / overflowed menu must not
  hide or drop icons.

## UI-17 提示信息分行 (Hint placement)

- Table list hints / status messages are not placed on the same line as
  the search bar.
- Long hints wrap to the next line; vertical overflow adds a scrollbar.

## UI-18 重型桌面端界面 (Heavy desktop UI, not web-styled)

- The app must look and behave like a native desktop application, not a
  website opened in a window; 不能 Web 化.
- Required desktop shell elements: desktop window frame / title bar,
  menu bar or equivalent desktop navigation, toolbar, status bar, data
  grid / list / tree, right-click menus, modal dialogs, keyboard
  shortcuts, column resize / reorder, and splitter or docked panels.
- Dense, information-first layout: compact rows, visible columns,
  stable toolbar heights, scrollable content. Avoid web-style
  marketing layouts: oversized hero headers, floating rounded cards,
  card-in-card, centered landing content, pill-only navigation,
  browser-like top navigation, infinite scroll, and mobile
  hamburger-only navigation.
- Web-based frameworks (Tauri / Electron / Wails / Neutralino) must
  still render a desktop shell: desktop window, dense management UI,
  right-click menus, status bar, and keyboard shortcuts; do not ship a
  website in a browser window.
- The first screen is the working UI (tables / tools), never a web
  landing or intro page.

### Heavy desktop data / performance rules

- Long lists and grids must be virtualized or paged, never bound to the
  full dataset at once: WPF `DataGrid` / `VirtualizingStackPanel`, WinUI
  3 `ItemsRepeater` / `ListView` + incremental loading, Qt
  `QAbstractItemModel` + `canFetchMore` / `fetchMore`, PySide6
  `QAbstractTableModel` + lazy fetch, tkinter `ttk.Treeview` + pagination,
  and virtual-list components when the UI is web-based.
- Search, filtering, sorting, and aggregation run on the data layer or a
  background worker; the UI thread only renders the visible page or
  viewport. Debounce search input and reuse the bounded worker pool from
  `references/threading_playbook.md`.
- Keep the app layered for long-term maintenance: UI / view-model /
  service / data access. .NET WPF / WinUI uses MVVM plus dependency
  injection; other frameworks use the same separation with their native
  patterns.
- Every heavy desktop build records cold start, idle memory, click-to-
  feedback latency, and a 100k-row (or equivalent) scroll/render test in
  Step 6; regressions are fixed before release, not after.

## UI-19 内置依赖中心 (Built-in dependency center)

- Every shipped app that needs an external runtime (ffmpeg / ffprobe,
  tesseract, ImageMagick, Playwright Chromium, aria2, 7z, etc.) manages
  that runtime inside the app; recipients never install it globally.
- After development, every runtime dependency is recorded in a dependency
  manifest (`dependencies.json`) and displayed in the dependency center
  menu: name, version, status, install path. The user does nothing except
  click `安装依赖` / `修复` / `更新`.
- The dependency center also shows plain-language help for every entry:
  what the dependency is for, where it will be installed, and the exact
  manual download / install steps (download URL, target directory, and
  restart behavior) for users who choose not to use the automatic button.
- Every dependency entry carries an official website URL (`homepage`); the UI
  renders it as a clickable link so the user can open the official page
  directly in the system's default external browser. The URL comes from
  each project's dependency manifest (`dependencies.json`) only;
  application code must not hard-code any dependency name or URL because
  every project has different dependencies.
- App-managed runtime directory, no admin required for portable
  dependencies: `%LOCALAPPDATA%\<AppName>\runtime` (Windows),
  `~/Library/Application Support/<AppName>/runtime` (macOS),
  `~/.local/share/<AppName>/runtime` (Linux).
- The UI shows a dependency center / status row with one entry per
  dependency: name, version, installed path, status
  (installed / missing / updating / failed), and one-click actions
  `安装依赖` / `修复` / `更新`.
- Clicking install starts a background worker only; the UI thread never
  blocks. Progress is real-time: percent, downloaded / total bytes,
  speed, ETA, stage, and current dependency.
- After the click the flow is fully automatic: parallel chunked
  download with resume, checksum verification, safe extraction,
  app-local path configuration, and status refresh. No terminal
  commands, no manual PATH editing, no browser download page, no
  interactive prompts.
- Slow or large downloads automatically use chunked concurrent download
  with resume/retry; the UI keeps showing bytes, speed, ETA, stage, and
  current dependency until every item is ready or a failure is logged.
- The app never auto-installs silently on launch. Startup only checks
  status and shows the install button; install requires the explicit
  user click.
- Reuse a local download cache and already-installed binaries; support
  retry / resume / repair when a dependency is missing, corrupt, or
  version-outdated.
- The app uses the app-local binary path directly (for example the
  ffmpeg path passed to the conversion engine), never relying on the
  recipient's system PATH.
- Optional Python modules follow the same rule with
  `scripts/lazy_python_dependency.py`: checked only on first use, installed
  into `%LOCALAPPDATA%\<AppName>\runtime\py-deps` with `pip --target` in
  source mode, and bundled at build time via
  `scripts/build_python.ps1 -InstallDeps` for frozen EXEs so recipients
  never run pip or download anything themselves.
- Failure goes to the log center (UI-13) with the exact reason and a
  suggested fix; the install / repair button remains available for
  retry.

## Acceptance checklist

- [ ] UI-01 one token source; Codex-like default when no theme specified
- [ ] UI-02 controls / menus / dialogs / dropdowns share one style
- [ ] UI-03 contrast passes 4.5:1 / 3:1 and no invisible buttons
- [ ] UI-04 alignment consistent; overflow uses scrollbar or wrap
- [ ] UI-05 one table per page; second table opens another page
- [ ] UI-06 no duplicate page title when nav shows it
- [ ] UI-07 bottom pagination on management lists
- [ ] UI-08 ellipsized text has full-value hover tooltip
- [ ] UI-09 row actions + context menu include auto-refresh interval
- [ ] UI-10 3+ built-in themes, online library + URL, refresh, button becomes 应用
- [ ] UI-11 no duplicate options anywhere
- [ ] UI-12 saved config restored on next launch
- [ ] UI-13 log center lists success/failure and shows reason + fix
- [ ] UI-14 danger red / warning orange / success green / info blue
- [ ] UI-15 forms provide examples / defaults
- [ ] UI-16 visible themed scrollbars; icons always shown
- [ ] UI-17 table hints on a separate line from search
- [ ] UI-18 heavy desktop shell; no web-style layout or web landing
  first screen
- [ ] UI-19 one-click dependency center downloads into app-local
  runtime with live bytes / speed / ETA, no manual input, no global
  install, and retry / repair on failure
- [ ] UI-19 dependency center menu lists every runtime dependency from
  the manifest; the user only clicks `安装依赖` and the app finishes with
  chunked / resumable download, verification, extraction, and status refresh
- [ ] Every list / table page has a loading progress bar; it appears while
  data loads and reflects 0-100% when the job emits progress
- [ ] Packaged EXE shows a startup animation + progress bar before the
  main window; splash hides only after initialization finishes
