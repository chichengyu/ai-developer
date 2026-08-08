# Framework selection engine (methodology)

`scripts/select_framework.py` walks every framework in the skill's matrix and
ranks them against a requirements brief. This document explains how the
scoring works, why it works that way, and how to extend it.

---

## Goals

The engine exists to answer the question **"given these concrete
requirements, which framework is optimal?"** in under a second, with
reproducible rationale. Three properties matter:

1. **Deterministic** -- the same brief always returns the same ranking.
2. **Defensible** -- the ranking can be explained dimension-by-dimension.
3. **Tunable** -- adding a new framework is a single row in one table.

The quick decision tree and the deep dive in `references/framework_matrix.md`
are *narrative* answers to this question. The engine is a *quantitative*
answer. When they disagree, the brief is the source of truth -- re-read it
and decide which dimensions were weighted too heavily or too lightly.

---

## Inputs

A requirements brief is a JSON / YAML object with the fields in
`templates/requirements_brief.md`. The minimum useful brief is:

```json
{ "target_os": [["windows", "x64"]], "team_languages": ["csharp"] }
```

Without `team_languages`, the engine cannot break ties between, e.g.,
WPF and tkinter for a Windows-only brief -- both fit. The team's existing
skills are the tie-breaker.

The built-in YAML loader accepts flat `key: value` lines only; nested values
such as `target_os` must use inline JSON-style arrays
(`target_os: [["windows", "x64"]]`), not indented block lists.

---

## Algorithm

### Step 1: derive weights

`derive_weights(req)` turns the brief into a `{dimension: weight}` map
where each weight is in [0, 1]:

- `target_os` -> weight 1.0 on every OS dimension + per-arch dimension.
- `hardware_access` -> weight 1.0 on `sendinput_friendly` (or
  `usb_serial_access`) and 0.7 on `win32_interop`.
- `web_ui_required: true` -> weight 1.0 on `web_ui_support`.
- `exe_size_budget: tiny` -> weight 1.0 on `exe_size_tiny`, 0.5 on `exe_size_small`.
- `cold_start_budget: fast` -> weight 1.0 on `cold_start_fast`.
- `native_look_required: win11` -> weight 1.0 on `native_look_win11`.
- `distribution: portable_exe` -> weight 1.0 on `single_file_output`.
- `team_languages` -> weight 1.0 on the synthetic `team_languages` dimension
  (handled in Step 2).

Always-on baselines (always weighted, even when not in the brief):

- `ecosystem_maturity` >= 0.4
- `threading_quality` >= 0.3
- `dev_speed` based on `dev_speed_priority` (0.0 / 0.5 / 1.0)

### Step 2: score each framework

For each framework `f`:

```
total_f = sum(weight_d * score_f_d for d in DIMS)
weight_sum_f = sum(weight_d for d in DIMS where weight_d > 0)
norm_f = max(0, total_f / weight_sum_f) * 100
```

The team-language dimension is per-framework:

```
team_boost_f = 1.0 if team_languages[0] in FRAMEWORK_LANGUAGES[f] else
               0.6 if any other team_languages[i] in FRAMEWORK_LANGUAGES[f] else
               0.0
```

and added into both `total_f` and `weight_sum_f` so it can swing the ranking.

### Step 3: rank and explain

Sort by `norm_f` descending, return the top N. For each pick, the top-2
positive dimensions (`top_reasons`) and top-2 negative dimensions
(`top_blockers`) drive the one-line rationale.

---

## How to add a new framework

1. Add a row to `FRAMEWORKS` with one entry per dimension in `DIMS`. Use
   `-1.0` for disqualifying dimensions (e.g. Linux support if the framework
   is Windows-only).
2. Add a row to `FRAMEWORK_LANGUAGES` mapping the framework to the
   language(s) it primarily targets.
3. Add a row to `DISPLAY_NAMES` so the human-readable output is correct.
4. Add a one-line entry to `RATIONALES` so each pick has a sentence.
5. Re-run `python select_framework.py --self-test` and update the test
   cases to cover the new entry.

---

## Limitations (be honest)

- The engine does not understand *novel* requirements (e.g. "must talk to a
  proprietary hardware dongle"). It uses the public, common dimensions.
  A spike to confirm hardware compatibility is always required.
- The framework scores are calibrated by hand against the matrix in
  `references/framework_matrix.md`. They are calibrated, not measured.
  When a framework ships a major release, re-check the relevant cells.
- The engine picks *one* framework. Sometimes the right answer is "two
  frontends" (e.g. Tauri for the desktop, MAUI for mobile). When in doubt,
  read the top-3 rationale and decide.
- It does not consider *organizational* constraints (existing codebases,
  internal skills, hiring market, license audits). Add those as
  `team_languages` and `oss_only` for now; future versions will add
  `codebase_constraints`.

---

## Worked example: TLBB game bot

Brief:

```json
{
  "target_os": [["windows", "x64"]],
  "team_languages": ["python"],
  "hardware_access": "sendinput",
  "exe_size_budget": "small",
  "cold_start_budget": "fast",
  "distribution": "portable_exe",
  "oss_only": true,
  "dev_speed_priority": "high"
}
```

Run `python scripts\select_framework.py brief.json`. Output:

```
#1  Python tkinter (stdlib)    score = 90.5
#2  Python PySide6 (Qt 6)      score = 86.0
#3  Tauri (Rust + WebView)      score = 84.0
```

Why tkinter wins:

- Positive dimensions: Windows support, macOS support, dev speed, threading
  quality, ecosystem maturity, sendinput friendly.
- Tkinter + PyInstaller + ctypes `SendInput` is the canonical path for
  Windows game automation: zero install, single EXE, fast iteration.

WPF would win if you swapped `team_languages` to `["csharp"]`.

---

## See also

- `templates/requirements_brief.md` -- input schema + worked examples.
- `references/framework_matrix.md` -- narrative pros/cons.
- `SKILL.md` Step 2 -- where the engine plugs into the 8-step workflow.
