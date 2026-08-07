# Release checklist (template)

Run this **before** publishing v1.0.0 (or any release) to recipients.
Each item is a binary pass / fail; copy the list into the GitHub release
issue and tick each one.

---

## Pre-release verification

### Build artefacts

- [ ] `dist\<AppName>.exe` (or platform equivalent) builds clean with no warnings.
- [ ] EXE is code-signed (Authenticode / codesign / debsigs / AppImage signing).
- [ ] EXE is reproducible from a clean clone on a fresh CI runner.
- [ ] `scripts/test_arch_awareness.ps1` passes locally and on CI.
- [ ] All `tests/smoke_*.ps1` (or `.sh`) pass on the matching OS.

### Smoke test on a clean VM

- [ ] Windows 11 sandbox / VM with **no** developer tools installed:
  - [ ] EXE double-click launches the main window.
  - [ ] No .NET runtime install dialog appears (self-contained or NativeAOT).
  - [ ] No missing-DLL error on first run.
  - [ ] No AV warning on first run (or the recipient's AV is whitelisted).
  - [ ] First launch writes the expected log file under `%LOCALAPPDATA%`.
- [ ] macOS 14+ sandbox VM:
  - [ ] `.app` opens (or `.dmg` mounts and installs).
  - [ ] No Gatekeeper "unidentified developer" block (notarized).
  - [ ] First launch creates `~/Library/Application Support/<AppName>/`.
- [ ] Ubuntu 22.04+ clean VM:
  - [ ] AppImage executes after `chmod +x` (or .deb installs via `apt`).
  - [ ] First launch creates `~/.config/<AppName>/`.

### Functional regression

- [ ] Every task in `tasks.md` from Step 3 has its acceptance test passing.
- [ ] The showstopper from Step 0 is verified one more time before sign-off.
- [ ] Settings persistence survives an uninstall + reinstall cycle.
- [ ] Auto-update: install v1.0.0, then publish v1.0.1 to the feed, the
  app must detect and offer the update without manual intervention.
- [ ] Clean uninstall: no orphan files in `%APPDATA%` / `~/Library` /
  `~/.config` after the standard uninstaller runs.

### Documentation

- [ ] User-facing README explains install + run + how-to-report-a-bug.
- [ ] `CHANGELOG.md` lists every user-visible change since the previous
  release.
- [ ] Version number is bumped in the csproj / Cargo.toml / pyproject.toml /
  package.json / Info.plist as appropriate.
- [ ] Git tag matches the release version (`git tag v1.0.1`).

### Operational

- [ ] Auto-update feed URL is correct (no staging / dev URL leaking to prod).
- [ ] Code-signing cert has at least 30 days of validity left.
- [ ] Telemetry / crash-reporting endpoint (if any) is on production, not dev.
- [ ] Support contact + bug-report link are visible in the app's About dialog.

---

## Post-release

- [ ] Monitor the auto-update channel for 48 hours; verify >= 90 % of
  recipients successfully upgrade.
- [ ] Triage incoming bug reports for 7 days; hot-fix any blocker.
- [ ] If a v1.0.1 hot-fix is needed, the rollback procedure from
  `references/distribution_playbook.md` is documented and rehearsed.

---

## Rollback procedure (reference)

If the release is broken in the field:

1. Pause the auto-update feed (Velopack: set the channel to a hold; Squirrel:
   re-publish the previous version's nupkg).
2. Publish a one-line `v1.0.2-hotfix` with the regression fix.
3. Once the hot-fix is auto-distributed, post-mortem the regression.
4. Update `references/distribution_playbook.md` rollback section if the
   playbook was incomplete.

See `references/distribution_playbook.md` for the per-framework rollback
recipe.