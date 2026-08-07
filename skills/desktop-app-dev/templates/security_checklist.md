# Security checklist (template)

Run this **before** every release. Every "must" item is a release blocker;
every "should" item is a documented deferral. Copy the list into the
release issue and tick each one.

---

## Input simulation (Category A only)

- [ ] **must**: Keystroke / mouse simulation uses `SendInput` (Win) /
  `CGEventPost` (mac) / `XTestFakeInputEvent` (X11) -- never `PostMessage`,
  `SendMessage`, `keybd_event`, memory write, or AHK scripts. Confirm by
  `grep`ing the source tree for `PostMessage` / `keybd_event`.
- [ ] **must**: Window enumeration runs in a worker thread with a 3 s
  timeout and a session cache. UI thread never blocks on EnumWindows.
- [ ] **must**: Before any input is sent, the target window is foregrounded
  via `SetForegroundWindow` + thread-input attach (Win) or
  `CGSConnection` (mac). No random input to a backgrounded window.
- [ ] **should**: Per-event jitter (30-80 ms hold, 50-150 ms between) is
  applied. Anti-cheat heuristics flag metronomic input.

## File system & paths

- [ ] **must**: All file paths go through `Path.Combine` / `os.path.join` /
  `pathlib.Path`. No string concatenation. Confirm by `grep`.
- [ ] **must**: Long-path aware (Windows): either enable `longPathAware`
  in the manifest or stay under 260 chars. See `templates/dpi_manifest.xml`
  for the `longPathAware` snippet.
- [ ] **must**: Non-ASCII paths work. Test with a folder named `测试-名前`
  and an EXE installed under it.
- [ ] **must**: File operations never run on the UI thread. A 50 MB file
  read on the UI thread freezes the window and triggers AV heuristics.

## Network

- [ ] **must**: `HttpClient` timeouts are explicit (default is 100 s, which
  is too long). Set `Timeout = TimeSpan.FromSeconds(30)` or less.
- [ ] **must**: TLS 1.2+ is enforced. `ServicePointManager.SecurityProtocol`
  is set or `HttpClientHandler` configured. No TLS 1.0 / 1.1 fallback.
- [ ] **must**: User-supplied URLs are validated against an allowlist
  before being passed to `Process.Start` or `WebView.Navigate`.
- [ ] **should**: Certificate pinning is used for any financial / health /
  auth endpoints. Default for production APIs.
- [ ] **should**: HTTP requests are retried with exponential backoff, not
  tight loops. Lock-up = DoS the upstream + your UX.

## Process & privilege

- [ ] **must**: The app does not require elevation unless absolutely
  necessary. If it does, the reason is documented in `requirements.md`.
- [ ] **must**: COM initialisation matches the threading model
  (STA vs MTA). Mis-matched COM throws `RPC_E_CHANGED_MODE` at runtime.
- [ ] **must**: No `Process.Start` with user-controlled strings without
  validation. Use a wrapper that disallows shell metacharacters.

## Code-signing & AV

- [ ] **must**: Release EXEs are code-signed. Unsigned Windows EXEs trigger
  SmartScreen "unknown publisher" warnings that look like malware to
  recipients.
- [ ] **must**: macOS app is notarized via `notarytool`. Otherwise
  Gatekeeper refuses to launch.
- [ ] **should**: Linux .deb is signed with `debsigs`. AppImage has no
  signing standard but should be distributed via HTTPS + checksum.
- [ ] **should**: AV false-positive notes are prepared (one-paragraph
  explanation of what the binary is, why it does X, contact email). Send
  to the recipient's IT in advance.

## Logging & data

- [ ] **must**: PII (emails, account names, tokens) is never written to
  logs without an explicit `--verbose-pii` flag. Default is redacted.
- [ ] **must**: Log files are written to a user-writable directory
  (`%LOCALAPPDATA%` / `~/Library/Logs` / `~/.local/share`), not next to
  the EXE (which may be in `Program Files` and require admin to write).
- [ ] **must**: Crash dumps do not contain full memory contents. Use
  `MiniDumpNormal` or `MiniDumpWithThreadInfo`, not `MiniDumpWithFullMemory`.

## Dependencies

- [ ] **must**: No NuGet / npm / PyPI package is added without a license
  audit. `pip-licenses`, `npm ls --long`, or `dotnet-license` per project.
- [ ] **must**: All dependencies are pinned to a specific version (no
  floating ranges). Reproducible builds require it.
- [ ] **should**: Run `npm audit` / `pip-audit` / `dotnet list package
  --vulnerable` before every release. Document any deferred CVE.

## Persistence

- [ ] **must**: Settings file uses an explicit schema. Migration code is
  present for v0 -> v1. A corrupt settings file does not crash on launch;
  the app falls back to defaults and logs the failure.
- [ ] **must**: Database connections are pooled, not opened per-query.
  SQLite `journal_mode=WAL` is recommended for desktop apps.
- [ ] **must**: Auto-update checks verify the package signature before
  applying. Velopack does this by default; rolling your own does not.

## Common foot-guns (re-check before every release)

- [ ] No `dynamic` or `Activator.CreateInstance` over user-controlled types.
- [ ] No `Assembly.LoadFrom` with user-controlled paths.
- [ ] No `Process.Start("cmd.exe", "/c " + userInput)`.
- [ ] No `string.Format` / interpolation of user input into SQL.
- [ ] No hardcoded secrets, tokens, or test credentials in the source.
- [ ] No third-party analytics SDK that phones home without opt-in.

---

## See also

- `references/win32_recipes.md` -- 13 Win32 security patterns.
- `references/distribution_playbook.md` -- code-signing per platform.
- `references/restricted_network_playbook.md` -- when the build host has
  no internet, how to keep dependency chains auditable.