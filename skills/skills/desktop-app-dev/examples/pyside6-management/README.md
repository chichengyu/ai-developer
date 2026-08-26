# PySide6 management shell

Runnable PySide6 example that combines the skill's mandatory UI and
lifecycle rules into one template:

- Left navigation + `QStackedWidget`, one table per right-side page
  (UI-05). A second table always opens on another page.
- Every action button and table gets a visible loading state while its
  background job runs.
- Every list page has a loading progress bar; when the job reports
  progress it renders 0-100%, and it hides after the list settles.
- The packaged EXE opens a frameless startup splash with a fade-in
  animation, status text, and a 0-100% progress bar before the main
  window appears.
- UI layout lives in `app.ui` and is loaded from Python with `QUiLoader`,
  so the same file can still be edited in Qt Designer.
- Optional dependencies are imported lazily. `openpyxl` is only imported
  when the user clicks export; dependency status/install runs in the
  dependency center, never at startup.
- `assets/dependencies.json` is the single dependency manifest. The
  dependency center lists every runtime dependency in a table; the user
  clicks `安装依赖` and the app auto-downloads / installs / configures
  each one with chunked, resumable download and no other manual steps.
- The manifest also carries `help`, `description`, and `manual_install`
  text. The dependency center shows what each dependency is for, where it
  is installed, and exact manual download / install steps for users who
  prefer not to use the automatic button.
- Every dependency can carry an official `homepage`; the dependency center
  renders it as a clickable link and opens the system default browser when
  clicked.
- Homepage / download URLs are **not hard-coded in code**. Every project
  fills its own `assets/dependencies.json`; when the software changes, only
  the manifest changes. See `templates/dependency_manifest.example.json`.

## Dependency center layout

The dependency center page contains:

1. Toolbar: `检查依赖` and `安装依赖`.
2. Dependency table: name, version, status, install path.
3. Help panel below the table: overall install instructions, official
   homepage links, and per-dependency manual install steps.
4. A loading progress bar while the table loads or installs.
- Closing the window cancels and waits for all `JobRunner`s and the global
  `QThreadPool`, and terminates any child processes registered by the app.

## Run

```powershell
python examples/pyside6-management/app.py
```

## Build a fast-starting EXE

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_python.ps1 `
  -Entry examples/pyside6-management/app.py `
  -Name PySide6Management `
  -HiddenImports "PySide6.QtUiTools,dependency_center,builtin_dependency_manager,lazy_python_dependency,threading_pyside6" `
  -Paths "scripts" `
  -AddData "examples/pyside6-management/assets;assets" `
  -Install -InstallDeps -FastStart
```

`-FastStart` produces a leaner PySide6 bundle, passes
`--disable-windowed-traceback`, and defaults to `OneDir` output for faster
cold start. For a single portable EXE, keep `-Mode OneFile`; it will be
smaller to distribute but slower to launch because PyInstaller extracts
the bundle to a temp directory first.

## UI regeneration

Open `assets/app.ui` in Qt Designer to edit the layout, then rebuild with
the command above. The Python controller reads the `.ui` at runtime, so no
generated Python UI file needs to be committed.
