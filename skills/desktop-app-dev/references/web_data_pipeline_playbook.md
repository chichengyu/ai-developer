# Web data pipeline: fingerprint browser, CAPTCHA, API collection, and processing

Playbook for a desktop app that needs to collect page and API data
automatically, then process it according to user-defined rules. It ties
together the existing skill templates:

- `scripts/browser_session.py` - stable fingerprint profile, cookies,
  storage state, runtime XHR/fetch capture
- `scripts/captcha_solver.py` - auto-detect, local OCR, third-party solver,
  manual fallback
- `scripts/page_data_parser.py` - deep static page analysis (metadata,
  embedded JSON, API endpoints, pagination, CAPTCHA detection)
- `scripts/api_analyzer.py` - API manifest with auth headers, endpoint
  scores, data paths, and inferred pagination
- `scripts/api_client.py` - build replayable API specs from a capture and
  fetch data through the rate-limited `MediaSession`
- `scripts/smart_fetch.py` - optional adaptive transport layer that
  auto-switches between `curl_cffi` (TLS/JA3/JA4 impersonation),
  `cloudscraper` (Cloudflare JS / Turnstile), `httpx` (HTTP/2), and the
  standard-library fallback
- `scripts/ensure_web_fetch_dependencies.py` - check-only or automatic
  pip installer for the optional web-fetch packages
- `scripts/flaresolverr.py` - standard-library client for a local
  FlareSolverr service (browser-based Cloudflare / DDoS-Guard solving)
- `scripts/stealth_browser.py` - deep browser solvers using Patchright,
  nodriver, or DrissionPage
- `scripts/data_processor.py` - declarative data shaping and aggregation
- `scripts/web_data_pipeline.py` - one-config end-to-end orchestrator
- `scripts/security_detector.py` - automatic identification of Cloudflare,
  WAF, rate-limit, login, CAPTCHA, cookie, JS, geo, and empty-SPA responses
  with a non-interactive action plan
- `scripts/cloudflare_challenge.py` - high-intensity Cloudflare challenge
  handling: stage detection, `cf_clearance` waiting, Turnstile interaction /
  token injection, reload retries, and proxy-rotation signals
- `scripts/deep_crawler.py` - BFS deep crawl through links and sitemaps with
  robots.txt, same-host filtering, deduplication, and blocked-page skipping

Only automate flows the user is authorized to automate. The guard rails in
`scripts/scrape_guard.py` still apply: rate limits, retries, robots.txt,
and adaptive backoff. The pipeline is not a stealth or CAPTCHA-bypass tool;
treat anti-bot responses as failures to log and handle, not as something to
hide.

## 1. Pipeline shape

```text
config.json
  -> BrowserSession (fingerprint + cookies + proxy + optional login)
  -> page/API analysis (static + runtime network)
  -> CAPTCHA auto-solve when needed
  -> ApiClient fetch with rate limit / retry
  -> data_processor steps (filter / select / sort / dedupe / aggregate)
  -> JSON / JSONL / CSV output
```

The HTTP-only mode skips Playwright and still works for public pages:

```text
config.json
  -> MediaSession fetch HTML
  -> page_data_parser.analyze_page()
  -> ApiClient fetch discovered API specs
  -> data_processor
  -> output
```

## 2. Minimal config

```json
{
  "pages": ["https://example.com/list"],
  "browser": {
    "enabled": false,
    "headless": true,
    "fingerprint": {"seed": 42, "locale": "zh-CN", "timezone_id": "Asia/Shanghai"},
    "fingerprint_path": "profiles/fp.json",
    "cookies_path": "profiles/cookies.json",
    "network_capture": {"include_bodies": true}
  },
  "captcha": {
    "enabled": false,
    "api_key": "",
    "allow_manual_fallback": false
  },
  "api": {
    "include_captured": true,
    "include_static": true,
    "max_specs": 100,
    "min_interval": 0.5,
    "max_retries": 3,
    "concurrency": 1
  },
  "processing": {
    "steps": [
      {"op": "filter", "params": {"conditions": [{"field": "price", "op": "gte", "value": 10}]}},
      {"op": "select", "params": {"fields": ["id", "name", "price"]}},
      {"op": "sort", "params": {"keys": [{"field": "price", "desc": true}]}},
      {"op": "dedupe", "params": {"fields": ["id"]}}
    ]
  },
  "output": "data/result.json"
}
```

Run it with:

```powershell
python scripts/web_data_pipeline.py --config config.json
```

## 3. Fingerprint browser

`BrowserSession` keeps one stable profile per account:

- user agent, locale, timezone, viewport, screen, languages
- hardware concurrency and device memory
- persistent cookies and Playwright storage state (local/session storage)
- optional proxy and per-account `user_data_dir`
- request/response capture with POST bodies for API replay

Use one fingerprint for login, page analysis, and API fetching. Changing
user agent / proxy mid-session is a common block signal. `FingerprintOptions`
can be generated from a seed, saved to JSON, and reloaded:

```python
from browser_session import FingerprintOptions

fp = FingerprintOptions.generate(seed=42)
fp.save("profiles/account-a.json")
```

## 4. CAPTCHA handling

`captcha_solver.py` detects common challenges in HTML:

- reCAPTCHA v2 / v3
- hCaptcha
- Cloudflare Turnstile
- Geetest
- image CAPTCHA (`captcha`, `verify_code`, `yanzhengma`, ...)

Solving modes:

1. Local OCR: `OcrCaptchaSolver` uses optional Pillow + pytesseract for
   image CAPTCHAs and needs no network.
2. Third-party service: `CaptchaSolver` uses the common submit-then-poll
   API (`in.php` / `res.php`) and works for image, reCAPTCHA, hCaptcha,
   Turnstile, and Geetest.
3. Manual fallback: `ManualCaptchaSolver` pauses a worker for a human when
   the product is allowed to wait for user input.

`AutoCaptchaSolver` tries OCR first for image challenges, then the
third-party service, then manual fallback. It also fills the response field
in the page through `BrowserSession.solve_captchas_auto()`.

Install the optional OCR stack with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_media_dependencies.ps1 -Install
```

`media_dependencies.py` checks for Pillow, pytesseract, and the system
`tesseract` binary and reports them as the `ocr` status key.
It also reports the optional web-fetch stack: `curl_cffi`, `cloudscraper`,
`httpx`, and `h2`.

Keep API keys encrypted in local config (Windows DPAPI / keyring), never in
source or plaintext config. Do not claim the pipeline bypasses every
challenge; many platforms require human confirmation.

## 5. Automatic security identification

`security_detector.py` classifies one HTTP response into known obstacle
types so the pipeline can decide the next compliant strategy without
showing a dialog:

- `cloudflare_challenge` / `cloudflare_blocked` - challenge or block pages
- `waf_blocked` - Akamai, Imperva, ModSecurity, and generic WAF wording
- `rate_limited` - 429 / Retry-After / rate-limit wording
- `captcha_required` - reCAPTCHA, hCaptcha, Turnstile, Geetest, image CAPTCHA
- `login_required` - 401 / 403 or login-wall wording
- `cookie_consent_wall` / `js_required` - browser-only walls
- `geo_blocked` - 451 / regional-restriction wording
- `server_error`, `empty_page`, `dynamic_page` - retry or browser-render hints

Each finding includes confidence, evidence, and a recommendation. The
aggregate report exposes `blocked`, `actions`, `needs_browser`,
`needs_proxy`, `needs_captcha`, and `needs_login`. The pipeline uses these
signals to retry, rotate proxy, open the fingerprint browser, solve
CAPTCHAs automatically, or skip a page while continuing the rest of the
job.

`WebDataPipeline` handles this automatically from config:

```json
{
  "security": {
    "enabled": true,
    "skip_blocked": true,
    "escalate_to_browser": true,
    "auto_handle": true
  }
}
```

With `escalate_to_browser: true`, pages blocked over HTTP are re-captured in
the fingerprint browser before they are discarded. API responses that end
in 4xx / 5xx now keep their status, headers, and a security report instead
of collapsing into a generic exception.

### Adaptive fetch backends

`scripts/smart_fetch.py` adds a `fetch` config section that automatically
switches HTTP transports when the security detector sees a Cloudflare
challenge / block, WAF block, rate limit, or CAPTCHA wall:

```json
{
  "fetch": {
    "backend": "auto",
    "auto_install": true,
    "order": ["curl_cffi", "cloudscraper", "httpx", "urllib"],
    "impersonate": "chrome",
    "cloudscraper": {
      "delay": 5,
      "browser": {"browser": "chrome", "platform": "windows", "mobile": false}
    },
    "flaresolverr": {
      "base_url": "http://127.0.0.1:8191",
      "max_timeout": 60000
    }
  }
}
```

Backend priorities:

- `curl_cffi` impersonates a real browser TLS stack (JA3 / JA4, HTTP/2,
  header order) without launching a browser.
- `cloudscraper` runs Cloudflare JS / Turnstile challenge solving through a
  requests-compatible session.
- `httpx` uses HTTP/2 connection pooling when `h2` is installed.
- `flaresolverr` forwards the request to a local FlareSolverr instance when
  configured; the returned `cf_clearance` / cookies are merged back into the
  session before the next backend tries the URL.
- `urllib` is the dependency-free fallback.

In `auto` mode, `auto_install` defaults to `true`: `smart_fetch.py` calls
`ensure_web_fetch_dependencies.py` on first use and downloads only the
missing optional packages. Set `"auto_install": false` to disable that.
To run it as a standalone one-shot command:

```powershell
python scripts/ensure_web_fetch_dependencies.py          # auto install
python scripts/ensure_web_fetch_dependencies.py --check  # report only
python scripts/ensure_web_fetch_dependencies.py --http-only  # skip stealth browsers
```

For the full runtime (Chromium, ffmpeg, pycryptodome, optional manifest
dependencies), use `python scripts/ensure_all_dependencies.py --install`.

The session keeps one user agent, proxy, and cookie jar across switches.
Cloudflare official docs state that `cf_clearance` is tied to the visitor
and device and that a challenge solve from a different IP than the original
request is not valid, so the pipeline never rotates proxy or UA after a
clearance is obtained. `cf_clearance` is time-bound (Challenge Passage,
default 30 minutes), and `__cf_bm` is the Bot Management session cookie that
smoothes the bot score; both are preserved and reused for later API calls.
Sidecar `analyze`, `crawl`, and `webdata` tasks also honor `payload.fetch`
when the caller supplies a `fetch` object.

### Deep browser escalation

For Managed Challenges / Turnstile that the HTTP layer cannot clear, the
pipeline can use a stealth browser instead of plain Playwright:

```json
{
  "browser": {
    "engine": "patchright",
    "stealth_engine": "nodriver",
    "browser_path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "auto_install": true,
    "headless": true,
    "challenge_timeout": 60000
  }
}
```

- `engine: "patchright"` makes `BrowserSession` use the undetected Patchright
  Playwright API instead of stock Playwright.
- `stealth_engine: "nodriver"` or `"drission_page"` runs a lightweight
  deep solver (`scripts/stealth_browser.py`) for blocked pages when the
  browser is not already enabled.
- `browser_path` points to an installed Chrome / Edge binary, and
  `auto_install` (default true) installs a missing engine package before
  the solver runs.
- `scripts/flaresolverr.py` can also be used as a standalone service client
  when a remote / Dockerized FlareSolverr is available.

The solved cookies are merged into the API session, so subsequent requests
keep the same `cf_clearance`, `__cf_bm`, user agent, and proxy that the
challenge solver produced.

### Cloudflare high-intensity challenge handling

`scripts/cloudflare_challenge.py` adds a dedicated high-intensity path on
top of the generic browser escalation. It recognizes the common Cloudflare
stages: `js_challenge`, `managed_non_interactive`, `turnstile_captcha`, and
`blocked`. The handler:

1. waits for the `cf_clearance` cookie instead of only watching the title;
2. polls the challenge iframe and clicks the Turnstile checkbox when
   present;
3. submits a third-party Turnstile token into the challenge textarea when a
   solver is configured;
4. reloads with backoff and, after repeated failure, returns
   `needs_new_session` so the pipeline can rotate proxy and retry in a
   fresh fingerprint browser.

It also tracks official Cloudflare signals: valid vs. expired
`cf_clearance`, `__cf_bm`, `Server: cloudflare`, `cf-mitigated`,
`cf-cache-status`, `cf-ray`, and optional `cf-bot-score` / `x-bot-score`
headers. Managed Challenges dynamically choose non-interactive or
interactive Turnstile verification based on browser signals; when a
high-intensity challenge cannot be cleared by the smart HTTP layer, the
pipeline escalates to the fingerprint browser.

Enable it with:

```json
{
  "cloudflare": {
    "enabled": true,
    "max_attempts": 3,
    "wait_timeout": 60000,
    "clearance_timeout": 30000,
    "auto_click": true,
    "solve_turnstile": true,
    "reload_before_retry": true,
    "rotate_proxy_on_fail": true,
    "reuse_clearance": true,
    "pin_proxy": true,
    "keep_bm_cookie": true,
    "clearance_passage_seconds": 1800,
    "max_rotation_attempts": 1
  }
}
```

When the challenge passes, the pipeline keeps the `cf_clearance` and
`__cf_bm` cookies, the browser user agent, and the pinned proxy, and reuses
all of them for subsequent API fetches so the clearance is not invalidated
by a different IP / UA / cookie state. When the handler repeatedly fails and
`rotate_proxy_on_fail` is true, the pipeline closes the browser session,
marks the proxy as failed, and retries the same URL in a fresh fingerprint
browser with the next proxy, up to `max_rotation_attempts`.

## 6. Deep crawling

`deep_crawler.py` recursively discovers pages from HTML links and sitemaps
with configurable depth, page count, same-host scope, include / exclude
patterns, robots.txt enforcement, and rate limiting:

```powershell
python scripts/deep_crawler.py --seed https://example.com/list `
  --max-depth 2 --max-pages 100 --same-host --output crawl.json
```

The crawler normalizes and deduplicates URLs, skips binary/media
extensions, honors `Disallow` rules and `Sitemap:` entries, and runs every
page through `security_detector.py`. Blocked pages are recorded with their
security report and skipped by default (`skip_blocked: true`), so one
Cloudflare / WAF / CAPTCHA page never stops the rest of the crawl.

Enable it inside the web data pipeline:

```json
{
  "crawl": {
    "enabled": true,
    "seeds": ["https://example.com/list"],
    "max_depth": 2,
    "max_pages": 100,
    "same_host": true,
    "include": ["/list", "/detail"],
    "exclude": ["/logout"],
    "sitemap": true,
    "respect_robots": true,
    "skip_blocked": true
  }
}
```

The pipeline summary then reports `crawl_pages`, `crawl_summary`,
`security_findings`, and per-kind security counts.

## 7. Page and API analysis

Static analysis (`page_data_parser.analyze_page`) extracts:

- title / meta / OpenGraph / Twitter metadata
- JSON-LD and `application/json` blocks
- Next.js, Nuxt, Apollo, and global-state JSON
- media URLs and API-looking fields inside JSON
- API endpoints from `fetch`, axios, XHR, jQuery, forms, preloads, scripts
- pagination fields (`page`, `total`, `nextCursor`, `hasMore`, ...)
- CAPTCHA challenges

Runtime analysis (`BrowserSession.capture_page_data`) records actual
`xhr` / `fetch` / WebSocket traffic with method, URL, status, headers,
request bodies, and response JSON. `api_client.build_api_specs()` converts
both into replayable specs.

```python
from api_client import ApiClient, build_api_specs
from browser_session import BrowserSession

session = BrowserSession()
session.start()
capture = session.capture_page_data("https://example.com/list")
specs = build_api_specs(capture)
client = ApiClient(min_interval=0.5, max_retries=3)
results = client.fetch_all(specs)
session.close()
```

### API analysis manifest

`api_analyzer.py` turns one or more captures into a reviewable manifest:

```powershell
python scripts/api_analyzer.py --input capture.json --output manifest.json
```

The manifest contains:

- discovered endpoints with method, URL, params, body, source, and score
- auth header names (values are redacted unless `--include-secrets`)
- candidate `pagination` config inferred from query keys and response keys
- list data paths found inside captured JSON responses
- summary counts for captured/static endpoints

The pipeline can write this manifest automatically with
`api.manifest_output` and can auto-apply inferred pagination when
`api.auto_pagination` is enabled (default true).

## 8. API fetching

`ApiClient` uses `MediaSession` so every call inherits:

- cookie persistence
- proxy support
- `RateLimiter` min-interval + jitter
- `RetryPolicy` exponential backoff with `Retry-After`
- optional adaptive throttle on 403 / 429 / 5xx

`fetch_all()` is sequential by default; set `concurrency > 1` only for
stateless public endpoints because concurrent workers use separate sessions
and do not share cookies.

Failed API calls (403 / 429 / 5xx) are no longer opaque: each
`ApiFetchResult` keeps `status`, `headers`, and a `security` report so the
UI and pipeline can show exactly why the call was blocked and what the next
action should be.

### Automatic pagination

Set `api.pagination` in the config to automatically walk all pages:

```json
{
  "type": "page",
  "param": "page",
  "page_size_param": "page_size",
  "page_size": 50,
  "start": 1,
  "max_pages": 100,
  "items_path": "items",
  "total_path": "total",
  "has_more_path": "hasMore"
}
```

Supported types:

- `page` - increments the query parameter by 1
- `offset` - increments by `page_size`
- `cursor` - follows `next_path` until it is empty

`items_path` tells the client where the records live inside each response.
When the server provides `total_path` or `has_more_path`, the client stops
early; otherwise it stops when a page has no records or `max_pages` is
reached. Browser-collected cookies are copied into the API session, so
logged-in API calls keep working after page capture.

## 9. Data processing

`data_processor.py` processes collected records with an ordered JSON step
list. Supported operations:

| op | params | effect |
|---|---|---|
| `select` | `fields` | keep only the listed dotted paths |
| `rename` | `mapping` | rename keys (`{"old": "new"}`) |
| `filter` | `conditions`, `operator` | keep records matching eq/ne/gt/gte/lt/lte/contains/in/regex/... |
| `sort` | `keys` | multi-key sort, `desc` supported |
| `dedupe` | `fields`, `keep` | remove duplicates by fields or whole record |
| `flatten` | `separator` | flatten nested dicts into dotted keys |
| `limit` | `value` | cap the number of records |
| `aggregate` | `by`, `ops` | group and sum/avg/min/max/count/count_distinct |
| `drop` | `fields` | remove top-level or dotted fields |
| `default` | `mapping` | fill missing/null fields with defaults |
| `convert` | `fields` | convert fields to int/float/str/bool |
| `map` | `fields` | copy or transform fields (lower/upper/strip/title/length/str/int/float/bool/json) and build `template` values |
| `replace` | `fields` | replace text or regex patterns inside fields |
| `join` | `path`, `on`, `type`, `prefix`, `fields` | left/inner join records from another JSON/JSONL/CSV file |

Input/output supports `.json`, `.jsonl`, and `.csv`:

```powershell
python scripts/data_processor.py --config pipeline.json --input data.json --output result.csv
```

## 10. Desktop UI integration

For any desktop UI language, run the sidecar and enqueue a task:

```json
{
  "kind": "webdata",
  "payload": {
    "config": {
      "pages": ["https://example.com/list"],
      "fetch": {"backend": "auto", "auto_install": true},
      "api": {"min_interval": 0.5, "max_retries": 3},
      "processing": {"steps": [{"op": "select", "params": {"fields": ["id", "name"]}}]},
      "output": "out/result.json"
    }
  }
}
```

The task result contains a summary (`api_specs`, `raw_records`,
`processed_records`, `output`). Long-running browser jobs must run in a
worker, never on the UI thread; show progress and failures in the log
center (UI-13). The sidecar reports live stages (`collect`, `discover`,
`fetch`, `process`, `save`, `done`) through the task queue progress field.
For real-time display, poll:

```text
GET /tasks/<id>/progress
GET /tasks/<id>/events?after=<event_index>
```

`/progress` returns the current percent, stage, and event list;
`/events` returns only events newer than `after` plus the next index, so a
desktop UI can poll once per second without re-reading the whole history.

## 11. Proxy pool and dynamic IP rotation

`scripts/proxy_pool.py` provides `ProxyPool` (round-robin or random) and
`ProxyPoolStore` (named pools persisted in one JSON file). A pool rotates
on retry and puts failed proxies into cooldown after a configurable number
of failures:

```json
{
  "proxy_pool": {
    "proxies": ["http://p1:8080", "http://p2:8080"],
    "strategy": "round_robin",
    "max_failures": 3,
    "cooldown_seconds": 60
  }
}
```

Pass a pool name instead when the sidecar owns the store:

```json
{ "proxy_pool": "main" }
```

`MediaSession` and `ApiClient` accept `proxy_pool` directly, so API fetches
rotate automatically. Browser sessions pin one proxy per session to avoid
mid-session IP changes. Sidecar endpoints:

```text
GET  /proxy-pools
GET  /proxy-pools/<name>
POST /proxy-pools
DELETE /proxy-pools/<name>
```

## 12. Multi-account session management

`scripts/account_manager.py` stores named account profiles with Playwright
storage state, cookie files, browser profile dirs, proxies, headers, and
login selectors. A task leases one account at a time through the sidecar:

```json
{
  "kind": "webdata",
  "payload": {
    "account": "account-a",
    "config": {
      "pages": ["https://example.com/list"],
      "api": {"max_retries": 3}
    }
  }
}
```

Concurrent workers never share the same account session, and a failed
account enters cooldown before it can be leased again. Manage profiles:

```text
GET  /accounts
POST /accounts
DELETE /accounts/<name>
POST /accounts/<name>/acquire
POST /accounts/<name>/release
```

## 13. Scheduled tasks and automatic retry

`scripts/task_scheduler.py` turns recurring jobs into queue tasks. Supported
schedule shapes:

```json
{"type": "interval", "seconds": 3600}
{"type": "daily", "time": "09:30"}
{"type": "cron", "minute": "*/15", "hour": "*"}
{"type": "once", "at": "2026-08-08T09:30:00+08:00"}
```

Create and manage schedules through the sidecar:

```text
GET  /schedules
POST /schedules
DELETE /schedules/<id>
POST /schedules/<id>/pause
POST /schedules/<id>/resume
```

Retries are already durable in `scripts/task_queue.py`: each task carries
`max_attempts`, and failures with remaining attempts go back to `queued`
with `run_after`. Per-task payloads can tune behavior with
`"auto_retry": false` and `"retry_delay_seconds": 30`.

## 14. Completion notifications

`scripts/notifier.py` sends desktop toast, SMTP email, and webhook
notifications when a task succeeds or fails. Pass a JSON config to the
sidecar with `--notify-config`:

```json
{
  "desktop": {"enabled": true},
  "email": {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "username": "sender@example.com",
    "password": "secret",
    "from_addr": "sender@example.com",
    "to": ["ops@example.com"]
  },
  "webhook": {
    "url": "https://example.com/hooks/task",
    "headers": {"X-Token": "abc"}
  }
}
```

Channels are best-effort: one failing channel never fails the worker task.
The UI can check enabled channels with `GET /notifications/status`, send a
test with `POST /notifications/test`, and disable notifications for one
task with `"notify": false` in its payload.

## 15. Compliance checklist

- Confirm the user has permission to access and store the data.
- Honor robots.txt and platform terms where possible.
- Keep credentials encrypted and local.
- Keep rate limits on by default; expose a global stop switch.
- Log 403 / 429 / CAPTCHA failures with a suggested next step instead of
  hiding them.
- Do not market the tool as a CAPTCHA bypass, anti-ban, or stealth tool.
- Store source code before packaging; never let a build delete the source
  directory.
