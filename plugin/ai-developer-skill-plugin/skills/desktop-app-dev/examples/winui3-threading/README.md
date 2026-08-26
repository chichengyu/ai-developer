# WinUI 3 Threading Demo

Minimal WinUI 3 (.NET 8, Windows App SDK 1.5) app that uses
`scripts/threading_winui.cs` as a `<Compile Include>` link so the threading
template stays in one canonical place.

WinUI 3 (the modern Windows 11 Fluent UI toolkit) is structurally different
from WPF: there is **no** `Application.Current.Dispatcher`. Every UI-thread
touch must be posted through `Microsoft.UI.Dispatching.DispatcherQueue`.
The companion template `scripts/threading_winui.cs` enforces that contract.

## Run

```powershell
cd examples/winui3-threading
dotnet run -c Debug
```

## Build a self-contained unpackaged EXE

```powershell
powershell -ExecutionPolicy Bypass -File build_winui3.ps1 -Arch win-x64
```

Output: `dist\WinUIThreadingDemo.exe` plus the Windows App Runtime DLLs it
needs to run on a clean Win 10/11 VM.

## Build for Windows on ARM (Snapdragon X)

```powershell
powershell -ExecutionPolicy Bypass -File build_winui3.ps1 -Arch win-arm64
```

WinUI 3 has first-class `win-arm64` support since Windows App SDK 1.4.

## Why not MSIX?

This example ships **unpackaged** (`WindowsPackageType=None`) because:

1. The recipients are non-technical users who double-click an EXE.
2. No Microsoft Store / Partner Center account is needed.
3. Sideloading warnings and `Add-AppxPackage` steps are avoided.

If you need Store distribution or `Package.Identity` for deep Windows
integration, see `examples/msix-packaging/` and flip the csproj to
`<WindowsPackageType>MSIX</WindowsPackageType>`.