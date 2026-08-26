# Desktop UI playbook (桌面界面能力)

A deep-dive for building dense, native-feeling desktop interfaces that
survive real users: theme systems, layout, data grids, dialogs, keyboard
navigation, accessibility, state management, and UI performance. Read it
with `references/ui_hard_requirements.md` (UI-01..UI-19) and
`references/heavy_desktop_playbook.md` for data-heavy apps.

## 1. UI foundation

### 1.1 Design tokens

- One token source drives every view: colors, typography, spacing, radii,
  dimensions, elevation, motion, and semantic states.
- Copy `templates/desktop_ui_tokens.json` into the app and map it to the
  framework resource system: WPF / WinUI `ResourceDictionary`, Qt QSS /
  QML constants, PySide6 `QPalette` + QSS, CSS variables for web-based
  shells.
- If the user has no brand, use the Codex-like default palette in
  `references/ui_hard_requirements.md`.
- Never hard-code a color, font size, or spacing value in a view.

### 1.2 Control catalog

Use the native control set first; add custom controls only when native
behavior is missing:

| Area | Required desktop controls |
|---|---|
| Shell | menu bar / toolbar / status bar, docked panels, tab strip |
| Data | data grid, tree, list, pagination, property grid |
| Input | text box, combo box, date picker, file picker, search box |
| Feedback | modal dialog, toast, progress, log center, tooltip |
| Selection | check box, radio, toggle, multi-select |

Controls must have stable dimensions and hit targets; text must never
overflow or overlap. Cards stay at 8px radius or less, and cards are only
for repeated items, modals, and framed tools, never page sections.

### 1.3 Layout system

- Use a grid / dock / panel layout with stable toolbar, row, and status
  bar heights.
- The minimum window is 800x600; resizing down adds scrollbars, never
  clipped controls.
- Long tables use horizontal + vertical scrolling with frozen headers.
- Splitters, column widths, and panel states persist across launches.
- No web-style hero, centered landing, floating card clusters, or
  card-in-card layouts in a desktop app.

## 2. Theming

### 2.1 Theme registry

- Register light, dark, and high-contrast themes from one token source.
- Detect the OS theme at startup and react to OS changes.
- Runtime theme switching updates every window without restart.
- Theme center shows installed themes, a download URL, refresh, and an
  `应用` action (UI-10).
- Persist the selected theme and restore it on next launch (UI-12).

### 2.2 Semantic colors

- Danger red, warning orange, success green, and info blue are the same
  tokens everywhere (UI-14).
- Text and background contrast passes 4.5:1 for body text and 3:1 for
  large text / UI components (UI-03).
- Focus, selection, hover, pressed, disabled, and error states all come
  from tokens, not one-off colors.

### 2.3 Framework theming notes

- WPF / WinUI: `ResourceDictionary` + `DynamicResource`; never `StaticResource`
  for theme colors that switch at runtime.
- Qt: QSS + `QPalette`; keep colors in a central style sheet.
- PySide6: `QPalette` + QSS; regenerate the palette on theme change.
- Tauri / Electron: CSS variables + a theme manager; no hard-coded hex in
  components.

## 3. Data-rich controls

### 3.1 Data grid

- One table per page (UI-05); a second table opens another page.
- Columns resize, reorder, sort, and persist width / order.
- Rows use compact density, stable row height, and bottom pagination
  (UI-07).
- Ellipsized cells show the full value in a tooltip (UI-08).
- Row actions and context menus include auto-refresh interval (UI-09).
- Grids with 100k+ rows use virtualization or paging (see heavy desktop
  playbook).

### 3.2 Tree

- Lazy-load child nodes; never load the whole tree up front.
- Keep selection, expansion state, and scroll position in the ViewModel,
  not only in the control.
- Checkboxes and drag-drop are opt-in and must preserve undoable state.

### 3.3 Forms

- Labels align consistently; validation appears next to the field.
- Provide examples and sensible defaults in placeholders (UI-15).
- Disable the submit action while invalid; show one clear error at a time
  plus a summary in the log center.
- Escape and Enter follow the platform convention.

### 3.4 Search and filters

- Search bar and table hints are on separate lines (UI-17).
- Debounce search 250-400 ms; cancel stale results.
- Filters run in the data layer; the UI only renders the result page.

## 4. Interaction

### 4.1 Keyboard

- Every command has a keyboard path: menu, toolbar, context menu, or
  shortcut.
- Tab order follows the visual flow; Enter activates, Esc cancels.
- Mnemonics and tooltips exist for icon-only buttons.
- Focus is always visible after keyboard navigation.

### 4.2 Context menus and commands

- Row context menu mirrors the row action bar; never a menu with only one
  item.
- Commands are wired through ViewModel commands / actions, not direct
  control event handlers.
- Long-running commands show progress and cancellation, never freeze the
  window.

### 4.3 Dialogs

- Modal dialogs own their task: confirm, choose file, settings, about.
- Dialogs are centered on the owner, remember size, and use the same
  theme.
- Destructive actions require confirmation and show the consequence.

## 5. State management

Every page or workspace has explicit states:

| State | UI requirement |
|---|---|
| Loading | skeleton / progress, no blank page |
| Empty | explanation + primary action |
| Error | reason + suggested fix in log center (UI-13) |
| Disabled | controls disabled with tooltip |
| Saving | busy state, no double submit |
| Dirty | unsaved changes indicator |

Layout, columns, filters, and active page persist (UI-12). Undo / redo is
required wherever the app edits user data.

## 6. Accessibility

- Screen readers get names and roles through UIA / MSAA / AT-SPI /
  AppleScript; deep-dive: `references/accessibility_cross_platform.md`.
- Full keyboard-only operation: every action reachable without mouse.
- High-contrast theme is tested, not bolted on.
- Focus order is deterministic; dialogs trap focus while open.

## 7. UI performance

- Grids and lists are virtualized or paged; never render 100k rows.
- Batch model updates and throttle progress; the UI thread only renders.
- Reuse control templates; avoid per-cell bindings for large tables.
- Keep theme switching cheap: change tokens, not control instances.
- Measure scroll latency, resize latency, and theme-switch latency in
  Step 6.

## 8. UI acceptance

Run `references/ui_hard_requirements.md` UI-01..UI-19 plus
`templates/desktop_ui_checklist.md`. Capture screenshots at 800x600 and
1920x1080 in light, dark, and high-contrast modes; verify no overlap,
no clipped text, and no web-style layout.

## Mapping to existing skill assets

- UI hard requirements: `references/ui_hard_requirements.md`
- Accessibility: `references/accessibility_cross_platform.md`
- Heavy data grids: `references/heavy_desktop_playbook.md`
- Threading / UI bridge: `references/threading_playbook.md`
- Token template: `templates/desktop_ui_tokens.json`
- Acceptance checklist: `templates/desktop_ui_checklist.md`
- DPI manifest: `templates/dpi_manifest.xml`
