# WPF Threading Demo

Minimal WPF (.NET 8) app that uses `scripts/threading_wpf.cs` as a
`<Compile Include>` link so the template stays in one canonical place.

## Run

```powershell
cd examples/wpf-threading
dotnet run
```

## Build a single-file EXE

```powershell
dotnet publish -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true -p:PublishReadyToRun=true
```

Output: `bin/Release/net8.0-windows/win-x64/publish/WpfThreadingDemo.exe`
