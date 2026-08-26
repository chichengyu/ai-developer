# 2026-08-09 (round 42) -- Adaptive anti-bot fetch + Cloudflare hardening

### Added

- `scripts/smart_fetch.py` -- automatic multi-backend HTTP transport layer:
  `curl_cffi` (TLS/JA3/JA4 impersonation), `cloudscraper` (Cloudflare JS /
  Turnstile), `httpx` (HTTP/2), and the standard-library `urllib` fallback.
  `SmartFetchSession` keeps the `MediaSession` interface and switches
  backends when the security detector sees Cloudflare / WAF / rate-limit /
  CAPTCHA responses, while preserving cookies, UA, and proxy.
- `create_fetch_session()` factory plus `"fetch": {"backend": "auto"}`
  config support in `web_data_pipeline.py`, `api_client.py`, and
  `deep_crawler.py` (`--fetch-backend auto`).
- Cloudflare official-mechanism hardening: `cloudflare_challenge.py` now
  tracks valid vs. expired `cf_clearance`, `__cf_bm`, `Server: cloudflare`,
  `cf-mitigated`, `cf-cache-status`, `cf-ray`, and optional bot-score
  headers, plus `reuse_clearance`, `pin_proxy`, `keep_bm_cookie`, and
  `clearance_passage_seconds` config.
- `media_dependencies.py` checks / installs the optional web-fetch stack:
  `curl_cffi`, `cloudscraper`, `httpx`, and `h2`.

### Docs

- `references/web_data_pipeline_playbook.md`, `README.md`, `INDEX.md`, and
  `SKILL.md` document the adaptive fetch section and Cloudflare clearance /
  Bot Management cookie rules from the official Cloudflare docs.

### Tests

- `tests/test_media_pipeline.py` adds smart-fetch factory, local fallback,
  backend-switch, blocked-metadata, clearance-cookie, and expired-clearance
  coverage.
