# Task card (template)

One card per atomic task. Keep tasks S/M/L; if larger, decompose further.

---

## T<ID>: <title>

- **Category**: scaffold | model | service | ui | feature | polish | integration | pkg | docs
- **Size**: S (< 1h) | M (1-4h) | L (4-8h, prefer to decompose)
- **Showstopper**: yes / no
- **Parallelizable**: yes / no (tag `[P]` in the task list)
- **Owner**: <who does the work>

### Description

One paragraph: what this task produces and why.

### Acceptance criteria

Each criterion is testable in <= 5 minutes:

- [ ] `<specific, testable behavior>`
- [ ] `<specific, testable behavior>`
- [ ] `<specific, testable behavior>`

### Dependencies

- `T<prev-id>` -- `<one-line reason>`
- (or "none" if this is a foundation task)

### Verification method

Unit test / manual smoke / automated UI test / other -- and the exact
command or click-through that confirms the acceptance criteria.

### Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| | low/med/high | low/med/high | |

### Definition of done

- All acceptance criteria checked
- Verification method executed and recorded
- Any new dependencies added to T1 / T3 / project metadata
- If this is a `[showstopper]` task: the showstopper still holds

---

## Worked examples

### T1: Project scaffold (S)

> Acceptance: `git clone && dotnet build` produces a runnable WPF shell on
> a clean Windows VM. Verification: open the produced EXE, see the empty
> main window, resize it.

### T5.3: Convert Markdown to PDF (S)

> Acceptance: opening `tests/fixtures/sample.md` and clicking "Convert"
> produces `sample.pdf` whose text content matches the markdown source.
> Verification: open the PDF, copy a paragraph, compare to the source.

### T6.2: Logging in production (M)

> Acceptance: triggering an unhandled exception produces a log entry at
> ERROR level with the full stack trace, written to
> `%LOCALAPPDATA%\\MyApp\\logs\\app-YYYYMMDD.log`, rotated when the
> file exceeds 10 MB. Verification: induce the error, open the log file,
> confirm the entry; induce a 10 MB+ log, confirm rotation.

### T7.1: Velopack auto-update (M)

> Acceptance: install v1.0.0, publish v1.0.1 to the Velopack feed, restart
> the app, see the update prompt, accept, app updates in place, no manual
> uninstall required. Verification: run the acceptance script that
> installs v1.0.0 and triggers the update check.
