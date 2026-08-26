# NativeAOT optimization (deep dive)

When you want a single-file Windows EXE that is small, starts fast, and
needs **no** .NET runtime on the target machine, NativeAOT is the answer.

This reference covers what NativeAOT is, when to use it, what it costs,
and how to migrate an existing .NET 8 WinForms app to it.

---

## What NativeAOT actually is

NativeAOT (officially: "Native AOT", `<PublishAot>true</PublishAot>`) is
the .NET 8+ path that compiles your IL directly to a native Windows
binary ahead of time. There is no JIT at runtime, no framework lookup,
no `dotnet.exe` host. The output is one EXE plus (optionally) a few
side-by-side DLLs you control via `-p:PublishSingleFile=...`.

A minimal "Hello, world" WinForms app under NativeAOT produces:

```
NativeAotWinFormsDemo.exe    ~5 MB
```

The same app as a ReadyToRun self-contained WPF build:

```
MyApp.exe          ~150 KB
*.dll (BCL)        ~60 MB total
```

The size win is real, and so is the cold-start win: ~50 ms vs ~150 ms.

---

## When to use NativeAOT

| Use it when...                                              | Avoid it when...                                       |
|-------------------------------------------------------------|--------------------------------------------------------|
| You ship a portable EXE to non-technical users.             | You need WPF or WinUI 3 (neither supports AOT in .NET 8). |
| Cold start is a hard constraint (< 100 ms).                 | You depend on reflection-heavy libraries.              |
| The UI is small enough to build with WinForms.               | You need arm64 today (lands in .NET 9).                |
| You want fewer AV false positives (smaller surface).        | You need a Microsoft Store listing (NativeAOT is unpackaged by design). |
| You want no runtime install story.                          | You need `<PublishAot>` + `dotnet test` in CI without the matching SDK. |

---

## The four flags that make it work

Add these to the csproj (the `examples/nativeaot-winforms/NativeAotWinFormsDemo.csproj`
is the canonical example):

```xml
<PropertyGroup>
  <OutputType>WinExe</OutputType>
  <TargetFramework>net8.0-windows</TargetFramework>
  <RuntimeIdentifier>win-x64</RuntimeIdentifier>
  <PlatformTarget>x64</PlatformTarget>
  <UseWindowsForms>true</UseWindowsForms>

  <!-- The four AOT flags -->
  <PublishAot>true</PublishAot>
  <IsAotCompatible>true</IsAotCompatible>
  <OptimizationPreference>Size</OptimizationPreference>
  <InvariantGlobalization>true</InvariantGlobalization>
</PropertyGroup>
```

What each one does:

- `PublishAot` -- turns on the AOT compiler (the ILCompiler from the dotnet/runtime repo).
- `IsAotCompatible` -- opt the assembly into AOT-trim-safe analysis. Without it, the trimmer treats the assembly as opaque and may strip needed code.
- `OptimizationPreference=Size` -- favours smaller binary over faster code. Remove if you want speed.
- `InvariantGlobalization` -- drops the ~2-3 MB of culture data. Keep only if your app needs `CultureInfo` other than invariant.

---

## AOT safety: what to remove from your existing app

The trimmer is conservative: any code path it cannot prove safe is
removed, and reflection that survives is rewritten to throw at runtime.

### Replace these libraries

| Library                 | AOT-safe replacement                                              |
|-------------------------|-------------------------------------------------------------------|
| `Newtonsoft.Json`       | `System.Text.Json` (with `JsonSerializerContext` source gen)      |
| `AutoMapper`            | Manual `Map` methods or `Mapperly` (source-gen)                   |
| `MediatR`               | Direct method calls                                               |
| `EF Core` (lazy load)   | Projections, `AsNoTracking`, no navigation property lazy load     |
| `Serilog` (default)     | `LoggerMessage` source generators + structured logging           |
| `NLog` (default)        | `LoggerMessage` source generators                                 |
| `FluentValidation`      | `MiniValidator` or hand-written `if` checks                       |
| `Refit`                 | `HttpClient` + manual DTOs                                        |
| `Dapper`                | Works, but only if you use raw SQL strings (no reflection over types) |

### Replace these patterns

| Anti-pattern                                  | AOT-safe alternative                              |
|-----------------------------------------------|---------------------------------------------------|
| `Activator.CreateInstance(t)`                 | Direct `new` (or DI with compile-time graph)      |
| `Type.GetProperties()` then read attributes   | Source generators, or hard-coded mapping          |
| `Assembly.LoadFrom(...)`                      | `<Reference>` + direct `new`                      |
| `JsonConvert.DeserializeObject<T>(s)`         | `JsonSerializer.Deserialize<T>(s, ctx)`           |
| `Lazy<T>(() => new T())` over a service       | Eagerly constructed at startup                    |
| `MakeGenericType(...)`                        | Pre-generated closed generic types per call site  |
| `dynamic` and `IDispatch` COM calls           | Strongly-typed COM wrappers (CsWin32 / WinSDK)    |

### Add these to make warnings actionable

```xml
<PropertyGroup>
  <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  <NoWarn>$(NoWarn);IL2026;IL3050</NoWarn>  <!-- only if you have triaged the warnings -->
</PropertyGroup>
```

Then run `dotnet publish` and read **every** IL warning. Each one is a
potential AOT runtime crash.

---

## Cold-start numbers (typical, i5-12400 / Win 11 23H2)

| Build mode                          | EXE size    | Cold start | Notes                                |
|-------------------------------------|-------------|------------|--------------------------------------|
| `dotnet` framework-dependent        | ~150 KB     | 250 ms     | needs 8.0 Desktop Runtime installed   |
| ReadyToRun self-contained           | ~30 MB      | 150 ms     | pre-JIT'd, still BCL DLLs             |
| NativeAOT single-file               | ~5 MB       | 40 ms      | no JIT, no runtime init              |
| Tauri (Rust + WebView2)             | ~8 MB       | 200 ms     | WebView2 paint time dominates         |
| C++ Qt 6 static                     | ~20 MB      | 80 ms      | comparable                           |
| Electron                            | ~150 MB     | 1500 ms    | Chromium spin-up                     |

NativeAOT is the smallest and fastest *fully-managed* option. C++/Qt
static is comparable but you give up the BCL ecosystem.

---

## CI integration

```yaml
- name: Publish NativeAOT
  run: |
    dotnet publish examples/nativeaot-winforms/NativeAotWinFormsDemo.csproj `
      -c Release -r win-x64 `
      -p:PublishAot=true `
      -o dist

- name: Upload artifact
  uses: actions/upload-artifact@v4
  with:
    name: NativeAotWinFormsDemo-win-x64
    path: dist/NativeAotWinFormsDemo.exe
```

The build needs a Windows runner with the .NET 8 SDK and the matching
workload for the ILCompiler. The `windows-latest` GitHub runner already
has this.

---

## Verifying it actually is AOT

After `dotnet publish`, check that:

1. The output EXE is in `dist\` and is single-file (no side-by-side DLLs unless you kept them).
2. `dumpbin /headers dist\MyApp.exe` shows subsystem `WINDOWS` (not `CONSOLE`).
3. Copy the EXE to a Windows VM with **no** .NET 8 runtime installed; double-click and confirm it runs.

If step 3 fails, you have a hidden reflection path. Re-run the publish
with `-p:IlcGenerateMetadataFile=true` to get a metadata dump, then
profile with `dotnet-trace` to find the failing site.

---

## When you should not migrate

| Reason                                         | What to do instead                              |
|------------------------------------------------|-------------------------------------------------|
| You need WPF data templates with reflection.   | Stay on ReadyToRun self-contained.              |
| You use a vendor SDK that relies on `Reflection.Emit`. | Ask the vendor for an AOT build; meanwhile ReadyToRun. |
| Your CI cannot pull the `Microsoft.DotNet.ILCompiler` workload. | Stay on ReadyToRun. |
| You need to ship to Windows 7.                 | Stay on .NET Framework 4.8 or self-contained 8 with `--no-restore`. |

NativeAOT is a sharp tool. Use it when the trade-off favours size +
cold start over the ecosystem you would have to give up.

---

## See also

- `scripts/build_dotnet_nativeaot.ps1` -- the build script.
- `examples/nativeaot-winforms/` -- the canonical runnable project.
- `references/distribution_playbook.md` -- distribution matrix including NativeAOT.
- `references/framework_matrix.md` -- how NativeAOT fits in the .NET ecosystem.
- Official: <https://learn.microsoft.com/dotnet/core/deploying/native-aot/>