# examples/

Ten minimal runnable projects that demonstrate the skill's templates in
real (non-toy) contexts. They either consume the canonical scripts in
`../scripts/` by file link (`<Compile Include>` in .NET) or runtime
`sys.path` injection (Python), or demonstrate a standalone packaging path.

| Folder                | Framework    | Demonstrates                          |
|-----------------------|--------------|----------------------------------------|
| `wpf-threading/`      | C# / WPF 8   | `threading_wpf.cs` + dispatcher bridge |
| `winui3-threading/`   | C# / WinUI 3 | `threading_winui.cs` + DispatcherQueue |
| `tkinter-threading/`  | Python 3.12  | `threading_tkinter.py` + SendInput     |
| `pyside6-threading/`  | Python 3.12  | `threading_pyside6.py` (QThread+Signal)|
| `pyside6-management/` | Python 3.12  | `.ui` + left nav + loading + lazy deps + clean exit |
| `tauri-threading/`    | Rust + Web   | `threading_tauri.rs` + window.emit     |
| `msix-packaging/`     | C# / WPF + Windows App SDK | MSIX packaging pipeline |
| `nativeaot-winforms/` | C# / WinForms + NativeAOT | single-file NativeAOT EXE |
| `game-automation/`    | Python 3.12  | TLBB-style bot: window + SendInput + threading |
| `media-toolkit/`      | Python 3.12  | live-progress downloader + all-format converter |

For independent batch jobs, swap in the matching
`scripts/threading_pool_*` template (Python / C# / Tauri / Compose /
Electron) so the example gets aggregate progress, retry, and one
`cancel()`.

The two PySide6 examples are Python-only. Other languages do not install
PySide6 or use `lazy_python_dependency.py`; use their native UI files and
package managers instead.

## Why file-link / sys.path injection?

The skill's `scripts/` directory is the single source of truth. Every
example imports from it; nothing is duplicated. Bug fixes to the templates
automatically propagate to every example.

## Smoke test

```powershell
# tkinter (no extra deps)
python examples/tkinter-threading/app.py

# pyside6 (requires pip install PySide6)
pip install PySide6
python examples/pyside6-threading/app.py

# pyside6 management shell (.ui + loading + lazy deps + clean shutdown)
python examples/pyside6-management/app.py

# WPF (requires .NET 8 SDK)
cd examples/wpf-threading && dotnet run

# WinUI 3 (requires .NET 8 SDK + Windows App SDK)
cd examples/winui3-threading && dotnet build

# MSIX and NativeAOT packaging (see each folder's README)
cd examples/msix-packaging && powershell -File build_msix.ps1
cd examples/nativeaot-winforms && dotnet publish

# Tauri (requires Rust + tauri-cli)
cd examples/tauri-threading && cargo tauri dev

# Game automation (no extra deps)
python examples/game-automation/app/app.py

# Media toolkit (no extra deps; ffmpeg needed for media conversion)
python examples/media-toolkit/app.py
```

The tkinter, game-automation, and media-toolkit examples open a real
window on your desktop. The others require the matching framework
installed; their `README.md` documents the prereqs.
