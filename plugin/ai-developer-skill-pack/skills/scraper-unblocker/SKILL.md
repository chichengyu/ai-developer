---
name: scraper-unblocker
description: Professional web scraping assistant that builds robust crawlers, automatically diagnoses common anti-bot obstacles (403, 429, 503, JS challenges, cookie walls, WAF blocks), and deep-crawls media such as images, videos, and HLS streams with classification by series/drama name. Use when the user asks to scrape a website, write or fix a spider/crawler, extract data from HTML or public JSON APIs, crawl all images/videos from a site, classify media by name, handle rate limits or anti-bot blocks, or build an incremental scraper pipeline.
---

# Scraper Unblocker

Build compliant, robust scrapers and turn common blocking signals into concrete fixes.

## Hard Boundaries

- Scrape only sites you are authorized to scrape; check robots.txt, terms, and applicable law first.
- Never bypass authentication, paywalls, CAPTCHAs, or other access controls. Never automate challenge solving, use CAPTCHA-solving services, forge tokens, or disguise the client to defeat anti-bot fingerprinting.
- When a site enforces a CAPTCHA or interactive challenge as an access control, stop automation and switch to the official API, a documented export, or a human-in-the-loop session.
- Keep traffic low, set a descriptive User-Agent with contact info, honor `Retry-After`, and obey robots directives.

## Workflow

1. Prefer official APIs, sitemaps, bulk exports, or public datasets before scraping HTML.
2. Probe the target: `python scripts/scraper_probe.py --url https://example.com/path`. Use `--json` for machine-readable output; the probe checks robots.txt, sitemap, status, headers, and block heuristics, then suggests next steps. Add `--cookie` or `--header` only for a session the user already holds.
3. Map any detected block to a fix in `references/block-patterns.md` before changing the crawler.
4. Build or adapt the crawler from `scripts/scraper_runner.py`. Set `--concurrency`, `--delay`, `--max-pages`, and `--output` to match the site's tolerance.
5. Validate extracted data: normalize URLs, dedupe, keep source metadata, and write JSONL incrementally so interrupted runs resume cleanly.
6. Log challenge or CAPTCHA pages as `BLOCKED` and report them; do not retry or circumvent them.

## Media Deep Crawl

1. Identify the target type: images, videos, both, or media classified by series/drama name.
2. Prefer the site sitemap for discovery; expand sitemap indexes before guessing category URLs.
3. Probe one detail page with `python scripts/media_probe.py --url <detail-url> --json` to learn the title field, metadata, inline state keys, and media URL shape.
4. Crawl with `python scripts/media_runner.py --seed <sitemap-or-page> --mode all --download --ffmpeg <path>`. Use `--mode images`, `--mode videos`, `--mode audio`, or comma-separated combinations; it writes `media_index.jsonl` classified by drama name and downloads direct assets.
5. For JS-only media URLs, render with Playwright/Selenium and extract resources from the live DOM; do not add stealth patches.
6. Log encrypted HLS/DASH streams and access-controlled media as `PROTECTED`; never decrypt or bypass them.
7. For sites that need a login, run `python scripts/session_capture.py --login-url <login-page> --username <account> --password <password>` once. It fills an ordinary login form and submits it; if the site adds a CAPTCHA, SMS, or two-factor step, the user completes that step in the opened browser. Then pass `--cookies-file session_cookies.json` to the other tools. If the login fields are unusual, add `--username-selector`, `--password-selector`, `--submit-selector`, or `--success-url`.

## Resources

- `scripts/scraper_probe.py`: stdlib diagnostic probe; run it first on any blocked target.
- `scripts/scraper_runner.py`: stdlib concurrent crawler template with robots checks, retries and backoff, rate limiting, same-host link traversal, and JSONL output.
- `scripts/media_probe.py`: stdlib deep media probe that extracts titles, Open Graph/JSON-LD metadata, inline state JSON, and image/video/audio/manifest URLs.
- `scripts/media_runner.py`: stdlib media crawler with sitemap discovery, drama-name classification, direct downloads, and optional ffmpeg HLS merging.
- `scripts/session_capture.py`: opens a real browser, can auto-fill the user's own account credentials, and saves the authenticated session for `--cookies-file`.
- `references/block-patterns.md`: catalog of block signals (status codes, headers, body markers) with compliant fixes and architecture guidance.
- `references/media-crawling.md`: media request patterns, metadata sources, media handling, and a real sitemap-driven short-drama site example.

## Implementation Notes

- Use `requests` or `httpx` when the environment has them; the bundled scripts intentionally use only the standard library so they run anywhere.
- For JS-rendered pages, use Playwright or Selenium only for rendering; do not add stealth patches or challenge-solving automation.
- For pagination, prefer `rel=next`, sitemaps, or documented query parameters; avoid guessing page URLs.
- Add exponential backoff with jitter and a global minimum delay before scaling concurrency.
- Pass the user's own authorized session with `--cookie` or `--header` when a site expects login; never forge or steal sessions.
- Prefer `--cookies-file` produced by `session_capture.py` when the user does not know cookie syntax; use `--username` and `--password` for ordinary forms, while CAPTCHA and two-factor steps stay human-in-the-loop.
- Store raw responses and extraction timestamps; reprocess incrementally instead of re-downloading the whole site.
- For media sites with sitemap indexes pointing to player pages, crawl the sitemap, then classify assets by the detail-page `h1`/`og:title`; write the media index before downloading.
