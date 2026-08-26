# Tauri Mobile deep dive

Read this when Step 1.5 picks Tauri Mobile (Rust-first teams that
want a small WebView-based binary).

## When to use

- Rust backend / shared business logic is already the team strength.
- Web frontend is acceptable and binary size matters.
- Desktop + mobile share one Rust core.

## When NOT to use

- Team is not Rust-first.
- App needs deep native UI or complex OS integrations.
- The mobile toolchain is not yet stable enough for the team's
  release process.

## Project shape

```
my-app/
  src/                       frontend assets
  src-tauri/
    Cargo.toml
    tauri.conf.json
    src/main.rs
```

## Commands

```bash
npm install
npm run tauri android init
npm run tauri android build
npm run tauri ios build      # macOS only
```

## Build

Use `scripts/build_tauri_mobile.ps1` or the Tauri CLI directly.
The first mobile build downloads platform toolchains and can take
several minutes.

## Notes

- `tauri.conf.json` controls app identifier, window size, and the
  frontend directory.
- Rust dependencies compile for each mobile target; keep the graph
  small to control build time.
- iOS still requires macOS and Xcode; Android requires Android SDK /
  NDK plus Rust Android targets.
