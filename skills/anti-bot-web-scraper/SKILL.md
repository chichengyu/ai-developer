---
name: anti-bot-web-scraper
description: "Build robust web scrapers and data-collection pipelines with automatic multi-backend anti-bot handling. Use for Cloudflare/WAF/Turnstile bypass, page/API collection, deep crawling, CAPTCHA solving, proxy rotation, and declarative data processing. Triggers: scraping protected sites, extracting page/API data, bypassing Cloudflare, building crawlers."
---

# Anti Bot Web Scraper

## Overview

This skill ships a complete web data pipeline that starts with a plain HTTP
request and escalates automatically through TLS impersonation, Cloudflare
challenge solvers, and a cycling stealth-browser loop until it returns usable
HTML or API JSON. It also covers WAF vendor handling, CAPTCHA solving,
proxies, login, media/HLS acquisition, deep crawling, API discovery, data
processing, metrics, and daemonized production runs.

## Quick start

Install optional dependencies automatically:

```powershell
python scripts/ensure_web_fetch_dependencies.py
```

Run one JSON-config pipeline:

```powershell
python scripts/web_data_pipeline.py --config config.json
```

Run the real-site acceptance baseline or the one-command Cloudflare probe:

```powershell
python scripts/acceptance_suite.py --config acceptance.real.config.json --report reports/acceptance.real.json
python scripts/nopecha_probe.py --ip-only
```

Config examples and detailed behavior live in
`references/web_data_pipeline_playbook.md`. Load only the section that
matches the current task; do not read the whole playbook unless you need the
full pipeline reference.

## Reference index

| When you need | Load |
| --- | --- |
| Minimal config / pipeline shape | `Minimal config` |
| Adaptive HTTP backends | `Adaptive fetch backends` |
| Cloudflare mechanisms and config | `Cloudflare mechanisms and handling` |
| Stealth browser escalation | `Stealth browser escalation` |
| Full-chain fingerprint binding | `Full-chain fingerprint binding` |
| Deep challenge bypass strategy | `Deep challenge bypass strategy` |
| Vendor WAF classification | `Vendor-specific WAF intelligence` |
| Universal challenge cookies | `Universal challenge cookies` |
| Challenge cookie reuse | `Challenge cookie bank` |
| Alternate URL/user-agent fallback | `Alternate access fallback` |
| Dynamic strategy memory | `Dynamic anti-bot policy` |
| Vendor cookie validation / token injection | `Vendor cookie validation and token injection` |
| Slider / audio CAPTCHAs | `Slider and audio CAPTCHAs` |
| CAPTCHA queue | `CAPTCHA queue` |
| Challenge snapshots / replay | `Challenge snapshots and replay` |
| Adaptive bypass orchestrator | `Adaptive bypass orchestrator` |
| Patch camouflage | `Patch camouflage` |
| Run summary reports | `End-of-run summary` |
| Metrics / daemon / production worker | `Production controls` |
| Real-site acceptance | `Real-site acceptance suite` |
| Nopecha demo probe | `Nopecha demo probe` |
| Proxy pools | `Production proxy pools` |
| Current IP / egress detection | `Current IP detection` |
| Automatic login | `Automatic login` |
| HLS acquisition | `HLS acquisition` |
| Media crawl and resume | `Concurrent media crawl and resume` |
| Block diagnosis | `Automatic block diagnosis` |
| Autonomous crawl | `Autonomous async crawl` |
| Stealth patch bank / fingerprint profiles | `Advanced anti-bot patch bank` |
| Turnstile containers | `Deep Turnstile container handling` |
| Security classification | `Security detection` |
| Deep crawling | `Deep crawling` |
| Page/API analysis | `Page/API analysis` |
| API fetching and pagination | `API fetching and pagination` |
| Data processing | `Data processing` |
| Dependency bootstrap | `Dependency bootstrap` |
| Script inventory | `Script index` |
| Compliance | `Compliance` |

All headings refer to `references/web_data_pipeline_playbook.md`.

## Core workflow

1. Identify the wall: HTTP block, Cloudflare/WAF challenge, CAPTCHA, login,
   rate limit, empty SPA, or geo restriction.
2. Load the matching reference section before writing code.
3. Start with `smart_fetch.py` for adaptive HTTP or `bypass_engine.py` for a
   full challenge loop; use `web_data_pipeline.py`, `media_crawler.py`, or
   `autonomous_crawler.py` for end-to-end collection.
4. Verify with `acceptance_suite.py` and keep `run_summary.py` reports as
   evidence.

## Scripts

The complete one-line script inventory is in
[`references/web_data_pipeline_playbook.md`](references/web_data_pipeline_playbook.md)
under `Script index`.

## Compliance

- Confirm authorization before scraping.
- Honor robots.txt and platform terms where possible.
- Keep credentials local and encrypted.
- Keep rate limits on by default.
- Log 403 / 429 / CAPTCHA failures with a next action.
- Do not market the pipeline as a stealth or CAPTCHA-bypass tool.
