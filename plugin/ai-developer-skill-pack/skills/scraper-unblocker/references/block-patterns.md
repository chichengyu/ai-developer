# Block Patterns and Compliant Fixes

## Legal Check Before Scraping

- Confirm permission: public data is not automatically legal to scrape.
- Read robots.txt and the site terms; respect `Disallow`, `Allow`, and `Crawl-delay`.
- Prefer official APIs, sitemaps, and bulk exports when they exist.
- Never bypass authentication, paywalls, CAPTCHAs, or other access controls.
- Put contact info in the User-Agent and keep request rates below site tolerance.

## Signal Table

| Signal | Likely Cause | Compliant Fix |
| --- | --- | --- |
| 401 | Authentication required | Use official auth/API, or stop; never bypass login. |
| 403 | Access control or WAF | Improve request hygiene; if access-controlled, stop or use official API. |
| 429 | Rate limited | Honor `Retry-After`; exponential backoff with jitter; reduce concurrency. |
| 503 | Overload, maintenance, or challenge | Retry later; if body shows a challenge, stop automation. |
| "Just a moment", "Checking your browser", `cf-chl` | JS challenge | Use official API/permission or a human-in-the-loop browser session; never automate challenge solving. |
| CAPTCHA | Access control | Human solves it or use the official API; never use solving services. |
| "Enable JavaScript" | JS-rendered content | Render with Playwright/Selenium; do not stealth-patch the browser. |
| Cookie/consent wall | Consent flow | Use official API or documented export when data is consent-gated. |
| WAF pages ("Access Denied", Akamai, Incapsula, DataDome) | Bot traffic signature | Reduce volume, set a real User-Agent, use a maintained HTTP client; if still blocked, stop or get permission. |
| IP/geo block | IP reputation or region | Use lawful proxies only if permitted; prefer official API or a local mirror. |
| Redirect loop | Session/cookie dependency | Inspect the final URL and cookies; never loop through challenge redirects. |
| TLS/HTTP2 fingerprint block | Advanced bot detection | Use maintained HTTP libraries; do not spoof fingerprints to evade detection. |

## Diagnosis Decision Tree

1. Run `scraper_probe.py --url <target> --json` and read `block_signals`.
2. No signals: keep volume low, use `scraper_runner.py`, and cache responses.
3. `rate_limited` or HTTP 429: honor `Retry-After`, add exponential backoff with jitter, reduce concurrency.
4. `temporarily_unavailable` or HTTP 503: retry later; if body shows a challenge, stop automation.
5. `waf_or_access` or HTTP 403: check robots and request hygiene; if access-controlled, stop or use the official API.
6. `challenge`, `cloudflare`, `captcha`, `perimeterx`, `kasada`, `arkose`: stop automation; use official API, documented export, or a human-in-the-loop session.
7. `js_required`: render with Playwright/Selenium; do not stealth-patch the browser.
8. `cookie_wall`: if consent-gated, use the official API or documented export.

## Request Hygiene Checklist

- Set a descriptive User-Agent with contact info; keep it stable per crawl.
- Send only headers the site needs; do not fake browser fingerprints to defeat detection.
- Use your own authorized session via `--cookie` or `--header` when the site expects login; never steal or forge sessions.
- Keep a global minimum delay and low concurrency; scale only after observing stable 200s.
- Use exponential backoff with jitter and honor `Retry-After`; do not hammer 429/503 responses.
- Cache robots.txt, sitemaps, and successful responses so repeat crawls do not re-hit the site.
- Use lawful proxies only when permitted; do not rotate IPs to evade an explicit block.
- If a site still blocks you, stop and seek the official API or permission instead of escalating.

## Build Order

1. Static HTML: use `requests`/`httpx` or the bundled runner with retries and rate limiting.
2. Embedded JSON: parse `window.__INITIAL_STATE__`, JSON-LD, or `<script type="application/json">` instead of HTML.
3. Pagination: prefer `rel=next`, sitemaps, or documented query parameters.
4. JS rendering: use Playwright/Selenium for rendering only, with human-like interactions and no stealth patches.
5. API discovery: inspect documented endpoints in the network tab or OpenAPI docs before scraping HTML.

## Health Checks

- robots.txt is honored.
- User-Agent identifies the crawler and includes contact info.
- Retries use exponential backoff with jitter and honor `Retry-After`.
- A global rate limit exists before concurrency is scaled.
- Output is incremental JSONL with dedupe and source metadata.
- Challenge/CAPTCHA pages are logged as `BLOCKED`, not retried.
- The legal boundary for each target is documented.
