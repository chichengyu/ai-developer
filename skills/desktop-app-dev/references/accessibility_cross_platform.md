# Cross-platform accessibility (deep dive)

Reading and driving the UI of another application for testing or automation
is doable on every desktop OS, but the API surface differs wildly. This
reference pulls together what works on each platform and links to the
canonical template in `scripts/`.

---

## Windows

### UIA (UI Automation) -- the modern path

`scripts/accessibility_uia.py` -- the canonical wrapper. UIA is the
Windows-supplied COM API for accessibility. It is the right choice for any
modern app (Win32, WPF, WinUI, WinForms, Office, browsers, Electron, Tauri).

Strengths:

- Tree walking with `IUIAutomationElement.FindAll` + filter conditions.
- Element properties: `Name`, `AutomationId`, `ClassName`, `ControlType`,
  `BoundingRectangle`, `Value`, `IsEnabled`, `IsOffscreen`.
- Patterns: `InvokePattern`, `ValuePattern`, `SelectionItemPattern`,
  `TextPattern`, `ScrollPattern`. Each one gives you the right action
  (click, set text, select, read text, scroll) without resorting to
  SendInput.

Pitfalls:

- UIA is COM and STA-only. Pump messages on the UI thread before calling.
- Some apps (older Win32, certain controls) have broken UIA trees. Fall
  back to MSAA in that case.
- WebView2 / Edge / Chrome use UIA bridge; `ControlType` is `Document`
  and the inner DOM is not directly traversable -- use the web frontend
  test framework instead.

### MSAA (Microsoft Active Accessibility) -- the legacy fallback

`scripts/accessibility_msaa.py` -- for legacy apps where UIA returns
empty / stale trees. MSAA uses `IAccessible` COM interfaces and works on
Win32, MFC, and some older WPF controls.

When to use MSAA over UIA:

- Win32 app where UIA tree is empty.
- Self-elevation required (UIA blocks in some elevated contexts).
- Cross-process accessibility for Office / IE legacy.

### SendInput -- the hardware-level fallback

`scripts/sendinput_python.py` (and the 10-language set). When neither UIA
nor MSAA works (game clients, anti-cheat-blocked apps, very old Win32
tools), SendInput bypasses the UI layer entirely and pushes events into
the input queue. The recipient app sees them as real keyboard events; the
Python Windows template also ships mouse helpers.

Use SendInput as a last resort -- it cannot read state, it can only
write. Pair with UIA / MSAA for reading.

### Live region / screen reader

For the *recipient* app (the one you are shipping), expose UIA
`LiveSetting` properties on dynamic content regions. WPF supports this
via `AutomationProperties.LiveSetting`. WinForms needs manual provider
implementation.

---

## macOS

### AppleScript / System Events -- the canonical path

macOS does not expose a UIA-equivalent public API. The supported path is
**System Events** via AppleScript:

```applescript
tell application "System Events"
    tell process "Safari"
        click button "Reload" of window 1
    end tell
end tell
```

Strengths:

- Native, supported, no permission prompts (when granted via Accessibility
  panel).
- Stable across OS versions.

Pitfalls:

- The calling app needs Accessibility permission in
  System Settings -> Privacy & Security -> Accessibility. Without it,
  AppleScript silently does nothing.
- Speed is slow (~200 ms per event). For tight loops, batch via
  `osascript -e`.

### Accessibility API (private)

The `AXUIElement*` C API (ApplicationServices framework) is more powerful
than AppleScript but is technically private. Apple has not committed to
its stability. Use only when AppleScript is too slow and you have a
maintained shim.

### CGEventPost -- the hardware-level fallback

`scripts/sendinput_macos.py` (Quartz). Bypasses the UI layer entirely.
Same caveats as Windows SendInput: writes only, not reads.

---

## Linux

### AT-SPI2 (Assistive Technology Service Provider Interface) -- the
canonical path

DBus service at `org.a11y.atspi`. Tools:

- `at-spi2-core` (apt) provides the daemon.
- `python-pyatspi` (apt) gives Python bindings.

```python
import pyatspi
desktop = pyatspi.Registry.getDesktop(0)
for app in desktop:
    print(app.name, app.get_toolkit_name())
```

Strengths:

- Standard across GNOME, KDE, XFCE, MATE.
- Tree walking, role lookup, state queries, action invocation.

Pitfalls:

- Not all toolkits expose AT-SPI (some Qt apps need `QT_ACCESSIBILITY=1`).
- Wayland sessions may need `dbus-daemon` running with the right session
  bus.
- The X11 path is well-trodden; the Wayland path is still maturing in
  2026.

### uinput -- the hardware-level fallback

`scripts/sendinput_linux.py` (X11) for X11 sessions; raw uinput for
Wayland (kernel-level, requires a small `uinput` group permission).

---

## Decision tree

```
Need to read UI state?
├── Windows
│   ├── Modern app (WPF, WinUI, WinForms, web)        -> UIA
│   ├── Legacy / broken tree                          -> MSAA
│   └── Game client / anti-cheat                      -> SendInput (write only)
├── macOS
│   └── Any app                                       -> System Events (AppleScript)
└── Linux
    ├── GTK / Qt / Electron / Tauri (X11 or Wayland)  -> AT-SPI2
    └── None of the above                             -> uinput (kernel-level)

Need to write input?
├── Yes, by clicking / typing into a known control    -> UIA patterns (Win)
│                                                       System Events (mac)
│                                                       AT-SPI2 (Linux)
└── No clean path / the app blocks above              -> SendInput / CGEventPost / XTestFakeInputEvent
```

---

## Tooling recipes

### Windows: enumerate every clickable element on screen

```powershell
# requires scripts/accessibility_uia.py on PYTHONPATH
python -c "from accessibility_uia import enumerate_clickable; enumerate_clickable()"
```

### macOS: dump the frontmost app's element tree

```bash
osascript -e 'tell application "System Events" to get every UI element of front window of (first process whose frontmost is true)'
```

### Linux: list every AT-SPI accessible app

```bash
python -c "import pyatspi; [print(a.name) for a in pyatspi.Registry.getDesktop(0)]"
```

---

## When NOT to use accessibility APIs

- **Game clients with anti-cheat**: SendInput may be blocked; memory-write
  is bannable; UIA may be ignored. The "safe" path is to ask the user to
  click manually, or to operate outside the game (a companion app).
- **macOS apps without Accessibility permission**: the calling app will
  silently fail. Ask the user to grant permission in System Settings.
- **Linux Wayland without DBus session**: there is no per-element path.
  Fall back to uinput.

See `references/win32_recipes.md` R13 for the priority order on Windows.
