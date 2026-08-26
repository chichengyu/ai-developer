# 2026-08-09 (round 45) -- Online Cloudflare verification + browser_path/auto_install

### Added

- `stealth_browser.py` accepts `browser_path` (Chrome / Edge binary) and
  `auto_install` (default true) so a missing engine is pip-installed before
  solving.
- `smart_fetch.py` treats an embedded Turnstile widget as passed when a
  valid `cf_clearance` cookie exists for the host, so HTTP backends stop
  bouncing after browser clearance is obtained.
- `web_data_pipeline.py` forwards `browser.browser_path` /
  `browser.auto_install` to the deep browser solver.

### Verified

- Installed `curl_cffi`, `cloudscraper`, `httpx`, `h2`, `patchright`,
  `nodriver`, and `DrissionPage`.
- Online against `https://nowsecure.nl/`:
  - DrissionPage + Edge: returned `cf_clearance`
  - Patchright + Edge: returned `cf_clearance`
  - nodriver + Edge: returned `cf_clearance`
  - End-to-end: DrissionPage clearance reused by `curl_cffi` over HTTP,
    status 200 and full page returned.
