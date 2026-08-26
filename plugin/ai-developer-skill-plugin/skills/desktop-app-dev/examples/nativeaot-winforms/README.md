# NativeAOT WinForms Demo

Minimal WinForms (.NET 8) app compiled with `<PublishAot>true</PublishAot>`.
Produces a single ~5 MB EXE that runs on a clean Windows machine **with no
.NET runtime installed**.

This is the right shape when:

- The recipient is non-technical and you want a portable binary, not an installer.
- Cold start matters (NativeAOT skips JIT, so the window paints in < 50 ms).
- The app is small (single window, a handful of controls).
- You want AV-friendly size to reduce false positives (smaller surface = fewer
  heuristic matches).

It is **not** the right shape when:

- You need WPF or WinUI 3 (neither is NativeAOT-compatible in .NET 8).
- You pull in reflection-heavy NuGet packages (Newtonsoft.Json, AutoMapper,
  MediatR, EF Core with lazy loading). Use a regular ReadyToRun publish instead.
- You need cross-platform ARM64 today (NativeAOT Windows is x64-only in .NET 8;
  arm64 lands in .NET 9).

## Run / build

```powershell
cd examples/nativeaot-winforms
powershell -ExecutionPolicy Bypass -File ..\..\scripts\build_dotnet_nativeaot.ps1 `
    -Project .\NativeAotWinFormsDemo.csproj
```

Output: `dist\NativeAotWinFormsDemo.exe` (~5 MB). Copy to a clean Windows
10/11 VM (or Windows Sandbox) with **no** .NET runtime installed and run.

## Size comparison

| Build mode                           | Output size  | Cold start | Notes                              |
|--------------------------------------|--------------|------------|------------------------------------|
| `dotnet publish` (framework-dependent)| ~150 KB     | ~250 ms    | needs runtime on target            |
| ReadyToRun self-contained            | ~30 MB       | ~150 ms    | JIT ahead-of-time, but still .NET   |
| NativeAOT self-contained             | ~5 MB        | < 50 ms    | no runtime, no JIT                 |

## When to choose NativeAOT vs Velopack vs MSIX

- **NativeAOT** -- single-file EXE, fastest start, smallest size, x64 only.
- **Velopack** -- installer + portable, automatic delta updates, multi-arch.
- **MSIX** -- Microsoft Store, deep Windows integration, per-user clean install.
- **WiX / NSIS** -- classic installers; choose when Store is not an option.

See `references/distribution_playbook.md` for the full matrix.

## AOT safety checklist

When converting an existing WinForms app to NativeAOT:

- [ ] Remove all `Assembly.LoadFrom`, `Activator.CreateInstance`, and reflection over types.
- [ ] Replace JSON.NET with `System.Text.Json` (source-gen compatible).
- [ ] Replace `ILogger` with `LoggerMessage` source generators if you use logging.
- [ ] Replace `Lazy<T>` and `ActivatorUtilities` with direct constructor calls.
- [ ] Set `<InvariantGlobalization>true</InvariantGlobalization>` if you do not need cultures.
- [ ] Run `dotnet publish` with `-p:PublishAot=true` and read the **IL trim warnings** -- every warning is a potential runtime crash under AOT.