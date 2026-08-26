# Win32 recipes

Common Win32 patterns that desktop apps need. Each recipe is language-neutral;
see `scripts/` for the implementation in Python (ctypes), C# (P/Invoke), and C.

---

## R1: SendInput (hardware-level keyboard input)

See `scripts/sendinput_*.py|cs|c` for keyboard implementations. The
Python Windows template also includes `move_mouse` / `click` / `scroll`;
the other language templates are keyboard-only.

Anti-cheat safety:
- Do NOT use `PostMessage(hwnd, WM_KEYDOWN, ...)`. PostMessage inserts the
  message into the target's queue; the target decides whether to act. Many
  games and anti-cheat libraries filter these.
- Do NOT use `SendMessage`. Same problem; even worse because synchronous.
- Do NOT write to game memory. This is the easiest detection vector.
- Use `SendInput` because it injects at the kernel-level input stack,
  bypassing most message filters.

Timing:
- 30-80 ms hold for a single key.
- 50-150 ms jitter between events when targeting a game. Templates
  randomize this range by default; pass an explicit positive `jitterMs`
  value to force a fixed delay.
- For combos, hold modifiers down 50-100 ms before the trigger and release
  50-100 ms after.

Foreground requirement:
- `SendInput` only delivers to the foreground window on modern Windows
  (the InputSynthesisProtectionLevel restriction). Use:
  ```c
  ShowWindow(hwnd, SW_RESTORE);
  SetForegroundWindow(hwnd);
  ```
  before each `SendInput` call. If the user wants unattended input, look at
  `SendInput` with `INPUT_HARDWARE` (not always available) or use a kernel
  driver (only for legitimate accessibility/research uses).

---

## R2: EnumWindows with timeout

`EnumWindows` invokes a callback for every top-level window. An owner-drawn
window can hang the callback for seconds. Always run with a timeout:

```c
// pseudocode
DWORD tid;
HANDLE t = CreateThread(NULL, 0, enum_worker, &ctx, 0, &tid);
WaitForSingleObject(t, 3000);    // 3 s
if (WAIT_TIMEOUT == WaitForSingleObject(t, 0)) {
    ctx.done = TRUE;             // tell callback to bail
    WaitForSingleObject(t, 100);
}
CloseHandle(t);
```

In Python, use `threading.Thread.join(timeout=3)` (see `scripts/window_enum_python.py`).

In C#, run `EnumWindows` inside a `Thread` and `await Task.Delay` until it
exits or the timeout expires (see `scripts/window_enum_dotnet.cs`).

---

## R3: Window text and class name

```c
int len = GetWindowTextLengthW(hwnd);
WCHAR *buf = malloc((len + 1) * sizeof(WCHAR));
GetWindowTextW(hwnd, buf, len + 1);
// use buf
free(buf);

WCHAR cls[256];
GetClassNameW(hwnd, cls, 256);
```

In C# the StringBuilder pattern is faster for repeated calls; in Python the
ctypes create_unicode_buffer pattern is fast enough.

---

## R4: Window always-on-top and click-through

```c
// always-on-top
SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);

// click-through (for overlay UIs that should not block input to underlying apps)
LONG ex = GetWindowLong(hwnd, GWL_EXSTYLE);
ex |= WS_EX_TRANSPARENT | WS_EX_LAYERED;
SetWindowLong(hwnd, GWL_EXSTYLE, ex);
```

Caveat: an always-on-top click-through window is also where anti-cheat looks
first for overlay-based bots. Use only for legitimate accessibility overlays.

---

## R5: Global hotkeys

```c
RegisterHotKey(hwnd, HOTKEY_ID, MOD_CONTROL | MOD_SHIFT, VK_F1);
// in WndProc:
case WM_HOTKEY:
    if (wParam == HOTKEY_ID) { /* Ctrl+Shift+F1 pressed */ }
    break;
```

In WPF / WinUI 3, use `HwndSource.AddHook` + `WM_HOTKEY`, or
`Microsoft.UI.Input.InputKeyboardSource` for WinUI 3.

---

## R6: Registry read / write

```c
RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\MyApp", 0, KEY_READ, &hkey);
DWORD size = MAX_PATH;
WCHAR value[MAX_PATH];
RegQueryValueExW(hkey, L"LastUser", NULL, NULL, (LPBYTE)value, &size);
RegCloseKey(hkey);
```

In .NET, prefer `Microsoft.Win32.Registry` over P/Invoke. In Python, use
`winreg` stdlib module.

---

## R7: System tray icon

```c
NOTIFYICONDATAW nid = {0};
nid.cbSize = sizeof(nid);
nid.hWnd = hwnd;
nid.uID = 1;
nid.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
nid.uCallbackMessage = WM_TRAYICON;
nid.hIcon = LoadIconW(hInst, MAKEINTRESOURCEW(IDI_APP));
wcscpy_s(nid.szTip, L"MyApp");
Shell_NotifyIconW(NIM_ADD, &nid);
```

In .NET, use `Hardcodet.NotifyIcon.Wpf` (WPF) or `H.NotifyIcon.WinUI` (WinUI).
In Python, use `pystray` or `infi.systray`.

---

## R8: Single-instance enforcement

```c
HANDLE m = CreateMutexW(NULL, TRUE, L"Local\\MyAppSingleton");
if (GetLastError() == ERROR_ALREADY_EXISTS) {
    // Another instance is running; bring it to foreground
    HWND existing = FindWindowW(L"MyAppClass", NULL);
    SetForegroundWindow(existing);
    return 0;
}
```

In .NET, use `Mutex` or `System.Threading.Semaphore`. In Python, `fcntl`-like
Windows behavior via `msvcrt` is awkward; use the same `CreateMutex` pattern
via ctypes.

---

## R9: File system watcher

```c
HANDLE h = FindFirstChangeNotificationW(L"C:\\Watch\\", TRUE,
                                         FILE_NOTIFY_CHANGE_FILE_NAME, &dw);
while (h != INVALID_HANDLE_VALUE) {
    WaitForSingleObject(h, INFINITE);
    // filesystem changed
    FindNextChangeNotification(h);
}
FindCloseChangeNotification(h);
```

In .NET, use `System.IO.FileSystemWatcher`. In Python, `watchdog` library.

---

## R10: ETW (Event Tracing for Windows)

For high-performance tracing, ETW is the OS-native answer. Use
`TraceLoggingProvider.h` macros in C++ or `Microsoft.Diagnostics.Tracing`
in .NET. Tools: `PerfView`, `WPA`, `xperf`.

---

## R11: UAC elevation

```c
ShellExecuteExW(&sei);
// with sei.lpVerb = L"runas" to trigger UAC prompt
```

In .NET, `Process.Start(new ProcessStartInfo { Verb = "runas", ... })`.
In Python, `subprocess.run(['something'], shell=True)` with the same verb.

Never silently elevate. UAC prompts exist for a reason; respect them.

---

## R12: Windows services

For a long-running background service:
1. Create a Windows Service project in .NET (`dotnet new worker --name MyService`).
2. Install with `sc create MyService binPath= C:\Path\To\MyService.exe`.
3. Start with `sc start MyService`.
4. Configure recovery with `sc failure MyService reset= 30 actions= restart/5000`.

For Python, use `pywin32`'s `win32serviceutil`. For C++, use the
`SvcMain` / `ServiceMain` template from MSDN.

---

## R13: Accessibility automation

If you must drive another app's UI, prefer the supported accessibility
APIs over SendInput or memory write. They are detectable by the target
app (it can refuse), but they are the legitimate path for productivity
apps and accessibility tools.

Priority order (most legitimate first):

1. **UI Automation (UIA)** -- `UIAutomationCore.dll`. Supported, accessibility-
   grade, exposes a tree of `AutomationElement`s with Name /
   `AutomationId` / `ControlType`. Works in .NET via
   `UIAutomationClient` / `UIAutomationProvider`, and in Python via
   `scripts/accessibility_uia.py` (comtypes) or `pywinauto`.
2. **MSAA** -- `oleacc.dll`. Legacy; still works for older apps. Use
   `scripts/accessibility_msaa.py` for a no-deps ctypes smoke check, or
   `pywinauto` for full IAccessible dispatch.
3. **SendInput** -- drives the OS input stack directly (see R1). Works
   regardless of what the target exposes; detectable but not refusable.
4. **Memory write** -- last resort. Easily detected by every modern
   anti-cheat.

For game anti-cheat, UIA and MSAA are usually blocked; SendInput is
the only supported path. See `scripts/sendinput_python.py`.

### When to pick what

| Target                              | Best choice                                |
|-------------------------------------|--------------------------------------------|
| Office, browsers, LOB tools         | UIA (full read + invoke)                   |
| Legacy app without UIA              | MSAA via `accessibility_msaa.py`           |
| Any Win32 app (input only)          | SendInput (see R1)                         |
| Game with anti-cheat                | SendInput (UIA / MSAA blocked)             |
| Accessibility / NVDA-style reader   | UIA                                        |
| UI testing (WinAppDriver, FlaUI)    | UIA + InvokePattern                        |
