# Heavy desktop acceptance (重型桌面端验收)

Copy this into `requirements.md` / release notes. Fill the blanks from
Step 0, verify each item in Step 6, and attach the report from
`scripts/heavy_desktop_verify.ps1`.

## Data volume

- [ ] Expected max rows per grid: `________`
- [ ] Expected local DB records: `________`
- [ ] Virtualization or paging strategy: `________`
- [ ] 100k-row scroll / render latency budget: `________ ms`
- [ ] Search debounce: `________ ms`

## Architecture

- [ ] Layers: UI / ViewModel / Service / Data access / Infrastructure
- [ ] DI composition root location: `________`
- [ ] Feature modules: `________`
- [ ] Plugin surface (if any): `________`
- [ ] Event aggregator / message bus: `________`

## Long-running work

- [ ] Job state machine persisted: pending / running / paused / cancelled /
  completed / failed
- [ ] Worker pool used (see `references/threading_playbook.md`)
- [ ] Progress aggregated: total / done / failed / bytes / speed / ETA
- [ ] Shutdown drains, cancels, and flushes
- [ ] COM work isolated on a dedicated STA thread (if applicable)

## Performance

- [ ] Cold start budget: `________ ms`
- [ ] Idle memory budget: `________ MB`
- [ ] Idle CPU budget: `________ %`
- [ ] Click-to-feedback budget: `________ ms`
- [ ] 1-hour memory growth budget: `________ %`
- [ ] `scripts/heavy_desktop_verify.ps1` report attached

## Stability

- [ ] Single instance enforced
- [ ] Unhandled-exception handler + crash dump
- [ ] Log rotation and correlation ids
- [ ] Settings migration `v1 -> v2` tested
- [ ] DB transactions and pre-migration backup
- [ ] Offline / retry / disk-full / permission behavior defined

## Multi-window and plugins

- [ ] Window manager owns every window / ViewModel lifetime
- [ ] Window bounds, splitter, columns, and active page persist
- [ ] Plugin contract versioned and isolated

## Release gate

- [ ] UI-01..UI-19 pass (waivers recorded)
- [ ] Heavy desktop acceptance items above all pass
- [ ] `scripts/heavy_desktop_verify.ps1` numbers match Step 0 budgets
