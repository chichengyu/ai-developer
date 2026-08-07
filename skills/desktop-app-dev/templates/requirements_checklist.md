# Requirements checklist (template)

Copy this file into the project as `requirements.md` and fill it in before
coding starts. Items marked **required** must be answered. Items marked
**optional** may be deferred; record the deferral explicitly.

---

## 0. Project meta

- **Name**:
- **Owner**:
- **Target recipient** (developer, internal employee, consumer, gamer):
- **Target deadline**:
- **Maintenance commitment** (one-shot, 6 months, indefinite):

---

## 1. Functional requirements

### 1.1 Literal (what the user explicitly asked for)

| ID | Requirement | Priority (must / should / could) | Acceptance |
|---|---|---|---|
| F-1 | | | |
| F-2 | | | |
| F-3 | | | |

### 1.2 Implicit (what they need but did not say)

| ID | Requirement | Default we are assuming | Override |
|---|---|---|---|
| F-IMP-1 | Settings persistence | `%APPDATA%\\<AppName>\\config.json` | |
| F-IMP-2 | Error UI | Modal dialog with copy-to-clipboard | |
| F-IMP-3 | Logging | `%LOCALAPPDATA%\\<AppName>\\logs\\app-YYYYMMDD.log` | |
| F-IMP-4 | Single-instance enforcement | Named mutex | |
| F-IMP-5 | DPI awareness | Per-monitor v2 | |
| F-IMP-6 | HiDPI icon set | 16/24/32/48/64/128/256 px | |
| F-IMP-7 | Keyboard navigation | Full Tab order, Esc cancels | |
| F-IMP-8 | Localizable strings | All UI strings in resource file | |
| F-IMP-9 | File path handling | `Path.Combine` only | |
| F-IMP-10 | Time / date handling | `DateTimeOffset` only | |
| F-IMP-11 | Clean shutdown on logoff | Trap `WM_QUERYENDSESSION` | |
| F-IMP-12 | Uninstall cleanup | Remove app data on uninstall | |

---

## 2. Non-functional requirements

| Metric | Target | Measurement method |
|---|---|---|
| Cold start (window interactive) | | stopwatch from `Process.Start` |
| Steady-state memory at idle | | Task Manager working set |
| Steady-state CPU at idle | | Task Manager CPU % |
| Click-to-feedback (visible work) | | manual stopwatch on 10 clicks |
| Click-to-feedback (background work) | | progress indicator appears |
| Throughput | | benchmark script |
| Reliability per session | | error log count |
| Data sensitivity | (public / internal / confidential / regulated) | n/a |
| Minimum Windows version | | refused at startup if older |

---

## 3. Distribution

- **Format**: portable EXE / MSI / MSIX / Store:
- **Per-user or per-machine**:
- **Code-signing cert**: yes/no, vendor, expiry:
- **Auto-update**: yes/no, channel:
- **Elevation required**: yes/no, why:
- **Uninstall behavior**: keep user data / offer to remove / always remove:

---

## 4. Integration map

| System | Protocol | Auth | Failure mode | Response |
|---|---|---|---|---|
| | | | | |
| | | | | |

---

## 5. Failure modes (designed responses)

| Failure | Response | Test in T6? |
|---|---|---|
| Target process missing | | |
| Network unreachable | | |
| Disk full | | |
| Permission denied | | |
| Concurrent modification | | |
| Corrupt config file | | |
| Wrong runtime version | | |
| AV quarantines binary | | |

---

## 6. Showstopper

The single most important thing the app must NOT do wrong:
> **<one sentence>**

Every design decision should defer to this if it conflicts with another
requirement. The showstopper is verified first in Step 6.

---

## 7. Explicit assumptions and deferred decisions

| Assumption / deferral | Owner | Review date |
|---|---|---|
| | | |
| | | |

---

## 8. Sign-off

- [ ] User reviewed and accepted requirements
- [ ] Showstopper is unambiguous
- [ ] Every required field is filled
