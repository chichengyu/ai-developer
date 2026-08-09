# Web data pipeline playbook

## Table of contents

- [Pipeline shape](#pipeline-shape)
- [Minimal config](#minimal-config)
- [Adaptive fetch backends](#adaptive-fetch-backends)
- [Cloudflare mechanisms and handling](#cloudflare-mechanisms-and-handling)
- [Stealth browser escalation](#stealth-browser-escalation)
- [Full-chain fingerprint binding](#full-chain-fingerprint-binding)
- [Deep challenge bypass strategy](#deep-challenge-bypass-strategy)
- [Vendor-specific WAF intelligence](#vendor-specific-waf-intelligence)
- [Universal challenge cookies](#universal-challenge-cookies)
- [Challenge cookie bank](#challenge-cookie-bank)
- [Alternate access fallback](#alternate-access-fallback)
- [Dynamic anti-bot policy](#dynamic-anti-bot-policy)
- [Vendor cookie validation and token injection](#vendor-cookie-validation-and-token-injection)
- [Slider and audio CAPTCHAs](#slider-and-audio-captchas)
- [CAPTCHA queue](#captcha-queue)
- [Challenge snapshots and replay](#challenge-snapshots-and-replay)
- [Adaptive bypass orchestrator](#adaptive-bypass-orchestrator)
- [Patch camouflage](#patch-camouflage)
- [End-of-run summary](#end-of-run-summary)
- [Production controls](#production-controls)
- [Real-site acceptance suite](#real-site-acceptance-suite)
- [Nopecha demo probe](#nopecha-demo-probe)
- [Production proxy pools](#production-proxy-pools)
- [Current IP detection](#current-ip-detection)
- [Automatic login](#automatic-login)
- [HLS acquisition](#hls-acquisition)
- [Concurrent media crawl and resume](#concurrent-media-crawl-and-resume)
- [Automatic block diagnosis](#automatic-block-diagnosis)
- [Autonomous async crawl](#autonomous-async-crawl)
- [Advanced anti-bot patch bank](#advanced-anti-bot-patch-bank)
- [Deep Turnstile container handling](#deep-turnstile-container-handling)
- [Security detection](#security-detection)
- [Deep crawling](#deep-crawling)
- [Page/API analysis](#pageapi-analysis)
- [API fetching and pagination](#api-fetching-and-pagination)
- [Data processing](#data-processing)
- [Dependency bootstrap](#dependency-bootstrap)
- [Script index](#script-index)
- [Compliance](#compliance)

## Pipeline shape

```text
config.json
  -> adaptive HTTP fetch (curl_cffi / tls_client / cloudscraper / httpx / flaresolverr / urllib)
  -> security classification
  -> optional stealth browser loop (patchright / camoufox / scrapling / nodriver /
     seleniumbase / undetected_chromedriver / drission_page / selenium)
  -> page/API analysis
  -> rate-limited API fetching with cookies
  -> declarative data processing
  -> JSON / JSONL / CSV output
```

## Minimal config

```json
{
  "pages": ["https://example.com/list"],
  "fetch": {"backend": "auto", "auto_install": true},
  "api": {"min_interval": 0.5, "max_retries": 3},
  "processing": {
    "steps": [
      {"op": "select", "params": {"fields": ["id", "name", "price"]}},
      {"op": "filter", "params": {"conditions": [{"field": "price", "op": "gte", "value": 10}]}}
    ]
  },
  "output": "data/result.json"
}
```

Run:

```powershell
python scripts/web_data_pipeline.py --config config.json
```

## Adaptive fetch backends

`smart_fetch.py` exposes `SmartFetchSession` and `create_fetch_session()`.
When a backend returns a Cloudflare challenge / block, WAF block, rate
limit, or CAPTCHA wall, the next installed backend is tried automatically.
When every HTTP transport fails and a `browser` config is present, the
session escalates to a stealth browser loop and merges solved cookies into
the same session so later API calls reuse the clearance.

```json
{
  "fetch": {
    "backend": "auto",
    "auto_install": true,
    "order": ["curl_cffi", "cloudscraper", "httpx", "urllib"],
    "impersonate": "chrome",
    "browser": {
      "engine": "auto",
      "headless": true,
      "max_attempts": 3,
      "retry_delay": 2,
      "rotate_proxy_on_fail": true
    },
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

- `curl_cffi` impersonates a real browser TLS stack (JA3/JA4, HTTP/2,
  header order).
- `tls_client` impersonates browser TLS from the Go tls-client library.
- `cloudscraper` runs Cloudflare JS / Turnstile solving.
- `httpx` uses HTTP/2 connection pooling when `h2` is installed.
- `flaresolverr` forwards to a local FlareSolverr instance when configured.
- `browser` runs the stealth browser loop as the final fallback.
- `urllib` is the dependency-free fallback.

The session keeps one user agent, proxy, and cookie jar across switches.
When a valid `cf_clearance` exists for the host, an embedded Turnstile widget
is treated as already passed. A solved browser result is returned as HTML and
its cookies are merged back into the HTTP session.

## Cloudflare mechanisms and handling

Cloudflare official behavior relevant to this pipeline:

- `cf_clearance` proves the visitor passed a challenge and is tied to the
  visitor/device.
- A challenge solved from a different IP than the original request is not
  valid, so keep proxy and UA stable after clearance.
- `cf_clearance` is time-bound (Challenge Passage, default 30 minutes).
- `__cf_bm` is the Bot Management session cookie and should be reused with
  the clearance.
- Managed Challenges choose non-interactive or interactive Turnstile based
  on browser signals.

`cloudflare_challenge.py` tracks:

- `cf_clearance` value, expiry, and validity
- `__cf_bm` value and expiry
- `cf-ray`, `cf-mitigated`, `cf-cache-status`, optional bot-score headers

Example:

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
    "clearance_passage_seconds": 1800
  }
}
```

## Stealth browser escalation

`stealth_browser.py` solves Managed Challenges / Turnstile with:

- `patchright` -- undetected Playwright API
- `camoufox` -- patched anti-fingerprint Firefox browser
- `scrapling` -- stealth fetcher with built-in Cloudflare solving
- `nodriver` -- CDP-only Chromium automation
- `seleniumbase` -- SeleniumBase UC / CDP mode
- `undetected_chromedriver` -- patched ChromeDriver
- `drission_page` -- DrissionPage Chromium automation
- `selenium` -- Selenium WebDriver with stealth injection

`--engine auto` tries every installed engine in order. Each round can
rotate proxy on failure and retries until `cf_clearance` or non-challenge
content appears.

CLI:

```powershell
python scripts/stealth_browser.py --url "https://target.example/" --engine auto --engine-order patchright,camoufox,scrapling --browser-path "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --no-headless
python scripts/stealth_browser.py --check
```

CLI flags include `--url`, `--engine`, `--browser-path`, `--engine-order`,
`--max-attempts`, `--retry-delay`, `--rotate-proxy-on-fail`,
`--headless/--no-headless`, `--headless-fallback/--no-headless-fallback`,
`--storage-state`, and `--check`. With `--engine auto` it tries each
installed engine in order, rotates proxy on failure, and loops until a
challenge cookie or non-challenge content appears.

Pipeline config:

```json
{
  "browser": {
    "engine": "auto",
    "stealth_engine_order": [
      "patchright",
      "camoufox",
      "scrapling",
      "nodriver",
      "seleniumbase",
      "undetected_chromedriver",
      "drission_page",
      "selenium"
    ],
    "max_attempts": 3,
    "retry_delay": 2,
    "rotate_proxy_on_fail": true,
    "browser_path": "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "auto_install": true,
    "headless": false,
    "headless_fallback": true,
    "storage_state": "state/account.json",
    "challenge_timeout": 60000
  }
}
```

Solved cookies are merged back into the API session so later requests reuse
the same `cf_clearance`, `__cf_bm`, UA, and proxy.

`headless_fallback: true` retries the same engine in headed mode when the
headless attempt stays on a challenge, which is the most common fix for
headless-browser detection. `storage_state` reuses cookies and local
storage across patchright / camoufox runs so a solved clearance does not
have to be re-earned for every deep-crawl page. Managed Challenge clicks
use human-like mouse movement and fall back through visible checkbox
labels, challenge buttons, Cloudflare iframes, and nested Shadow DOM.

## Full-chain fingerprint binding

Use one named profile for every layer instead of independent fingerprints.
`fingerprint_binding.py` exposes `chrome126`, `chrome124`, `edge126`,
`firefox127`, and `safari17`.

```json
{
  "fingerprint_binding": "chrome126",
  "fetch": {
    "backend": "auto",
    "fingerprint_binding": "chrome126",
    "browser": {
      "engine": "auto",
      "headless": true
    }
  }
}
```

`SmartFetchSession` uses the binding for its HTTP headers and TLS
impersonation. `FingerprintManager` and `BrowserSession` use the same binding
for user agent, locale, timezone, and browser context. `stealth_browser.py`
passes the binding into each engine and prefers the binding's compatible
engine order. `validate()` reports obvious mismatches, and
`binding_report()` includes the resolved profile for acceptance evidence.

## Deep challenge bypass strategy

The pipeline treats a challenge as a state machine instead of one HTTP
response:

1. `extract_cloudflare_state()` classifies the stage from body markers plus
   `cf-mitigated`, `cf-chl-*`, `cf-challenge`, `cf-ray`, bot-score, and
   `__cf_bm` / `cf_clearance` cookies.
2. `CloudflareChallengeHandler.recommended_action()` chooses `wait`,
   `click`, `solve`, or `rotate` for the current stage.
3. The handler waits for the challenge widget to render, tries a
   human-like checkbox click, and only then uses provider token injection.
4. Turnstile tokens are read from normal DOM, every frame, nested iframes,
   and Shadow DOM, and provider tokens can fire dotted callback paths such
   as `app.captcha.onToken`.
5. One proxy is pinned for the whole request (`pin_proxy()`), so switching
   from `curl_cffi` to `cloudscraper` to a stealth browser does not change
   the IP that `cf_clearance` is bound to.
6. The challenge variant is fingerprinted from vendor, stage, body markers,
   iframe URLs, script paths, cookies, and header signals, then recorded in
   the adaptive policy store so a rotated challenge gets a fresh strategy.

`challenge_evolution.py` produces the stable `signature` used by
`adaptive_policy.py`. When Cloudflare, DataDome, or Akamai rotates its
challenge DOM, the old signature no longer matches and `bypass_engine.py`
reports `new <vendor> challenge variant <signature>` before starting the
browser round.

A result is treated as solved when `cf_clearance` is present even if the
last DOM snapshot still contains challenge markup; the HTTP verification
step then confirms the real page. The solver also clicks Managed Challenge
iframes that expose no standard Turnstile sitekey and reloads with a
cache-busted URL when Cloudflare swaps to a new Managed Challenge
script/cookie stage.

## Challenge snapshots and replay

`challenge_replay.py` saves blocked challenge evidence to
`reports/challenges/<host>/<timestamp>-<signature>.html` plus a JSON
metadata file containing the variant fingerprint, headers, cookies, status,
and original URL. On a later run you can fingerprint a snapshot and compare
it with known signatures:

```powershell
python scripts/challenge_replay.py --meta reports/challenges/example.com/20260809T...-<signature>.json
python scripts/challenge_replay.py --html challenge.html --vendor datadome
python scripts/challenge_replay.py --snapshot-dir reports/challenges --list
```

`vendor_solver.py` validates Akamai `_abck` (non-empty, not `-1~`,
unexpired), DataDome `datadome` tokens, and AWS WAF / PerimeterX response
fields; it can inject provider tokens and solve sliders inside DataDome,
Geetest, and yidun iframes.

`stealth_browser.py --check` now reports installed engines, detected browser
binaries, and preflight status:

```powershell
python scripts/stealth_browser.py --check
```

Run that check before a real strong-anti-bot acceptance baseline. The
acceptance report also includes `stealth_preflight`.

## Adaptive bypass orchestrator

`bypass_engine.py` is the single-call entry point for the whole strategy
loop:

```python
from bypass_engine import run_bypass

result = run_bypass(
    "https://target.example/",
    {
        "fingerprint_binding": "chrome126",
        "fetch": {"backend": "auto", "auto_install": False},
        "browser": {"engine": "auto", "headless": True},
        "proxy_pool": {"min_pool_size": 5, "source": {"url": "..."}},
        "captcha_solver": solver,
    },
    timeout=30,
    max_rounds=2,
)
```

It first tries HTTP with the binding, then picks browser engines based on
the Cloudflare stage:

- Turnstile + Firefox binding prefers `camoufox` / `scrapling`.
- Turnstile + Chrome binding prefers `patchright` / `nodriver`.
- Managed / JS challenges use the binding's compatible engine list.

After a browser solve, cookies are merged back into an HTTP session pinned
to the same proxy, and the result is verified before reporting success.
Stealth browser engines receive `captcha_solver` so provider Turnstile
tokens can be used inside `patchright` / `camoufox` loops.

The orchestrator also runs vendor-stage detection (`datadome_captcha`,
`akamai_sensor`, `cloudflare_managed`, etc.) and consults the policy store
by exact challenge signature, so known variants reuse the winning engine
order while unknown variants trigger the full browser strategy.

## Vendor-specific WAF intelligence

`waf_vendor.py` classifies the major bot-management / WAF vendors beyond
Cloudflare:

- DataDome (`datadome` cookies / `x-datadome`)
- Akamai Bot Manager (`_abck`, `ak_bmsc`, `bm_sz`)
- PerimeterX / HUMAN (`_px3`, `_pxhd`, `px-captcha`)
- Shape Security (`__shape`, `shape-api`)
- Kasada (`kasad`, `kpsdk`)
- Imperva / Incapsula (`incap_ses_*`, `visid_incap_*`, `x-iinfo`)
- AWS WAF (`awswaf_*`, `aws-waf-token`, `captcha.awswaf.com`)
- F5 BIG-IP ASM (`TS*`, `x-wa-info`)
- Alibaba Cloud WAF (`acw_tc`, `aliyungf_tc`)
- Arkose / FunCaptcha (`funcaptcha`, `arkoselabs`)
- Fastly (`server: fastly`, `x-fastly-request-id`)
- Sucuri (`x-sucuri-id`, `x-sucuri-block`)
- Radware (`x-rdwr`, `radware captcha`)
- Reblaze (`x-reblaze`, `rbzid`)
- StackPath (`x-stackpath`, `stackpath waf`)
- Tencent Cloud WAF (`x-waf-*`, `qcloud`, `t-sec`)

Each vendor maps to its known challenge cookies, recommended TLS
impersonation profile, and browser-engine order. `security_detector.py`
reports vendor-specific kinds (`datadome_challenge`, `akamai_challenge`,
`perimeterx_challenge`, etc.) so logs and metrics show the actual wall. Each
detection includes a `challenge_stage` and a stable `signature` that changes
when DataDome / Akamai / Cloudflare rotate iframe URLs, script paths,
cookies, or header signals.

## Universal challenge cookies

`stealth_browser.py` no longer waits only for `cf_clearance`. Any known
vendor challenge cookie (`cf_clearance`, `datadome`, `_abck`, `ak_bmsc`,
`_px3`, `_pxhd`, `incap_ses_*`, `awswaf_*`, `TS*`, and more) triggers the
same reload-and-verify loop. A page can still contain challenge markup right
after the cookie appears; the browser reloads it up to two times and then
lets the HTTP verification step confirm the real content with the solved
cookies.

## Challenge cookie bank

`challenge_cookie_bank.py` keeps solved challenge cookies per host in a
small JSON store so a later run can reuse a still-valid `cf_clearance`,
`datadome`, `_abck`, `_px3`, or other vendor cookie before launching a
browser. The bank filters by host, honors cookie/entry expiry, writes
atomically, and is thread-safe.

```json
{
  "cookie_store_path": "state/challenge-cookies.json"
}
```

`bypass_engine.py` loads the bank before the first HTTP attempt (a hit
becomes `http:cookie_bank`) and saves the solved cookie set after a verified
browser pass. `stealth_browser.py` also accepts `cookie_store_path`
directly. Region/country-constrained proxy selection never falls back to the
current IP, so a requested geo policy is not silently violated.

## Alternate access fallback

`alternate_access.py` probes a bounded set of legitimate variants before
escalating to a browser: bare/www hosts, `m.` / `amp.` hosts, `/feed`,
`/rss`, `/sitemap.xml`, `/wp-json/`, `/graphql`, JSON suffixes, JSON
queries, and alternate user agents (mobile, Googlebot, feed readers, XHR).
Only a non-blocked `2xx` response counts as passed.

```json
{
  "alternate": {
    "enabled": true,
    "include": ["feed", "json", "query", "headers"],
    "max_variants": 8,
    "timeout": 3
  }
}
```

`bypass_engine.py` runs this probe after the first HTTP failure, so common
walls that protect only the canonical HTML route are solved without
launching a browser at all. `media_crawler.py`, `autonomous_crawler.py`,
and `web_data_pipeline.py` run the same fallback before browser escalation.

## Dynamic anti-bot policy

`adaptive_policy.py` records per-host, per-stage, per-engine outcomes plus
the challenge vendor/signature, weights recent samples higher, and re-orders
the browser strategy on later runs. A brand-new signature is reported as a
new challenge variant before the browser round.

```json
{
  "adaptive_policy_path": "state/adaptive-policy.jsonl"
}
```

`bypass_engine.py` reads and updates this store automatically, so the stack
learns which engine works for a target as Cloudflare changes its behavior.

## Vendor cookie validation and token injection

`vendor_solver.py` validates the cookie that actually matters per vendor:

- Akamai `_abck` must be non-empty, not `-1~`-blocked, and unexpired
- DataDome `datadome` must be a real token, not placeholder values
- AWS WAF `aws-waf-token` and PerimeterX response fields must be non-empty

It also injects provider tokens into vendor-specific fields
(`aws-waf-token`, `px-captcha-response`, `fc-token`, etc.) and solves
sliders inside DataDome / Geetest / yidun iframes.

## Slider and audio CAPTCHAs

`slider_solver.py` detects Geetest / yidun / slide-verify / generic slider
containers and drags the handle with human-like easing and jitter.
`captcha_solver.py` detects audio CAPTCHA elements and provides
`AudioCaptchaSolver` with a provider or local speech-to-text callback.
`BrowserSession.solve_captchas_auto()` handles slider directly in the
browser and routes audio through the configured audio solver. CAPTCHA
detection also recognizes Arkose / FunCaptcha, DataDome, PerimeterX, AWS
WAF, and reCAPTCHA Enterprise. The 2captcha-style adapter gains
`solve_funcaptcha()` and `solve_recaptcha_enterprise()`.

## CAPTCHA queue

`captcha_queue.py` runs CAPTCHA provider calls through a worker pool with
priorities, retries, backoff, and status tracking:

```python
from captcha_queue import CaptchaTaskQueue, ConcurrentCaptchaSolver

queue = CaptchaTaskQueue(solver, workers=3)
concurrent = ConcurrentCaptchaSolver(queue)
future = queue.submit("solve_turnstile", "sitekey", "https://example.com/")
```

## Patch camouflage

The stealth patch bank now includes deeper fingerprint camouflage:

- cleanup of `cdc_*`, `$cdc_*`, `__webdriver_*`, `__selenium_*`,
  `domAutomation`, `callPhantom`, and other automation residue
- WebGL parameter spoofing for `MAX_VIEWPORT_DIMS`,
  `MAX_RENDERBUFFER_SIZE`, and debug renderer info
- deterministic Canvas / OffscreenCanvas seed noise and WebGL2
  debug-renderer spoofing
- deterministic AudioContext / AnalyserNode frequency noise
- stable `speechSynthesis.getVoices()` results that match the locale
- timezone-aware `Date.getTimezoneOffset()`, `Date.toString()`,
  `toTimeString()`, and `Intl.DateTimeFormat` values that match the binding
- Chrome-only surfaces (`chrome.runtime`, plugins, `deviceMemory`,
  `userAgentData`, `pdfViewerEnabled`) are skipped for Firefox / Safari
- full `screen` geometry plus `userAgentData.getHighEntropyValues()` and
  `fullVersionList` coherence
- browser launch flags that disable background networking, component
  updates, client-side phishing checks, sync, hang monitoring, mock
  keychain, and pin the profile timezone

These values are rendered from the active `FingerprintBinding`, so
`patchright`, `nodriver`, `DrissionPage`, Selenium, and the HTTP/TLS layer
all describe the same browser.

## End-of-run summary

The media crawler, autonomous crawler, web data pipeline, and acceptance
suite all end with a `run_summary` JSON report. The report always includes:

- `save_paths`: every output directory / JSONL / SQLite / report file with
  absolute path, existence, and byte size
- `resources`: every page and media resource with status
  (`success` / `failed` / `blocked` / `discovered` / `skipped`), saved
  path, size, SHA-256, status code, and error
- `resource_counts`: status totals
- `summary`: the original run counters

Enable a persisted report with:

```json
{
  "summary_output": "state/run-summary.json"
}
```

`run_summary.py` also has `jsonl_report()` to replay an existing crawl
JSONL and rebuild the resource list after a crash or shutdown.

## Production controls

The following modules turn the pipeline into a long-running production
worker:

- `adaptive_policy.py`: JSONL-backed strategy memory. Record success/failure
  per host/stage/engine/vendor/signature with recency weighting, then
  `recommend()` re-orders future runs and reports known/unknown variants.
- `slider_solver.py`: Geetest / yidun / generic slider detection plus
  human-like mouse drag solving inside a real browser.
- `captcha_solver.py`: audio CAPTCHA detection and `AudioCaptchaSolver`
  with provider or speech-to-text callback.
- `captcha_queue.py`: concurrent provider queue with priority, retry,
  backoff, status, and a `ConcurrentCaptchaSolver` facade.
- `metrics.py`: `MetricsRegistry` counters/gauges/histograms, Prometheus
  text exposition, and `AlertManager` rules for failure rate, proxy
  depletion, and new challenge variants.
- `daemon.py`: PID file, heartbeat, crash restart, timeout, and clean
  SIGINT/SIGTERM shutdown for crawler commands.

Example daemon invocation:

```powershell
python scripts/daemon.py --command python scripts/media_crawler.py --config crawl.json --pid-file state/daemon.pid --log-file state/daemon.log --heartbeat-file state/daemon.heartbeat
python scripts/daemon.py --status --pid-file state/daemon.pid
python scripts/daemon.py --stop --pid-file state/daemon.pid
```

`bypass_engine.py` emits `task_total`, `task_success`, `task_failed`,
`proxy_available`, `bypass_duration_ms`, `variant_total`, and
`variant_new`.

## Real-site acceptance suite

The local tests validate protocol behavior, not whether a real target is
actually reachable. `acceptance_suite.py` runs the full stack against
targets you own or are authorized to test.

```json
{
  "fingerprint_binding": "chrome126",
  "fetch": {"backend": "auto", "auto_install": false},
  "browser": {"engine": "auto", "headless": true},
  "captcha": {"provider": "capsolver", "api_key_env": "CAPSOLVER_API_KEY"},
  "proxy_pool": {
    "min_pool_size": 5,
    "source": {
      "url": "https://provider.example/list",
      "format": "json",
      "json_path": "data",
      "country_field": "country",
      "city_field": "city"
    }
  },
  "targets": [
    {
      "name": "cloudflare-basic",
      "url": "https://example.com/",
      "kind": "page",
      "expected_status": [200],
      "expected_marker": "Example Domain",
      "checks": ["http", "browser"],
      "skip_without": ["browser"]
    },
    {
      "name": "turnstile-login",
      "url": "https://example.com/login",
      "kind": "cloudflare",
      "expected_status": [200],
      "skip_without": ["browser", "proxy"]
    },
    {
      "name": "captcha-provider",
      "url": "https://example.com/",
      "kind": "captcha",
      "sitekey": "0x...",
      "skip_without": ["captcha"]
    }
  ]
}
```

```powershell
python scripts/acceptance_suite.py --config acceptance.json --report reports/acceptance.json
python scripts/acceptance_suite.py --config acceptance.json --dry-run
python scripts/acceptance_suite.py --config acceptance.json --offline
python scripts/acceptance_suite.py --self-test
```

The report includes backend status, installed stealth engines, resolved
fingerprint binding, proxy pool health, CAPTCHA balance, per-target security
classification, challenge signatures, duration, and saved failure snapshots
when `snapshot_dir` is configured.

A checked-in real-target config is `acceptance.real.config.json`; keep
generated reports under `reports/`.

## Nopecha demo probe

`nopecha_probe.py` is a one-command smoke test for the nopecha.com
Cloudflare full-page demo. It reports the real public IP (STUN) versus the
HTTP egress IP, runs a stealth browser engine against the demo page, and
prints a compact JSON verdict with challenge stage, `cf_clearance` evidence,
and any public IP visible on the page.

```powershell
python scripts/nopecha_probe.py --ip-only
python scripts/nopecha_probe.py --engine auto --headless --max-attempts 1
python scripts/nopecha_probe.py --engine patchright --no-headless --no-proxy --save reports/nopecha.json
```

Use `--no-proxy` when the machine's HTTP egress differs from the real local
public IP, so the browser test bypasses an unintended system proxy.

## Production proxy pools

`proxy_pool.py` now supports SOCKS4/SOCKS5/SOCKS5H strings, embedded
authentication, `default_auth`, country/city/region filtering, provider
sources, and automatic refill after failed proxies are removed.

```json
{
  "proxy_pool": {
    "proxies": ["socks5://user:pass@127.0.0.1:1080"],
    "default_auth": "user:pass",
    "min_pool_size": 10,
    "refill_threshold": 5,
    "auto_remove_on_fail": true,
    "country": "US",
    "source": {
      "url": "https://provider.example/api/list",
      "method": "GET",
      "headers": {"Authorization": "Bearer ${PROXY_API_TOKEN}"},
      "format": "json",
      "json_path": "data.proxies",
      "proxy_field": "proxy",
      "country_field": "country",
      "city_field": "city",
      "auth": "user:pass",
      "sync": true,
      "timeout": 20
    }
  }
}
```

When `min_pool_size` / `refill_threshold` is set and the active pool falls
below the threshold, `get_proxy()` and `get_proxy_for()` attempt one source
refresh. `refresh_from_source()` can also be called explicitly or by the
background health monitor. `report_failure()` removes a proxy permanently
when `auto_remove_on_fail` is enabled and then attempts a refill.

## Current IP detection

When no residential proxy or CAPTCHA key is configured, the pipeline
defaults to the current IP (`current_ip`) and continues with browser
auto-click instead of skipping or failing the whole run; CAPTCHA-only
acceptance targets are reported as skipped rather than failed. The
current-IP detector prefers STUN (UDP reflexive address) over HTTP echo
services, so it reports the real public IP even when the Codex/cloud HTTP
egress goes through a proxy. `scripts/current_ip.py` shows both values.
`current_ip` is detected by STUN reflexive address first (the real home/NAT
public IP), with HTTP echo IP shown separately as `http_egress_ip` so a
Codex/cloud egress address is never mistaken for the local public IP.

## Automatic login

`login_detector.py` scans a page for:

- username / email / phone / account inputs
- password inputs
- submit buttons and login-looking button text
- login/sign-in links
- CAPTCHA inputs
- logged-in markers (logout, account center, welcome text)

`BrowserSession.auto_login()` uses those selectors when the caller does not
provide exact ones. The pipeline config can be fully declarative:

```json
{
  "browser": {
    "login": {
      "url": "https://example.com/login",
      "username": "user",
      "password": "secret",
      "auto": true,
      "success_markers": ["welcome", "退出登录"],
      "storage_state": "data/account-state.json",
      "cookies_path": "data/cookies.json"
    }
  }
}
```

Existing cookies or storage state are loaded first; login is only attempted
when the page does not already look authenticated.

## HLS acquisition

`hls_client.py` provides:

- master playlist resolution
- variant selection by preferred height or max bandwidth
- media playlist and `EXT-X-MAP` init segment handling
- AES-128 / AES-256 key fetch and decrypt (requires `cryptography`)
- segment download with `Range`/`BYTERANGE` support
- optional combined `.ts` / fragmented `.mp4` output

CLI:

```powershell
python scripts/hls_client.py --url "https://example.com/master.m3u8" --output data/media --height 1080
python scripts/hls_client.py --url "https://example.com/master.m3u8" --output data/media --height 720 --combine
```

Pipeline config:

```json
{
  "media": {
    "enabled": true,
    "output_dir": "data/media",
    "preferred_height": 1080,
    "max_bandwidth": 8000000,
    "include_segments": true,
    "combine": true,
    "decrypt": true
  }
}
```

`BrowserSession` captures HLS requests from runtime network traffic, and
`PageCapture.hls_urls()` also returns HLS URLs found in HTML and embedded
JSON. The pipeline downloads every discovered `m3u8` stream.

## Concurrent media crawl and resume

`media_crawler.py` is a standalone resumable crawler:

- extracts image / video / audio / HLS from HTML and embedded JSON
- accepts direct image/video/audio/HLS URL seeds and downloads them directly
- follows same-host links, robots.txt, and sitemaps
- uses thread pools for pages and media with global rate limits
- retries with exponential backoff and rotates proxies on failure
- appends every page/media result to JSONL immediately
- resumes from `jsonl_path` when `resume: true`, skipping completed work
- escalates Cloudflare blocks through `stealth_browser.py` when configured
- records SHA-256 for downloaded assets for content deduplication
- streams large resources through `resource_downloader.py` with Range resume
- persists resource state in SQLite (`resource_store.py`) for retry and
  content-level deduplication
- `auto_adjust_max_pages` expands the page budget when a discovery layer
  contains more links than `max_pages`, bounded by `max_pages_cap`
- downloaded files keep the original URL/content-disposition extension and
  fall back to the Content-Type extension when the URL has no extension
- `resource_store.py` supports expiration cleanup with optional file
  deletion

Example config:

```json
{
  "seeds": ["https://example.com/gallery"],
  "max_depth": 3,
  "max_pages": 500,
  "max_workers": 8,
  "min_interval": 0.4,
  "max_retries": 3,
  "download_media": true,
  "media_types": ["image", "video", "audio", "hls"],
  "output_dir": "media",
  "jsonl_path": "crawl.jsonl",
  "resume": true,
  "proxy_health_check": true,
  "proxy_health_url": "https://example.com",
  "proxy_pool": {
    "proxies": ["http://p1:8080", "http://p2:8080"]
  }
}
```

```powershell
python scripts/media_crawler.py --config media_crawl.json
```

## Automatic block diagnosis

`block_diagnoser.py` combines:

- HTTP status code
- `Retry-After` and auth/CDN headers
- Cloudflare markers: `cf-ray`, `cf-mitigated`, challenge stage, sitekey
- WAF / rate limit / CAPTCHA / login / geo detection from
  `security_detector.py`
- robots.txt allow/deny and sitemap URLs

The diagnosis recommends `challenge_retry`, `proxy_recommended`,
`browser_recommended`, and `captcha_recommended` actions. The media crawler
uses those signals to rotate proxy, retry, or launch a stealth browser.

## Autonomous async crawl

`autonomous_crawler.py` targets unattended million-scale runs:

- asyncio scheduler with `max_concurrency`
- `UrlDeduplicator` backed by SQLite WAL, so seen URLs survive restarts
- `HumanBehavior` for UA rotation and randomized pacing
- `AutoDataExtractor` for tables, repeated blocks, embedded JSON, schema
  inference, and record validation
- structure signature changes trigger automatic DOM reparse
- dynamic rendering through the stealth browser loop when blocked
- proxy pool rotation with exponential backoff
- JSONL output for every page, record, media URL, block, and error

```json
{
  "seeds": ["https://example.com/"],
  "max_urls": 10000000,
  "max_concurrency": 32,
  "min_delay": 0.2,
  "max_delay": 1.2,
  "respect_robots": true,
  "sitemap": true,
  "dynamic_render": true,
  "url_db_path": "state/urls.sqlite3",
  "jsonl_path": "state/crawl.jsonl",
  "proxy_health_check": true,
  "proxy_health_url": "https://example.com",
  "proxies": ["http://p1:8080", "http://p2:8080"]
}
```

```powershell
python scripts/autonomous_crawler.py --config autonomous.json
```

## Advanced anti-bot patch bank

`stealth_patch_bank.py` exposes composable JS patches that can be injected
into Playwright/Patchright contexts and Selenium CDP sessions:

- WebDriver, Chrome runtime, plugins, MIME types, permissions
- languages/timezone, full screen geometry, hardware, network, battery,
  matchMedia
- `navigator.userAgentData` with high-entropy values, media devices,
  AudioContext, geolocation, WebRTC
- seeded Canvas / OffscreenCanvas noise, WebGL / WebGL2 vendor/renderer and
  debug-extension spoofing, `pdfViewerEnabled`

`fingerprint_bank.py` provides browser profiles and HTTP header profiles:

```json
{
  "fetch": {
    "backend": "auto",
    "header_fingerprint": "chrome"
  }
}
```

The header profile adds `Sec-CH-UA`, `Sec-Fetch-*`, `Accept`, and
`Accept-Language` fingerprints to `curl_cffi`, `tls_client`, `httpx`, and
`cloudscraper` requests.

`fingerprint_manager.py` bundles browser profile, HTTP headers, stealth JS,
and `browser_flags.py` anti-detect launch arguments into one session.

CAPTCHA providers can be chained with `MultiCaptchaSolver`; CapSolver and
AntiCaptcha adapters are included, with per-provider cooldown/status. Proxy
pools support `get_sticky_proxy()`, latency-aware `check_all()`, weighted /
best proxy selection, `ProxyManager` multi-pool failover, region/protocol
metadata, background health monitoring, and file/text/env imports.

`preprocess_captcha_image()` adds denoise, binarization, scaling, and
language options for local OCR.

## Deep Turnstile container handling

`turnstile_solver.py` detects and solves Turnstile container variants:

- `div.cf-turnstile` with `data-sitekey`
- explicit `turnstile.render(...)` widgets inside or outside
  `turnstile.ready(...)` wrappers
- variable sitekey / action values resolved from script constants
- iframe interactive / non-interactive challenges
- dynamically rendered Shadow DOM checkbox containers
- `execution: "execute"` widgets with widget id / selector / sitekey
- hidden token waiting across all frames and nested iframes
- third-party token injection with `turnstile.reset()`, DOM events, and
  dotted callback paths

It can wait for non-interactive widgets, auto-click, run `execute`
widgets, wait for the hidden `cf-turnstile-response` token, or inject a
provider token and trigger the page callback.

```json
{
  "cloudflare": {
    "solve_turnstile": true,
    "turnstile": {
      "auto_click": true,
      "wait_timeout": 30000,
      "max_attempts": 3
    }
  }
}
```

The handler is also wired into Patchright and Camoufox challenge loops.

## Security detection

`security_detector.py` classifies responses:

- Cloudflare challenge / block
- Generic WAF block
- Rate limit
- CAPTCHA / Turnstile
- Login wall
- Cookie consent / JS / geo / empty SPA / server error

The pipeline uses these findings to retry, rotate proxy, switch HTTP
backend, escalate to a stealth browser, or skip a page.

## Deep crawling

`deep_crawler.py` does BFS link and sitemap crawling:

```powershell
python scripts/deep_crawler.py --seed "https://example.com/list" --max-depth 2 --max-pages 100 --same-host --fetch-backend auto --output crawl.json
```

It honors robots.txt, same-host filtering, include/exclude patterns, rate
limits, and blocked-page skipping.

## Page/API analysis

`page_data_parser.py` extracts:

- metadata and OpenGraph
- JSON-LD and embedded JSON
- API endpoints from fetch / XHR / forms / scripts
- pagination fields
- CAPTCHA challenges

`api_analyzer.py` builds a reviewable manifest:

```powershell
python scripts/api_analyzer.py --input capture.json --output manifest.json
```

## API fetching and pagination

`api_client.py` replays captured specs with:

- cookie persistence
- proxy support
- min interval + jitter
- exponential backoff
- adaptive throttle
- page / offset / cursor pagination

```json
{
  "api": {
    "include_captured": true,
    "include_static": true,
    "max_specs": 200,
    "min_interval": 0.5,
    "max_retries": 3,
    "concurrency": 1,
    "pagination": {
      "type": "page",
      "param": "page",
      "page_size_param": "page_size",
      "page_size": 50,
      "max_pages": 100,
      "items_path": "items",
      "total_path": "total"
    }
  }
}
```

## Data processing

`data_processor.py` supports `select`, `rename`, `filter`, `sort`, `dedupe`,
`flatten`, `limit`, `aggregate`, `drop`, `default`, `convert`, `map`,
`replace`, and `join`.

Input/output supports `.json`, `.jsonl`, and `.csv`.

## Dependency bootstrap

```powershell
python scripts/ensure_web_fetch_dependencies.py           # auto install
python scripts/ensure_web_fetch_dependencies.py --check   # report only
python scripts/ensure_web_fetch_dependencies.py --http-only
python scripts/ensure_web_fetch_dependencies.py --browser-only
```

Or install the declared optional groups from `pyproject.toml`:

```powershell
pip install -e ".[http,browser]"
```

The full optional stack now includes `curl_cffi`, `tls_client`,
`cloudscraper`, `httpx`, `h2`, `patchright`, `camoufox`, `scrapling`,
`nodriver`, `seleniumbase`, `undetected_chromedriver`, `DrissionPage`,
`selenium`, and `cryptography` for encrypted HLS. Auto mode in
`smart_fetch.py` and `stealth_browser.py` defaults to `auto_install: true`,
so missing packages are installed on first use.

## Script index

- `smart_fetch.py` -- adaptive HTTP backend switcher
- `ensure_web_fetch_dependencies.py` -- dependency bootstrap
- `ensure_browser_binaries.py` -- chunked/Range-resumable browser binary installer
- `cloudflare_challenge.py` -- Cloudflare stage detection and clearance flow
- `challenge_evolution.py` -- dynamic challenge variant fingerprinting
- `challenge_replay.py` -- failure snapshots and offline variant replay
- `challenge_click.py` -- humanized Managed Challenge / Shadow DOM click helpers
- `challenge_cookie_bank.py` -- persistent per-host challenge cookie reuse
- `vendor_solver.py` -- vendor cookie validation, slider solving, token injection
- `waf_vendor.py` -- major WAF vendor classification and profiles
- `flaresolverr.py` -- local FlareSolverr client
- `stealth_browser.py` -- multi-engine stealth browser loop
- `nopecha_probe.py` -- real public IP and nopecha Cloudflare demo verdict
- `login_detector.py` -- login form/state auto-detection
- `hls_client.py` -- HLS resolve/download/combine client
- `media_crawler.py` -- concurrent resumable media crawl
- `media_session.py` -- rate-limited media HTTP session
- `media_parser.py` -- page/media parsing helpers
- `block_diagnoser.py` -- status/header/Cloudflare/robots block diagnosis
- `stealth_patches.py` -- reusable Playwright/Selenium stealth patches
- `autonomous_crawler.py` -- asyncio million-scale autonomous crawl
- `resource_downloader.py` -- streaming Range/resume downloader
- `resource_store.py` -- SQLite resource state store
- `browser_flags.py` -- anti-detect browser launch arguments
- `fingerprint_manager.py` -- unified fingerprint session manager
- `stealth_patch_bank.py` -- composable stealth patch library
- `fingerprint_bank.py` -- browser/HTTP header fingerprint profiles
- `turnstile_solver.py` -- deep Turnstile container solver
- `url_store.py` -- SQLite URL deduplication for resume/scale
- `data_extractor.py` -- schema-free record extraction and validation
- `human_behavior.py` -- UA rotation and randomized human pacing
- `security_detector.py` -- anti-bot response classification
- `deep_crawler.py` -- recursive link/sitemap crawler
- `api_client.py` -- API replay with retry and pagination
- `api_analyzer.py` -- API discovery and manifest builder
- `page_data_parser.py` -- static page/API analysis
- `captcha_solver.py` -- OCR / service / manual CAPTCHA solving
- `captcha_queue.py` -- concurrent CAPTCHA task queue
- `browser_session.py` -- fingerprint browser with network capture
- `scrape_guard.py` -- rate-limited HTTP session policies
- `proxy_pool.py` -- rotating proxy pool with geo/protocol support
- `current_ip.py` -- STUN/HTTP public IP diagnostics
- `data_processor.py` -- declarative data shaping
- `web_data_pipeline.py` -- pipeline orchestrator
- `acceptance_suite.py` -- real-site acceptance baseline runner
- `run_summary.py` -- end-of-run save paths and resource status report
- `adaptive_policy.py` -- per-target dynamic strategy memory
- `slider_solver.py` -- human-like slider CAPTCHA solving
- `metrics.py` -- metrics, Prometheus text, and alert rules
- `daemon.py` -- monitored daemon runner
- `alternate_access.py` -- alternate URL/UA fallback probes
- `fingerprint_binding.py` -- full-chain HTTP/TLS/browser identity binding
- `bypass_engine.py` -- adaptive challenge strategy orchestrator

## Compliance

- Confirm authorization before scraping.
- Honor robots.txt and platform terms where possible.
- Keep credentials local and encrypted.
- Keep rate limits on by default.
- Log 403 / 429 / CAPTCHA failures with a next action.
- Do not market the pipeline as a stealth or CAPTCHA-bypass tool.
