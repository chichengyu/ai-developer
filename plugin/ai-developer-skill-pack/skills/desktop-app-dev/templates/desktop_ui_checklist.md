# Desktop UI checklist (桌面界面验收)

Run with `references/ui_hard_requirements.md` UI-01..UI-19. Capture
screenshots at 800x600 and 1920x1080 in light, dark, and high-contrast
modes.

## Tokens and theming

- [ ] One token source exists and no view hard-codes colors / spacing
- [ ] Light / dark / high-contrast themes all render correctly
- [ ] OS theme changes apply at runtime
- [ ] Theme center has installed themes, download URL, refresh, and `应用`
- [ ] Semantic colors are consistent (success / warning / danger / info)

## Layout

- [ ] Minimum 800x600 works without clipped controls
- [ ] Toolbar, status bar, row, and panel heights are stable
- [ ] Long tables scroll both ways with frozen headers
- [ ] No web-style hero, floating card clusters, or card-in-card
- [ ] Splitters and column widths persist

## Controls

- [ ] Menu / toolbar / status bar / dock panels present where relevant
- [ ] One table per page with bottom pagination
- [ ] Ellipsized text shows full value in tooltip
- [ ] Row actions and context menus include auto-refresh interval
- [ ] Forms show examples / defaults and inline validation

## Interaction

- [ ] Full keyboard operation: Tab, Enter, Esc, mnemonics
- [ ] Focus is visible
- [ ] Destructive actions confirm before executing
- [ ] Long-running commands show progress and cancellation
- [ ] Loading / empty / error / disabled / dirty states are explicit

## Accessibility

- [ ] Contrast passes 4.5:1 / 3:1
- [ ] Screen readers get names and roles
- [ ] Dialog focus is trapped and released correctly
- [ ] High-contrast mode is usable, not an afterthought

## Performance

- [ ] Grids / lists virtualized or paged
- [ ] Search debounced and cancellable
- [ ] Theme switch does not rebuild the whole window
- [ ] Scroll / resize / theme-switch latency measured in Step 6

## Screenshots

- [ ] 800x600 light
- [ ] 800x600 dark
- [ ] 800x600 high-contrast
- [ ] 1920x1080 light
- [ ] 1920x1080 dark
- [ ] 1920x1080 high-contrast
