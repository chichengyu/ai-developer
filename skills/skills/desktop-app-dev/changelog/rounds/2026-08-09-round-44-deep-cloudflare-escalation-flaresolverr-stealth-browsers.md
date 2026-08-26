# 2026-08-09 (round 44) -- Deep Cloudflare escalation: FlareSolverr + stealth browsers

### Added

- `scripts/flaresolverr.py` -- standard-library FlareSolverr client with
  `request.get`, session create/list/destroy, cookie normalization, and
  CLI status / solve commands.
- `scripts/stealth_browser.py` -- deep Cloudflare solvers for Patchright,
  nodriver, and DrissionPage; returns solved HTML, cookies, and UA.
- `BrowserSession` now accepts `engine: "patchright"` as an undetected
  Playwright drop-in.
- `web_data_pipeline.py` accepts `browser.stealth_engine` and
  `fetch.flaresolverr`; blocked pages can escalate to nodriver /
  DrissionPage or a local FlareSolverr, then merge clearance cookies back
  into API fetches.
- `ensure_web_fetch_dependencies.py` / `media_dependencies.py` now cover
  `patchright`, `nodriver`, and `DrissionPage`.

### Docs

- `references/web_data_pipeline_playbook.md`, `README.md`, `INDEX.md`, and
  `SKILL.md` document FlareSolverr and stealth-browser escalation.

### Tests

- `tests/test_media_pipeline.py` adds FlareSolverr client parsing,
  smart-fetch FlareSolverr backend ordering, stealth-engine availability,
  and expanded dependency status coverage.
