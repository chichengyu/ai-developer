# tests/

Smoke tests for the `mobile-app-dev` skill. Each test verifies that a
canonical example or fixture has the structure this skill expects.

## How to run

```powershell
$py = "C:\Users\xc\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
Set-Location C:\Users\xc\.codex\skills\mobile-app-dev\tests
foreach ($t in Get-ChildItem test_*.py) {
    Write-Host "=== $($t.Name) ==="
    & $py $t.FullName
}
```

## Tests

| Test                                  | What it verifies                                                   |
|---------------------------------------|--------------------------------------------------------------------|
| `test_plist_parse.py`                 | `fixtures/Info.plist.xml` is well-formed.                         |
| `test_gradle_config.py`               | `fixtures/build.gradle.kts` has the required entries.              |
| `test_requirements_parse.py`          | `fixtures/requirements.json` matches the schema.                  |
| `test_compose_module_parse.py`        | `examples/compose-news-feed/` has MainActivity + ViewModel + ...   |
| `test_flutter_module_parse.py`        | `examples/flutter-news-feed/main.dart` uses Riverpod.              |
| `test_rn_module_parse.py`             | `examples/rn-news-feed/App.tsx` uses zustand + FlatList + a11y.    |
| `test_no_bom.py`                      | No text file starts with a BOM or embeds U+FEFF.                  |
| `test_references_exist.py`            | Backticked paths in docs resolve to real files.                   |
| `test_select_framework.py`            | Step 1.5 decision tree smoke tests.                               |
| `test_plan_project.py`                | requirements.md and tasks.md generation.                          |
| `test_scaffold_project.py`            | Project skeleton generation for all frameworks.                  |
| `test_store_metadata.py`              | Store metadata document generation.                               |
| `test_setup_toolchain.py`             | Toolchain planning and check-only CLI smoke tests.                |

## What is NOT tested here

- Real device launches -- requires Xcode + iPhone.
- Real Android builds -- requires Gradle + Android SDK.
- App Store submission -- requires Apple Developer account.
- Push notifications -- requires APNs / FCM.

These belong in the parent project's e2e suite, not in the skill.
