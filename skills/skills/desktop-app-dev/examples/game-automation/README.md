# Game-automation demo

Combines three skill assets into a minimal but real game-automation
controller, matching the worked TLBB example in
`references/task_decomposition.md`.

| Layer        | Asset                              |
|--------------|------------------------------------|
| Window pick  | `scripts/window_enum_python.py`    |
| Input        | `scripts/sendinput_python.py`      |
| Threading    | `scripts/threading_tkinter.py`     |

## Run

```powershell
python examples/game-automation/app/app.py
```

Click Refresh to enumerate top-level windows, type a title substring
(or window class) into the entry, then click Refresh again to select it.
After a target is selected, "Send F5" or "Combo Ctrl+F1" fires SendInput
into the foreground window.

## Safety

- `press_combo` uses randomized 50-150 ms timing; `send_key` holds the
  key for `hold_ms`.
- Foreground is forced before every keystroke (see `_ensure_foreground`).
- Enumeration, key sends, and combos run on a daemon thread so the GUI
  stays responsive.
- The demo does **not** include any dungeon flow or skill loop -- that's a
  T5.x task in your own project, not in this example.

## Package

```powershell
powershell -File scripts/build_python.ps1 `
  -Entry examples/game-automation/app/app.py `
  -Name GameAutoDemo
```
