# Requirements brief (input to scripts/select_framework.py)

Fill this in **before** Step 2 in SKILL.md. The framework auto-selector reads
this brief and returns the top 3 ranked candidates with rationale.

The brief can be JSON (preferred) or a flat `key: value` YAML shape. YAML
must use inline `[...]` values for lists (for example
`target_os: [["windows", "x64"]]`); indented block lists are not supported.
Save it as `requirements.json` (or any name) and run:

```powershell
python scripts\select_framework.py requirements.json
python scripts\select_framework.py requirements.json --json    # machine-readable
```

UTF-8 BOM is accepted and stripped automatically.

---

## Schema

| Field                    | Type                       | Required | Default | Notes |
|--------------------------|----------------------------|----------|---------|-------|
| `target_os`              | list of `[os, arch]` pairs | yes      | (none)  | `os` in {windows, macos, linux}; `arch` in {x64, arm64, x86}. |
| `team_languages`         | list of strings            | no       | `[]`    | First entry is the primary language (gets full boost). Examples: csharp, python, rust, typescript, cpp, go, kotlin, swift. |
| `hardware_access`        | string                     | no       | `none`  | `none` | `sendinput` | `raw_input` | `usb_serial`. Drives input / interop weighting. |
| `web_ui_required`        | bool                       | no       | `false` | If true, boost Tauri / Electron / Wails / Neutralino. |
| `exe_size_budget`        | string                     | no       | `no_limit` | `tiny` (< 5 MB) | `small` (< 30 MB) | `no_limit`. |
| `cold_start_budget`      | string                     | no       | `no_limit` | `fast` (< 0.5 s) | `no_limit`. |
| `native_look_required`   | string                     | no       | `none`  | `win11` | `macos` | `linux` | `any_native` | `none`. |
| `distribution`           | string                     | no       | `any`   | `any` | `portable_exe` | `installer` | `store` | `auto_update`. |
| `store_distribution`     | bool                       | no       | `false` | Boosts MSIX / DMG / deb support. |
| `auto_update_required`   | bool                       | no       | `false` | Boosts frameworks with built-in auto-update. |
| `oss_only`               | bool                       | no       | `true`  | If false, Qt 6 (paid license) can win. |
| `maintenance_horizon`    | string                     | no       | `indefinite` | `one_shot` | `6_months` | `12_months` | `indefinite`. |
| `dev_speed_priority`     | string                     | no       | `medium`    | `low` | `medium` | `high`. |

---

## Example: TLBB game automation

```json
{
  "target_os": [["windows", "x64"]],
  "team_languages": ["python"],
  "hardware_access": "sendinput",
  "exe_size_budget": "small",
  "cold_start_budget": "fast",
  "distribution": "portable_exe",
  "oss_only": true,
  "maintenance_horizon": "indefinite",
  "dev_speed_priority": "high"
}
```

Output: **Python tkinter** wins (PyInstaller + ctypes SendInput). WPF is a
near second if you swap team_languages to `["csharp"]`.

## Example: cross-platform productivity app with web UI

```json
{
  "target_os": [
    ["windows", "x64"],
    ["macos", "arm64"],
    ["linux", "x64"]
  ],
  "team_languages": ["rust", "typescript"],
  "web_ui_required": true,
  "exe_size_budget": "small",
  "distribution": "installer",
  "auto_update_required": true,
  "maintenance_horizon": "indefinite"
}
```

Output: **Tauri** wins. Electron is a close second if you swap to
`team_languages: ["typescript"]` only.

## Example: cross-platform .NET with native look

```json
{
  "target_os": [
    ["windows", "x64"],
    ["macos", "arm64"],
    ["linux", "x64"]
  ],
  "team_languages": ["csharp"],
  "native_look_required": "any_native",
  "distribution": "installer",
  "auto_update_required": true,
  "maintenance_horizon": "12_months"
}
```

Output: **C# / Avalonia 11**. WPF would win if you drop Linux / macOS.

## Example: Microsoft Store Win11 app

```json
{
  "target_os": [["windows", "x64"], ["windows", "arm64"]],
  "team_languages": ["csharp"],
  "native_look_required": "win11",
  "distribution": "store",
  "store_distribution": true,
  "maintenance_horizon": "indefinite"
}
```

Output: **C# / WinUI 3** (only framework that ships to Microsoft Store with
modern Fluent design).

## YAML form

```yaml
target_os: [["windows", "x64"], ["macos", "arm64"]]
team_languages: [python, csharp]
web_ui_required: false
distribution: installer
```
