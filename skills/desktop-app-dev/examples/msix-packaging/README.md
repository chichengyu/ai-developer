# MSIX Packaging Example

Minimal WPF (.NET 8 + Windows App SDK) app packaged as MSIX. Shows the
end-to-end CLI path: `dotnet publish` -> `MakeAppx.exe` -> `signtool`.

This is the canonical recipe for any modern Windows desktop app that wants
Store / sideload distribution.

## Layout

```
examples/msix-packaging/
  app/                       WPF project (MsixSample.csproj)
  package/                   Packaging project (package.msixproj)
    Package.appxmanifest     Appx identity + capabilities
    Assets/                  StoreLogo, Square150x150, Square44x44 PNGs (caller supplies)
  build_msix.ps1             CLI build: dotnet publish + MakeAppx + signtool
```

## Prereqs

- .NET 8 SDK
- Windows 10 SDK 22621+ (for `MakeAppx.exe` and `signtool.exe`)
- Code-signing certificate (.pfx) for production. For development,
  Visual Studio can create a self-signed test cert.

## Build

```powershell
cd examples/msix-packaging
powershell -File build_msix.ps1 `
  -CertPath path\to\cert.pfx `
  -CertPassword (Read-Host -AsSecureString)
```

Output: `dist/MsixSample.msix`.

## Sideload

```powershell
Add-AppxPackage .\dist\MsixSample.msix
```

To uninstall:

```powershell
Get-AppxPackage MsixSample | Remove-AppxPackage
```

## Notes

- The `Identity.Publisher` in `Package.appxmanifest` and the
  `PackageIdentityPublisher` in `package.msixproj` must match the
  subject of your signing cert. Use the `Get-PfxData` or
  `certutil -dump` to find the right value.
- For Microsoft Store submission, switch `<AppxBundle>Never</AppxBundle>`
  to `<AppxBundle>Always</AppxBundle>` and set `<AppxSymbolPackageEnabled>true</AppxSymbolPackageEnabled>`.
- For self-signed dev certs, use `New-SelfSignedCertificate` and trust it
  on the dev machine only.
