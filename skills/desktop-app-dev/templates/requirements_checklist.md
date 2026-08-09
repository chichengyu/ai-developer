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
| F-IMP-13 | Startup animation + progress bar | Show splash before main window | |

### 1.3 界面硬性要求（UI hard requirements）

All UI-01..UI-19 items in `references/ui_hard_requirements.md` are
mandatory unless explicitly waived below. Fill in the waiver or the
page / acceptance evidence for each item.

| ID | 硬性要求 | Default | Waiver / acceptance |
|---|---|---|---|
| UI-01 | 全局配色统一，默认模仿 Codex 界面 | required | |
| UI-02 | 全局控件样式统一 | required | |
| UI-03 | 文字与背景鲜明对比 | required | |
| UI-04 | 布局对齐一致，溢出滚动或换行 | required | |
| UI-05 | 右侧单表格，多表格另开页面 | required | |
| UI-06 | 不重复页面标题 | required | |
| UI-07 | 管理列表底部分页 | required | |
| UI-08 | 省略号悬停显示完整内容 | required | |
| UI-09 | 行操作栏与右键菜单支持自动刷新间隔 | required | |
| UI-10 | 主题中心 + 下载地址 + 刷新 + 下载后按钮变“应用” | required | |
| UI-11 | 所有选项去重 | required | |
| UI-12 | 用户配置持久化 | required | |
| UI-13 | 左侧日志入口 + 成功/失败日志详情 | required | |
| UI-14 | 危险红/警告橙/成功绿/信息蓝 | required | |
| UI-15 | 表单编辑提供示例 | required | |
| UI-16 | 滚动条明显且图标显示 | required | |
| UI-17 | 表格提示与搜索栏分行 | required | |
| UI-18 | 重型桌面端界面，禁止 Web 化 | required | |
| UI-19 | 内置依赖中心：菜单列出全部依赖，点击安装自动分片下载/安装/配置，无需其他操作 | required | |

### 1.4 代码开发硬性要求（minimal-change hard requirements）

All CODE-01..CODE-05 items in `SKILL.md` are mandatory whenever the task
touches existing code, unless explicitly waived below. Fill in the waiver
or the acceptance evidence for each item.

| ID | 硬性要求 | Default | Waiver / acceptance |
|---|---|---|---|
| CODE-01 | 保留可用的原有逻辑 | required | |
| CODE-02 | 改动范围最小 | required | |
| CODE-03 | 增量扩展优先 | required | |
| CODE-04 | 行为变更显式记录 | required | |
| CODE-05 | 原功能回归验证 | required | |

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
- [ ] UI-01..UI-19 均已逐项填写或显式豁免（含原因与复审日期）
- [ ] CODE-01..CODE-05 均已逐项填写或显式豁免（含原因与复审日期）
