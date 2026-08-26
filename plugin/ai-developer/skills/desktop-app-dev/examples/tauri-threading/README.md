# Tauri Threading Demo

Real Tauri v2 project that demonstrates the `threading_tauri.rs` template.
The Rust side lives in `src-tauri/`, the web UI in `src/`.

## Prereqs
- Rust toolchain (https://rustup.rs)
- Tauri CLI: `cargo install tauri-cli --version "^2.0"`
- WebView2 (Win10+ has it; otherwise install the runtime)

## Dev run
```powershell
cd examples/tauri-threading
cargo tauri dev
```

## Build
```powershell
powershell -File scripts/build_tauri.ps1
```

Produces NSIS + MSI in `src-tauri/target/release/bundle/`.
