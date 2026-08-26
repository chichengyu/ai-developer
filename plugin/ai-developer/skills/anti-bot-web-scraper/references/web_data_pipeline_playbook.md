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
- [No-key CAPTCHA mode](#no-key-captcha-mode)
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
- [Deep reverse engineering](#deep-reverse-engineering)
- [Reverse engineering lab](#reverse-engineering-lab)
- [Runtime deep hook](#runtime-deep-hook)
- [Browser function probe](#browser-function-probe)
- [One-command auto reverse](#one-command-auto-reverse)
- [AST data-flow tracing](#ast-data-flow-tracing)
- [Deep deobfuscation and bundle execution](#deep-deobfuscation-and-bundle-execution)
- [Active differential verification](#active-differential-verification)
- [CDP breakpoint probe](#cdp-breakpoint-probe)
- [CDP return-value probe](#cdp-return-value-probe)
- [Call-chain replay](#call-chain-replay)
- [Webpack module takeover](#webpack-module-takeover)
- [WASM boundary hook](#wasm-boundary-hook)
- [Dynamic coverage filtering](#dynamic-coverage-filtering)
- [Native API probe](#native-api-probe)
- [Symbolic flow and z3](#symbolic-flow-and-z3)
- [Concolic dependency tracing](#concolic-dependency-tracing)
- [Execution trace replay](#execution-trace-replay)
- [Oracle convergence](#oracle-convergence)
- [Interprocedural taint](#interprocedural-taint)
- [Byte-level capture](#byte-level-capture)
- [Dual-browser diff](#dual-browser-diff)
- [Vendor sensor and recipe prediction](#vendor-sensor-and-recipe-prediction)
- [Reverse tool auto-install](#reverse-tool-auto-install)
- [Cross-site signature knowledge](#cross-site-signature-knowledge)
- [Session-preserving replay](#session-preserving-replay)
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
  -> mandatory deep reverse (deep_reverse per page, reverse_lab across captures,
     reverse_report.json; deep_hook runtime capture is adaptive)
  -> reverse-assisted retry for captures still blocked after bypass
  -> page/API analysis
  -> rate-limited API fetching with cookies
  -> automatic subpage parameter augmentation
  -> declarative data processing
  -> JSON / JSONL / CSV output
```

## Minimal config

```json
{
  "mode": "auto",
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

The pipeline always writes `reverse_report.json` after collection; set
`reverse_output` in the config (or pass `--reverse-output`) to change the path.

`mode` defaults to `"auto"`: it enables adaptive HTTP backends, a consistent
Chrome 124 fingerprint binding, browser escalation on blocked pages, and
no-key OCR. Set `"mode": "explicit"` to keep the previous non-normalized
defaults.

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

`BrowserSession` auto-installs missing engine packages on first use and
launches an installed Edge/Chrome executable when available, so the real
browser binary already on the machine is reused.

`stealth_browser.py` solves Managed Challenges / Turnstile with:

- `patchright` -- undetected Playwright API
- `camoufox` -- patched anti-fingerprint Firefox browser
- `scrapling` -- stealth fetcher with built-in Cloudflare solving
- `nodriver` -- CDP-only Chromium automation
- `seleniumbase` -- SeleniumBase UC / CDP mode
- `undetected_chromedriver` -- patched ChromeDriver
- `drission_page` -- DrissionPage Chromium automation
- `selenium` -- Selenium WebDriver with stealth injection

`--engine auto` tries installed engines in priority order, even after one
engine obtains a challenge cookie, because a cookie alone does not mean the
page is clear. The engine budget defaults to `browser.max_engines_per_round:
3`. Cookies from a pending round are injected into the next engine/round so a
valid `cf_clearance` is not discarded. Each round can rotate proxy on failure
and retries until `cf_clearance` or non-challenge content appears.

When no explicit `fingerprint_binding` is set, `bypass_engine` rotates
between consistent profiles (`chrome124` / `edge124`) on later rounds, so a
blocked fingerprint gets a second real-browser identity before giving up.

CLI:

```powershell
python scripts/stealth_browser.py --url "https://target.example/" --engine auto --engine-order patchright,camoufox,scrapling --browser-path "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --no-headless
python scripts/stealth_browser.py --check
```

CLI flags include `--url`, `--engine`, `--browser-path`, `--engine-order`,
`--max-attempts`, `--retry-delay`, `--rotate-proxy-on-fail`,
`--headless/--no-headless`, `--headless-fallback/--no-headless-fallback`,
`--storage-state`, and `--check`. With `--engine auto` it tries each
installed engine in order (up to `browser.max_engines_per_round`, default 3),
rotates proxy on failure, and loops until a challenge cookie or
non-challenge content appears.

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

## Browser containers

`BrowserSession` can run each task in an isolated browser container profile.
Set `browser.container: true` to auto-create a temporary Chromium user-data
directory that is removed when the session closes; set `container_dir` to
keep a named container for reuse across runs.

```json
{
  "browser": {
    "enabled": true,
    "container": true,
    "container_dir": "state/containers/task-a",
    "proxy": "http://user:pass@proxy.example:8080",
    "fingerprint_binding": "chrome126"
  }
}
```

Containers isolate cookies, local storage, cache, and profile artifacts while
the fingerprint binding and proxy pool keep each container's network identity
coherent. This is the desktop-side equivalent of one browser instance per
task/account without requiring Docker.

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

## No-key CAPTCHA mode

When no `api_key` or `api_key_env` is configured, the pipeline keeps working:

- `captcha.ocr` defaults to `true`: local OCR auto-discovers installed
  engines (`ddddocr`, `rapidocr_onnxruntime`, `easyocr`, `paddleocr`,
  `cnocr`, `pytesseract`) and auto-installs the best one in priority order on
  first use.
- `captcha.ocr_priority` overrides the auto-install/discovery order.
- Non-interactive Cloudflare / Turnstile widgets are still solved by browser
  auto-click and token waiting; an empty provider is never passed to the
  browser challenge handler.
- `captcha.allow_manual_fallback: true` keeps the original manual mode.
- `captcha.ocr: false` restores the old no-key behavior with no local OCR.
- The run summary reports `captcha_mode` as `off`, `ocr`, `manual`, or
  `provider`.

```powershell
python scripts/ensure_web_fetch_dependencies.py --ocr-only
```

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
- consistent window geometry, `visualViewport`, `screenX/Y`, and inner size
- native-looking `Event.isTrusted` for mouse, keyboard, pointer, touch, wheel,
  input, focus, and clipboard events
- visible/focused document state (`visibilityState`, `hidden`, `hasFocus`,
  WebKit aliases)
- `onLine`, `doNotTrack`, and `cookieEnabled` network/navigator signals
- realistic `StorageManager.estimate()` quota/usage details
- coherent `performance.timeOrigin` and navigation timing values
- `MediaCapabilities.decodingInfo` and `navigator.wakeLock` browser-native
  behavior fallbacks
- `navigator.appName`, `appCodeName`, `product`, and `vendorSub` browser
  identity coherence
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
  SIGINT/SIGTERM (Unix) or SIGBREAK (Windows) shutdown for crawler commands.

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
- `EXT-X-MEDIA` subtitle rendition discovery and download
- clear errors for unsupported `SAMPLE-AES` sample encryption
- per-segment retry with exponential backoff and resume from existing segment
  files (`resumed_segments` is reported in the result summary)
- low-latency HLS parsing: `EXT-X-PART`, `EXT-X-PRELOAD-HINT`, `EXT-X-SKIP`,
  `EXT-X-SERVER-CONTROL`, `EXT-X-PART-INF`, `EXT-X-DATERANGE`,
  `EXT-X-PROGRAM-DATE-TIME`, and `EXT-X-I-FRAME-STREAM-INF`

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
    "decrypt": true,
    "download_assets": true,
    "max_assets": 200
  }
}
```

`BrowserSession` captures HLS requests from runtime network traffic, and
`PageCapture.hls_urls()` also returns HLS URLs found in HTML and embedded
JSON. The pipeline downloads every discovered `m3u8` stream, plus discovered
image/audio/video/CSS/JS/font/subtitle/data/document assets when
`download_assets` is enabled. Summaries report `asset_downloads` and
`asset_errors`.

## DASH acquisition

`dash_client.py` adds static DASH MPD support:

- MPD parsing for `SegmentTemplate`, `SegmentTimeline`, `SegmentList`, and
  `SegmentBase` (single-file streams with `indexRange` / `Initialization
  range`)
- representation selection by preferred height or max bandwidth
- initialization segment and media segment download
- optional combined `.mp4` / binary output
- per-segment retry with exponential backoff and resume from existing segment
  files (`resumed_segments` is reported in the result summary)
- CENC/DRM streams are reported as unsupported instead of corrupting output

```powershell
python scripts/dash_client.py --url "https://example.com/manifest.mpd" --output data/media --height 1080
```

`.mpd` URLs are classified as `dash` media by the HTML/JSON extractors and
downloaded automatically by `media_crawler.py`.

## Smooth Streaming and file metadata

- `parse_smooth_manifest()` parses Microsoft Smooth Streaming XML manifests,
  including stream indexes, quality levels, and chunk timelines.
- `.ism/Manifest` and `format=mp4` manifest URLs are classified as `smooth`
  media by HTML/JSON extractors.
- `media_metadata.py` sniffs MP4/M4A/TS/WebM/Matroska/MP3/FLAC/OGG/WAV/AVI/FLV
  containers by magic bytes, parses MP4 `mvhd` duration, and reads
  WebVTT/SRT/ASS cue counts plus PNG/JPEG/GIF dimensions.
- `ffprobe` is used automatically when installed for richer duration and
  stream metadata.
- `resource_downloader.py` attaches this metadata to every downloaded file in
  `details.metadata`, and CSS/JS downloads also include
  `details.nested_assets` parsed from `url()`, `@import`, `import`,
  `require`, and `new URL()`.

## Concurrent media crawl and resume

`media_crawler.py` is a standalone resumable crawler:

- extracts image / video / audio / HLS / DASH / Smooth / subtitles / CSS /
  JS / fonts / data files / documents from HTML and JSON
- accepts direct URL seeds for all of those kinds and downloads them

The default `media_types` now includes `image`, `video`, `audio`, `hls`,
`dash`, `smooth`, `subtitle`, `file`, `css`, `js`, `font`, and `data`.
CSS/JS nested assets are recursively discovered and downloaded: a CSS
`url(...)` image or `@import` file is added back into the crawl queue and
fetched with the same metadata pipeline.
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
- JSONL output for every page, record, media URL (HLS/DASH/Smooth/image/audio/
  video), asset (CSS/JS/font/data/document), WS/SSE stream, DOM/JS event,
  block, and error

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

Every visited page now records its full media/file inventory in `page.media`:
HLS, DASH MPD, Smooth Streaming, video/audio/image URLs, subtitle files, and
common document/archive files. Crawl summaries include `media_urls`, `files`,
and `subtitles` counts, so whole-site asset discovery is part of the crawl
result rather than a separate pass.

`page.assets` additionally records CSS, JavaScript, fonts, icon images, data
files (JSON/XML/CSV), and document links. Summary counts include `assets`,
`css`, and `js`.

Set `url_store_path` to persist every discovered page/media/asset/stream URL
into a SQLite deduplicator; crawl summaries then report `url_store_seen`.
Set `jsonl_path` to append every analyzed page as one JSON line immediately
after it is crawled; robots-denied, fetch-error, and blocked pages are also
written so the JSONL is a complete crawl log. Summaries report `jsonl_lines`,
and interrupted crawls keep all already-written page records on disk.

With `crawl_api_endpoints: true`, the crawler also fetches every GET API
endpoint found on a page, records its JSON response, and discovers API-like
URLs inside that JSON (`next_url`, `url`, `api`, `endpoint`, `link`). Newly
found endpoints are appended to the page's API list and fetched too, so API
responses participate in whole-site discovery instead of waiting for a later
fetch pass.

```json
{
  "subpages": {
    "enabled": true,
    "seeds": ["https://example.com/list"],
    "crawl_api_endpoints": true,
    "max_api_calls": 200
  }
}
```

## One-URL full-site crawl

Give the pipeline a single URL and it automatically builds the full-site job:
deep-crawl all reachable pages/subpages, discover APIs, events, WebSockets,
SSE streams, auto-fill parameters, write the whole-site API index, and save
the processed records.

```powershell
python scripts/web_data_pipeline.py --url "https://example.com" --max-depth 3 --max-pages 200 --crawl-api --site-index state/site-api-index.json --output data/site.json
```

`--crawl-api` also makes the crawler fetch discovered API endpoints during the
crawl and recursively follow API URLs found inside JSON responses.

For JS-heavy sites, add browser rendering and runtime discovery:

```powershell
python scripts/web_data_pipeline.py --url "https://example.com" --browser --trigger-events --capture-storage --crawl-api --site-index state/site-api-index.json --output data/site.json
```

`--browser` renders each page with a stealth browser and captures runtime
network/API traffic. `--trigger-events` clicks/triggers inline event handlers
so event-driven APIs appear in the capture. `--capture-storage` records
localStorage/sessionStorage and feeds those values back into the parameter
bank.

Blocked pages are not skipped by default. The crawler keeps them in the
output, applies request-level block retries, waits with backoff, rotates the
pinned proxy, and switches the adaptive HTTP backend before escalating to
`alternate_access` / browser fallback. Recovery attempts are recorded per page
as `recovery`, and the summary reports `block_recoveries` and
`recovered_pages`. Tune recovery with `--block-retries`,
`--block-retry-delay`, `--block-retry-backoff`, `--no-proxy-rotate`, and
`--no-retry-on-block`. Alternate URL/UA fallback is enabled by default and can
be disabled with `--no-alternate`. API requests apply the same block recovery
at `ApiClient` level: blocked responses sleep with backoff, rotate the pinned
proxy, and switch the adaptive backend before returning an error. A stealth
browser fallback can be enabled with `--browser-fallback`. In
`web_data_pipeline.py`, blocked API results are also retried with
reverse-built fresh signatures during both normal and chained API fetching.

## Multi-site parallel crawl

`multi_site_pipeline.py` runs one isolated full-site job per URL and executes
them concurrently. Each site gets its own output directory, processed records,
summary report, and optional whole-site API index. A combined report aggregates
pages, crawl pages, API specs, stream specs, and processed records.

```powershell
python scripts/multi_site_pipeline.py --url "https://a.example" --url "https://b.example" --workers 4 --crawl-api --browser --trigger-events --capture-storage --site-index --output-dir state/multi-site --combined-output state/multi-site/combined.json
```

`--config base.json` merges a common JSON config into every job (for shared
headers, proxy pools, login state, or processing rules). A failing site is
reported in the combined output without stopping the other jobs.

Risk control is on by default: every site uses a conservative request
interval with jitter, exponential backoff, robots.txt checks, blocked-page
skipping, and per-site limits. Tune it with `--min-interval`, `--jitter`,
`--max-retries`, `--backoff-base`, `--backoff-max`, and `--no-robots`. The
combined report includes `blocked_pages`, `api_blocks`, `errors`, and
`robots_skipped` so a risk-control incident is visible in the summary.

Whole-site job failures also retry: `--site-retries` (default 1),
`--site-retry-delay` (default 5s), and `--site-retry-backoff` (default 2x)
control how a failed site is retried. By default a site that completed but
had blocked pages is not retried; pass `--retry-on-blocked` only when you have
confirmed the block is transient and you are allowed to retry. The combined
report includes `site_retries`, `block_recoveries`, and `recovered_pages`.
Per-page block recovery is enabled through `--block-retries` and rotates
proxies/backends before a page is considered blocked.

## Subpage API parameter augmentation

`param_augmenter.py` automatically harvests parameter names and values from
every crawled subpage and expands discovered API specs into concrete fetch
variants. Sources include page URL query strings, subpage links, API endpoint
query strings, media/stream URL query strings, network response bodies,
WebSocket/SSE frame data, form fields, embedded JSON scalar state, and
pagination signals. A page that calls `/api/sub-data?id=1` while another subpage calls
the same endpoint with `id=2` will produce both fetch variants automatically.
Concrete path APIs such as `/api/items/1` and `/api/items/2` are grouped into
a path template (`/api/items/{id}`) and expanded across the whole site, so
path-style interfaces are covered as well.

```json
{
  "subpages": {
    "enabled": true,
    "seeds": ["https://example.com/list"],
    "max_depth": 2,
    "max_pages": 100
  },
  "api": {
    "auto_augment_params": true,
    "site_index_output": "state/site-api-index.json",
    "augment": {
      "max_variants": 200,
      "max_values_per_param": 10,
      "infer_path_templates": true,
      "max_templates": 20,
      "scope": "related_then_global",
      "include_pagination": false,
      "exclude_keys": ["token", "signature"],
      "param_map": [
        {
          "match": "/api/items/",
          "params": {"category": ["books", "movies"]}
        }
      ]
    }
  }
}
```

Run the augmenter standalone on an existing crawl and spec manifest:

```powershell
python scripts/param_augmenter.py --specs specs.json --pages crawl.json --config augment.json --output augmented-specs.json
python scripts/param_augmenter.py --pages crawl.json --config augment.json --site-index site-api-index.json
```

`augment_variants`, `augment_param_keys`, and `augment_harvested_values` are
reported in the pipeline summary for verification.

`site_index_output` writes a whole-site API index with every page, subpage,
endpoint, page-to-endpoint mapping, aggregated parameter bank, and inferred
path templates. The summary also reports `site_pages`, `site_endpoints`,
`site_templates`, and `site_param_keys`.

## Response-driven parameter chaining

When `api.chain.enabled` is true, fetched JSON responses are parsed back into
the parameter bank. IDs, slugs, category keys, and other scalar values from
one API become query/path parameters for the next fetch round, so a list API
can automatically drive every detail API without manual joins. API-like URL
fields inside responses (`next_url`, `url`, `api`, `endpoint`, `link`) are
discovered as new specs and fetched in the next round as well.

```json
{
  "api": {
    "auto_augment_params": true,
    "chain": {
      "enabled": true,
      "max_rounds": 3,
      "max_specs_per_round": 50
    }
  }
}
```

The pipeline summary reports `chain_rounds` and `chain_new_specs`. Each round
is deduplicated against every previously fetched spec, and the loop stops
when no new parameterized spec is produced.

## Deep reverse engineering

`deep_reverse.py` focuses on the "why does this request work" layer. It
extracts inline JavaScript from HTML, scores obfuscation, runs conservative
deobfuscation passes, locates request construction sites, and finds the
functions that build signatures, tokens, hashes, and encrypted payloads.

In the end-to-end pipeline this stage is mandatory. `web_data_pipeline.py`
analyzes each captured page with `deep_reverse.py`, feeds the per-page
analysis and available runtime network/hook data into `reverse_lab.py`, and
writes a combined report. The default path is `reverse_report.json`; override
it with `reverse_output` in the config. Runtime `deep_hook.py` injection is
adaptive by default: protected or blocked pages are collected without hook
injection for stealth, while clean pages get a deep hook reload for request
provenance. Set `reverse.hook: false` or `reverse.stealth: ultimate` for strict
ultimate stealth; `reverse.hook: true` forces hooking always.

If a capture is still blocked after browser escalation, `web_data_pipeline.py`
calls `reverse_lab.build_reverse_retry_requests()` to construct fresh signed
requests from verified signatures or extracted recipes, then retries them over
the adaptive HTTP session. Successful responses are added back as recovered
captures and the reverse report is regenerated.

Reverse retry is on by default. Disable it with `reverse.retry_on_block:
false`; `reverse.max_retry_requests` caps the number of signed request
variants, and `reverse.max_retry_attempts` caps the retry rounds.
`reverse.brute_force` is also on by default and tries short secrets up to
`reverse.brute_max_length` (default 2) when no recipe or verified secret is
available.

```powershell
python scripts/deep_reverse.py --html page.html --output report.json
python scripts/deep_reverse.py --capture capture.json --deobfuscate
python scripts/deep_reverse.py --js bundle.js --deobfuscate --output report.json
python scripts/deep_reverse.py --js bundle.js --source-map bundle.js.map
python scripts/deep_reverse.py --js bundle.js --dynamic-decode
python scripts/deep_reverse.py --js bundle.js --acorn
python scripts/deep_reverse.py --js bundle.js --install-beautifier
python scripts/deep_reverse.py --js bundle.js --run-function genSign --args '["a","b"]'
python scripts/deep_reverse.py --eval "Date.now()"
```

The JSON report contains:

- `obfuscation` -- score and detected signals (eval/Function, packed arrays,
  hex/unicode escapes, base64, control-flow flattening, minified source,
  long identifiers, high entropy, dense strings)
- `bundle` -- detected bundler framework (webpack / vite / rollup / esbuild /
  AMD / CommonJS), webpack module count, module IDs, and named module comments
- `bundle_cross_refs` -- functions defined in one script and referenced from
  another, useful for split bundles where a signature function lives in a
  different chunk than the request call site
- `deobfuscated` -- decoded escapes, resolved `atob` / `Buffer.from`,
  resolved `_0x...[]` string arrays, unwrapped `eval("...")`, and beautified
  output; `--dynamic-decode` additionally executes suspected string decoders
  in Node to resolve obfuscator-style `_0x` arrays
- `bundle.acorn` -- function names and string literals extracted with the
  mature `acorn` parser when `--acorn` is used (auto-installed via npx)
- `request_sites` -- fetch / axios / XHR / jQuery call sites with headers,
  bodies, params, line numbers, and inferred dynamic fields
- `dynamic_fields` -- timestamps, nonces, signatures, tokens, and crypto
  expressions with confidence scores
- `crypto_calls` -- MD5 / SHA / HMAC / AES / RSA / Base64 / UUID / URL-encoding
  markers
- `signature_candidates` -- function names, algorithm hints, snippets, call
  counts, and confidence
- `signature_recipes` -- per-candidate parameter ordering, secret keys,
  encoding, and replay-ready snippets
- `device_fields` -- navigator / screen / canvas / WebGL / fonts / timezone /
  battery / storage API usage that can feed device fingerprints
- `timestamp_fields` -- timestamp producers with inferred unit (milliseconds,
  seconds, hex, base36, ISO 8601) and nearby request parameter names
- `data_flow` -- variable-level links from device / timestamp / crypto /
  signature sources to request params, headers, body fields, and URL values
- `ast_data_flow` -- acorn-backed edges with assignment lines and higher
  confidence when the AST pass runs
- `source_map` -- decoded source-map mappings and original positions when a
  `.map` file is supplied with `--source-map`; `mapped_analysis` also maps
  every signature candidate and request site back to its original source
- `captured_requests` -- runtime network entries with dynamic query/body fields
  when a PageCapture JSON is supplied

The deobfuscation passes are dependency-free by default. When
`jsbeautifier` is installed (optional group `reverse`), the beautify pass uses
it. When Node.js is present, `--eval` and `--run-function` execute an
expression or a named signature function in a local child process with a
timeout, so an extracted algorithm can be verified against real inputs.
`deep_deobfuscation.py` adds the strong-obfuscation path automatically at
score >= 70 and `bundle_runner.py` executes whole bundles in a Node VM.
The open-source `webcrack` CLI is auto-installed on first use through
`npx --yes` / `npm install -g` when requested (`deep_reverse.py --webcrack`
or `deep_reverse.webcrack_deobfuscate()`). The built-in passes remain the
default so the module still works with no network access.

```powershell
pip install -e ".[reverse]"
```

Use `deep_reverse.py` before writing a manual signature reimplementation:
it narrows the search to the exact functions and dynamic parameters that
need to be reproduced.

## Reverse engineering lab

`reverse_lab.py` works on a set of captures instead of one page. Give it two
or more requests to the same endpoint and it finds which parameters are
constants, which change per request, and which are likely signatures,
timestamps, or device fingerprints.

`web_data_pipeline.py` calls `analyze_capture_set()` automatically as part of
the mandatory reverse stage, using the per-page `deep_reverse.py` analysis and
`deep_hook.py` runtime requests when hook injection is enabled.

`build_reverse_retry_requests()` turns verified signature constructions and
signature recipes into fresh request candidates with refreshed timestamps and
nonces; `web_data_pipeline.py` uses these candidates to retry blocked captures
automatically.

```powershell
python scripts/reverse_lab.py --input hook-1.json --input hook-2.json --output lab.json
python scripts/reverse_lab.py --input hook-1.json --secrets "appKey,secretKey" --algorithms md5,hmac-sha256
python scripts/reverse_lab.py --input hook-1.json --brute-secret --brute-max 3 --brute-charset abcdef0123456789
python scripts/reverse_lab.py --input hook-1.json --js bundle.js --max-functions 20
python scripts/reverse_lab.py --input hook-1.json --exclude-params ts,nonce
```

The report contains:

- `request_diffs` -- constant vs changing params/headers, plus signature,
  timestamp, and device param classification
- `timestamp_correlations` -- timestamp values compared with hook capture time
  to infer seconds / milliseconds / hex / base36 / ISO 8601 and clock offset;
  `server_synced` marks timestamps that track the server clock
- `timestamp_correlations` also scans `X-Timestamp` / `X-Time` style request
  headers, not only query/body params
- `server_clock_offsets` -- server `Date` / `X-Server-Time` / `X-Timestamp`
  response headers compared with hook capture time
- `fingerprint_tokens` -- flattened device snapshot fields with per-field
  SHA-256 and a stable overall device fingerprint hash
- `signature_verifications` -- common payload serializations and constructions
  (`payload+secret`, `secret+payload`, HMAC, timestamp variants) checked
  against real captured signature values, including auth headers such as
  `X-Token` / `Authorization` / `Cookie`, and nested JSON bodies flattened to
  `user.id=1` style keys; serialization variants include sorted/unsorted,
  `&`, `;`, compact JSON, original parameter order, and the raw JSON body text
  exactly as sent
- `signature_consistency` -- how many independent samples each verified
  construction matches, which filters out accidental single-request matches
- `signature_coverages` -- for each verified signature, which request params
  are included in the signed payload and which are excluded (`--exclude-params`
  can test hypotheses that specific params are not signed)
- `response_error_signals` -- 4xx/5xx response bodies classified into
  signature / timestamp / device / parameter hints
- `active_diff` -- oracle-guided mutation results showing which request fields
  are signed
- `secret_inference` -- candidate secrets and their sources from recipes,
  storage, headers, responses, JS literals, and known patterns
- secret candidates are auto-extracted from JS literals assigned to
  `appKey` / `signSecret` / `token` style variables when `--js` is supplied
- `brute_force_secrets` -- optional bounded brute force for short signature
  secrets against the captured requests
- `device_param_matches` -- request device/fingerprint params compared against
  MD5 / SHA-1 / SHA-256 hashes of the captured device fingerprint snapshot
- `storage_diffs` -- local/session storage keys that stay stable or rotate
  between captures, useful for finding tokens, nonces, and device IDs
- `generated_python` -- dependency-free Python replay stubs for signature
  recipes
- `generated_node` -- Node.js replay stubs for the same recipes
- `generated_request_builders` -- full Python functions that build the request
  URL, params, headers, and verified signature together
- `generated_node_request_builders` -- equivalent Node.js request builders
- `generated_device_python` -- Python hasher that reproduces the captured
  device fingerprint hash from a device snapshot
- `js_replay_verifications` -- extracted JS functions executed in Node and
  compared against captured signature / device / timestamp values; a match
  confirms which function actually generated the value

The verification step is deliberately bounded: it needs candidate secrets
from `--secrets`, from recipes extracted by `deep_reverse.py`, or from hook
storage values, and tries common algorithms (MD5 / SHA-1 / SHA-256 / HMAC
variants). A verified match means the exact composition and secret were
reproduced against real traffic.

## Runtime deep hook

`deep_hook.py` installs a browser init script that wraps `fetch`,
`XMLHttpRequest`, and `WebSocket` before page scripts run. For every API request it records
the call stack, URL, method, headers, body, captured-at timestamp,
performance timestamp, device fingerprint snapshot, and local/session storage
state at call time. WebSocket `send()` frames are recorded with the same
stack and device provenance.

In `web_data_pipeline.py` this hook is adaptive by default. It is skipped on
protected or blocked pages, then installed and followed by a reload only on
clean pages. `reverse.hook: true` forces it always; `reverse.hook: false` or
`reverse.stealth: ultimate` disables it for maximum stealth.

When injected, the hook stores records under a per-session random,
non-enumerable global name instead of a fixed marker. It also captures XHR
request headers, `navigator.sendBeacon` calls, and EventSource connections in
addition to fetch/XHR/WebSocket traffic, plus request-time cookies and
resource timing entries. Adaptive injection additionally requires a page with
no block, no security finding, and no CAPTCHA. A page with any risk skips hook
injection for that page only; clean pages later in the same run remain
eligible for the adaptive hook. The run-level summary keeps
`adaptive_stealth_switched` as an informational flag for any risk seen, not as
a hook lock.

```powershell
python scripts/deep_hook.py --print-hook
python scripts/deep_hook.py --url "https://example.com/api-page" --output deep-hook.json
python scripts/deep_hook.py --url "https://example.com" --no-headless --engine patchright
```

The JSON output combines `hook.requests` (stack + provenance + device
snapshot) with the standard `network` capture. Device snapshots include
navigator properties, screen metrics, canvas hash, WebGL vendor/renderer,
timezone, referrer, window name, history length, performance resource names,
and storage keys. This is the fastest way to see which function triggered a
request and what device/session signals were read immediately before it.

The hook output can be fed straight back into the static analyzer:

```powershell
python scripts/deep_reverse.py --capture deep-hook.json --deobfuscate
```

Browser execution requires `browser_session` plus an installed Playwright /
Patchright engine; `--print-hook` works without a browser and the hook is
Node-safe for syntax validation.

## One-command auto reverse

`deep_reverse_auto.py` is a thin orchestrator for the existing modules. It
does not change their behavior: the same functions can still be called
directly. One command runs runtime capture (when needed), static analysis,
cross-request lab analysis, optional mature-library enhancement, and combined
JSON output.

```powershell
python scripts/deep_reverse_auto.py --html page.html --js bundle.js --output auto.json
python scripts/deep_reverse_auto.py --capture hook.json --js bundle.js --acorn --webcrack
python scripts/deep_reverse_auto.py --url "https://example.com/api-page" --js bundle.js --headless --probe-patterns "genSign,deviceId"
python scripts/deep_reverse_auto.py --capture hook.json --js bundle.js --deep-deobfuscation auto --run-bundle auto --auto-install
python scripts/deep_reverse_auto.py --capture hook.json --active-diff
```

The combined report contains `deep_reverse`, `js_analysis`, `reverse_lab`,
`source_map`, `ast_data_flow`, `function_probes`, `active_diff`,
`secret_inference`, and an overall `summary`. Existing pipelines that call
`deep_reverse.py` / `reverse_lab.py` directly are unaffected.

## Browser function probe

`function_probe.py` emits a browser init script that wraps JavaScript
functions matching configured name/path patterns before page scripts run.
Every wrapped call records the real arguments, return value, stack, timestamp,
and duration. It is bounded by pattern and scan limits so it does not wrap
the whole page.

```python
from function_probe import function_probe_js, parse_function_probes

script = function_probe_js(["genSign", "deviceId", "buildFingerprint"])
```

`BrowserSession(function_probe_patterns=[...])` installs the probe alongside
the deep hook. `session.capture_function_probes()` rescans late-bound globals
and returns the calls. `deep_hook.py --probe-patterns` exposes the same option
for one-shot captures. In the full pipeline:

```json
{
  "reverse": {
    "function_probe_patterns": ["genSign", "deviceId", "buildFingerprint"]
  }
}
```

## AST data-flow tracing

`ast_dataflow.py` adds an acorn-backed pass on top of the regex data flow.
It tracks variable assignments and call expressions, then maps timestamp /
device / crypto / signature-candidate sources to the exact request target.
When acorn is unavailable it returns a non-fatal `ok: false` result.

```python
from ast_dataflow import analyze_ast_data_flow
from deep_reverse import analyze_js

analysis = analyze_js(js)
ast = analyze_ast_data_flow(js, analysis)
```

The edges are also merged into `analysis.ast_data_flow` when
`analyze_js(..., auto_install=True)` runs on strong obfuscation.

## Deep deobfuscation and bundle execution

`deep_deobfuscation.py` leaves ordinary/minified code on the built-in fast
path. For scripts with an obfuscation score of at least 70 (or
`mode="always"`) it runs the deeper passes: Node dynamic string-array
decoding, acorn validation, and webcrack when present.

`bundle_runner.py` executes a whole bundle in a Node VM with browser stubs,
scans the resulting global graph for candidate functions, calls them with
plausible argument templates, and returns runtime traces.

Both are on-demand by default:

```json
{
  "reverse": {
    "deep_deobfuscation": "auto",
    "run_bundle": "auto",
    "auto_install": true
  }
}
```

`auto_install` only installs acorn/webcrack when a strong-obfuscation script
actually needs them. Set `"deep_deobfuscation": "disabled"` or
`"run_bundle": "disabled"` to force the fast path.

## Active differential verification

`active_diff.py` replays a captured request while mutating one field at a
time. A changed status/body means the field is likely signed; an unchanged
response means it is likely unsigned. It is opt-in because it sends extra
requests:

```json
{
  "reverse": {
    "active_diff": {
      "enabled": true,
      "max_requests": 8,
      "min_interval": 0.5,
      "decision_tree": true
    }
  }
}
```

In `web_data_pipeline.py`, active diff uses the same session stack as API
fetching, so cookies, proxy, UA/TLS fingerprint, and rate limits stay
consistent. Results appear in `reverse_lab.active_diff`.

`decision_tree: true` adds combination rounds: all signed fields mutated
together, reversed parameter order, reversed header order, and timestamp
offsets of `-1 / +1 / +60`.

## CDP breakpoint probe

`cdp_probe.py` sets real Chrome DevTools Protocol breakpoints at the exact
source lines found by static analysis, then dumps the paused call frame:
function name, URL, line/column, arguments, and `this` scope keys. This
covers webpack closures that function-name scanning cannot reach.

```python
from cdp_probe import build_breakpoints_from_analysis, run_url_cdp_probe

breakpoints = build_breakpoints_from_analysis(analysis, "bundle.js")
capture = run_url_cdp_probe(url, breakpoints)
```

`BrowserSession.capture_cdp_function_calls(breakpoints)` exposes the same
probe on an already-open page. In `deep_reverse_auto.py`:

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --js bundle.js --cdp-probe --cdp-wait-ms 6000
```

## CDP return-value probe

`run_cdp_return_probe()` extends breakpoint probing with `Debugger.stepOut`:
it captures the function entry arguments first, then resumes to the return
frame and tries `Debugger.getReturnValue`, falling back to a caller-frame
evaluation. This closes the real “arguments → return value” loop in the
browser instead of relying on Node argument templates.

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --js bundle.js --cdp-return-probe
```

## Call-chain replay

`call_chain.py` joins the deep-hook stack trace with function-probe arguments:

1. parse `at genSign (bundle.js:12:3)` stack frames;
2. match them to static signature candidates;
3. read the real arguments from `function_probes`;
4. replay the function in Node;
5. verify the result against the captured `sign` / `token` value.

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --js bundle.js --probe-patterns "genSign" --replay-call-chain
```

## Webpack module takeover

`bundle_runner.py` now extracts `__webpack_modules__` tables and invokes each
module function directly with a fake `module` / `exports` /
`__webpack_require__`, then scans the module exports for candidate signature
functions. This bypasses the need to find a global reference to the loader.

Results are reported as `webpack_modules_executed` and the traced functions
are included in the normal bundle traces.

## WASM boundary hook

`wasm_hook.py` covers WebAssembly:

- `wasm_hook_js()` installs a browser init script that wraps
  `WebAssembly.instantiate` / `instantiateStreaming` and records exported
  function calls with arguments and results;
- `parse_wasm_imports_exports()` reads WASM import/export names from a local
  binary;
- `run_wasm_probe()` instantiates a `.wasm` file in Node with stubs and calls
  its exports, including per-call memory changed ranges.
- `decompile_wasm_pseudocode()` emits C-style pseudocode through `wasm2c` when
  installed; `run_wasm_memory_write_probe()` returns per-function memory write
  ranges.

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --wasm-hook
python scripts/deep_reverse_auto.py --capture hook.json --wasm sign.wasm
```

The full pipeline enables the browser WASM hook with:

```json
{
  "reverse": {"wasm_hook": true}
}
```

## Dynamic coverage filtering

`coverage_probe.py` starts CDP precise coverage, reloads the page, and keeps
only functions that actually executed. `filter_candidates_by_coverage()`
then drops static signature candidates that never ran during the real page
load.

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --js bundle.js --coverage-probe
```

`BrowserSession.capture_cdp_coverage()` exposes the same probe on an open
page.

## Native API probe

`native_probe.py` wraps high-value browser APIs used by signature code:

- `Date.now` / `performance.now`
- `crypto.subtle.digest`
- `TextEncoder.encode`
- `localStorage.setItem` / `sessionStorage.setItem`
- `WebAssembly.Memory`

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --native-probe
```

Results appear as `native_calls` in the capture and `native_calls` in the
reverse summary.

## Symbolic flow and z3

`symbolic_probe.py` tracks assignment-level symbolic expressions such as
`ts = Date.now()` and `sign = md5(ts + secretKey)`, propagates variable
references, and emits signature-derivation constraints. When `z3-solver` is
installed, `solve_short_secret_constraints()` hands simple constraints to z3;
otherwise it reports the missing dependency and falls back to
`constrained_secret_search()`.

```powershell
python scripts/deep_reverse_auto.py --js bundle.js --symbolic
```

## Oracle convergence

`run_active_diff_oracle()` turns active diff into an iterative loop: it reads
the last server error hint, chooses the next mutation family (timestamp,
signature layout, headers, params), and stops as soon as the server accepts
the request.

```json
{
  "reverse": {
    "active_diff": {
      "enabled": true,
      "oracle": true,
      "max_rounds": 5,
      "max_requests": 20
    }
  }
}
```

## Interprocedural taint

`bundle_taint.py` joins `cross_script_refs` with per-script data flow so a
device/timestamp/crypto source in one chunk propagates to a request target in
another chunk. `deep_reverse.analyze_script_bundle()` includes the result as
`interprocedural_flow`.

## Concolic dependency tracing

`concolic_runner.py` runs a candidate JS function with concrete arguments,
then mutates one argument at a time. Any mutation that changes the output
marks that argument as a real dependency. This gives a bounded concolic
dependency graph without needing a full symbolic JS engine.

```powershell
python scripts/deep_reverse_auto.py --js bundle.js --concolic
```

## Execution trace replay

`replay_trace.py` captures CDP `Debugger.scriptParsed` and
`Runtime.consoleAPICalled` events, fetches script sources, and re-executes
them in Node. It is a bounded execution-replay layer: the same source should
produce the same console output and be able to reproduce signature calls
outside the browser.

```powershell
python scripts/deep_reverse_auto.py --url "https://example.com/" --replay-trace
```

## Byte-level capture

`byte_capture.py` rebuilds the exact HTTP/1.1 request bytes for a captured or
replayed request, fingerprints them with SHA-256, and reports the first byte
where two requests differ. Optional `mitmdump` support is included for real
TLS-decrypted capture when installed.

```powershell
python scripts/deep_reverse_auto.py --capture hook.json --byte-compare
```

## Dual-browser diff

`browser_diff.py` snapshots two URLs (clean vs protected), then reports
injected/removed scripts, global functions, storage keys, and HTML similarity.
This is the fastest way to locate the anti-bot injection point before deep
reverse work starts.

```powershell
python scripts/browser_diff.py --baseline-url "https://example.com/clean" --target-url "https://example.com/" --output diff.json
```

## Vendor sensor and recipe prediction

`vendor_sensor.py` contains vendor profiles for Cloudflare, DataDome, Akamai,
and PerimeterX, runs bundles through the existing Node runner, and ranks
verified recipes by vendor/framework frequency and hit count.

```powershell
python scripts/deep_reverse_auto.py --js bundle.js --vendor-sensor akamai
```

## Reverse tool auto-install

`ensure_reverse_tools.py` installs optional binaries only when the matching
feature is used:

- `--symbolic` installs `z3-solver` through pip before constraint solving.
- `--wasm-pseudocode` installs `wabt` / `wasm2c` through pip or npm before
  emitting C-style pseudocode.
- `--mitm-capture` installs `mitmproxy` through pip before running
  `mitmdump` for TLS-decrypted byte capture.

Each installer returns `ok: false` with a clear error when installation is
not possible, so the pipeline continues with the available fallback instead
of failing hard.

```powershell
python scripts/ensure_reverse_tools.py --status
python scripts/ensure_reverse_tools.py --tool z3 --check
python scripts/ensure_reverse_tools.py --tool wabt
python scripts/ensure_reverse_tools.py --tool mitmproxy
```

## Cross-site signature knowledge

`signature_knowledge.py` persists verified recipes to a JSON store and feeds
them back as candidate secrets/algorithms on later runs. Enable it with:

```json
{
  "reverse": {
    "knowledge_store": "state/signature-knowledge.json"
  }
}
```

Every verified signature is merged back into the store with its host, URL,
algorithm, pattern, secret, and payload example. `reverse_lab` automatically
loads matching entries before verification. Entries auto-expire after 30 days
by default; `prune_knowledge()`, `deprecate_entry()`, and `migrate_knowledge()`
handle stale-variant cleanup and store migration.

## Secret inference and algorithm coverage

`infer_secret_candidates()` now pulls candidates from signature recipes,
storage keys/values, request headers, response fields, JS literals, and
known default patterns. `constrained_secret_search()` then reduces the
brute-force alphabet with those hints and tests prefix/suffix/known-pattern
shapes before expanding to the full alphabet. Signature verification covers:

- SHA-512, SHA3-256/512, BLAKE2, and matching HMAC variants
- payload-only, payload+secret, secret+payload, timestamp variants, header
  inclusion, URL-path inclusion, and UTF-16LE byte encoding
- AES-CBC / AES-GCM, ChaCha20, PBKDF2-SHA256, scrypt, and RSA PKCS#1 v1.5 /
  OAEP when `cryptography` is installed
- hex, base64, base64url, and reversed-hex encodings

All verified constructions still require the exact digest to match real
captured traffic; broadened coverage only adds candidate checks.

## Session-preserving replay

`replay_client.py` closes the loop between generated replay code and real
requests. It reads a verified signature from a `deep_reverse_auto.py` /
`reverse_lab.py` report, builds an `ApiSpec` with a `prepare_request` hook,
and sends it through `ApiClient` / `SmartFetchSession`.

```powershell
python scripts/replay_client.py --report auto.json --output result.json
python scripts/replay_client.py --report auto.json --cookie-file cookies.json --backend auto
python scripts/replay_client.py --report auto.json --proxy "socks5://127.0.0.1:1080" --min-interval 1
python scripts/replay_client.py --report auto.json --dry-run
```

Because the request is sent through the existing session stack, cookies,
UA/TLS fingerprints, proxy, retries, backoff, and rate limits stay attached to
the same identity. `ApiSpec.prepare_request` is an optional non-serialized
hook, so existing `api_client.py` behavior is unchanged when the hook is not
present.

`web_data_pipeline.py` now also uses this automatically: after its mandatory
reverse stage, verified replay specs are built with `build_replay_specs()` and
appended to the normal API discovery list, so `fetch()` sends them through the
same `ApiClient` session. Toggle with:

```json
{
  "reverse": {
    "replay": true
  }
}
```

`replay` defaults to `true`; set it to `false` to keep the old discovery-only
behavior.

## Page/API analysis

`page_data_parser.py` extracts:

- metadata and OpenGraph
- JSON-LD and embedded JSON
- API endpoints from fetch / XHR / forms / scripts
- POST request bodies from `fetch` / axios / jQuery / HTTP clients
- axios `params` objects and `axios.request({...})` configs
- GraphQL query/mutation operations and their variables
- WebSocket endpoints and JSON `send()` payloads
- EventSource / SSE endpoints and `text/event-stream` content types
- HTML `on*` event handlers and JS `addEventListener` / `.on()` bindings with
  nearby handler URLs
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

API requests use a separate header fingerprint from page loads:
`Accept: application/json`, `Sec-Fetch-Dest: empty`, `Sec-Fetch-Mode: cors`,
and `Sec-Fetch-Site: same-origin`, without the document-only
`Sec-Fetch-User` / `Upgrade-Insecure-Requests` headers.

Blocked API results are isolated per endpoint: only a result classified as a
WAF/challenge/block is marked `risky: true` with `stealth_mode: ultimate`, and
that endpoint's session is closed and recreated before the next endpoint.
Clean APIs keep the original session identity and are not switched to another
backend/proxy because another endpoint was blocked. Direct HTTP API fetches do
not use browser deep-hook injection; deep hook applies to browser page
captures.

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

## Real-time event capture

`page_data_parser.py` discovers WebSocket (`WS`) and EventSource / SSE
endpoints from page scripts. WebSocket `send(JSON.stringify({...}))` payloads
are parsed and attached to the endpoint as request bodies, so room IDs,
topics, and event parameters are available for later use.

`BrowserSession` network capture also listens to WebSocket frames:

- `framesent` and `framereceived` are recorded with parsed JSON `frame_data`
- every frame has a `direction` (`sent` / `received`)
- `text/event-stream` responses are parsed into discrete SSE entries with
  `frame_data.event`, `frame_data.data`, `frame_data.id`, and `direction:
  received`

DeepCrawler records `page.streams` (WS/SSE endpoints) and `page.events`
(DOM/JS event handlers) per page; crawl summaries include `streams` and
`events` counts.

Stream specs are reported separately as `stream_specs` in the pipeline summary
and are excluded from plain HTTP `ApiClient` fetching, since they require a
persistent socket rather than a request/response call.

With `browser.trigger_events` enabled, `BrowserSession` also triggers inline
`onclick` / `onchange` / `oninput` / form submit handlers and keeps the
resulting network traffic in the same capture. With
`browser.capture_storage` enabled, localStorage/sessionStorage values are
recorded and fed into the parameter bank for automatic API parameter fill.

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
python scripts/ensure_web_fetch_dependencies.py --ocr-only
```

Or install the declared optional groups from `pyproject.toml`:

```powershell
pip install -e ".[http,browser]"
```

The full optional stack now includes `curl_cffi`, `tls_client`,
`cloudscraper`, `httpx`, `h2`, `patchright`, `camoufox`, `scrapling`,
`nodriver`, `seleniumbase`, `undetected_chromedriver`, `DrissionPage`,
`selenium`, `cryptography` for encrypted HLS, and `pillow` / `ddddocr` for
local OCR. Auto mode in
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
- `dash_client.py` -- DASH MPD resolve/download/combine client
- `media_metadata.py` -- container sniffing / MP4 duration / subtitle parsing
- `media_crawler.py` -- concurrent resumable media crawl
- `media_session.py` -- rate-limited media HTTP session
- `media_parser.py` -- page/media parsing helpers
- `param_augmenter.py` -- subpage API parameter auto-fill and variant expansion
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
- `deep_reverse.py` -- JS deobfuscation and request/signature reverse analysis
- `ast_dataflow.py` -- acorn-backed source-to-request data-flow tracing
- `deep_deobfuscation.py` -- on-demand deep deobfuscation for strong bundles
- `bundle_runner.py` -- whole-bundle Node VM execution and trace collection
- `function_probe.py` -- browser-side function-level call tracing
- `active_diff.py` -- oracle-guided active differential verification
- `cdp_probe.py` -- CDP breakpoint-level call-frame sampling
- `call_chain.py` -- stack-to-candidate matching and Node argument replay
- `wasm_hook.py` -- WASM boundary hook, parser, and Node probe
- `coverage_probe.py` -- CDP precise-coverage candidate filtering
- `native_probe.py` -- native API call tracing
- `symbolic_probe.py` -- symbolic expression tracing and optional z3 solving
- `concolic_runner.py` -- bounded input-dependency concolic tracing
- `replay_trace.py` -- CDP execution trace capture and Node replay
- `byte_capture.py` -- raw HTTP request-byte fingerprinting and comparison
- `browser_diff.py` -- dual-browser DOM/JS diff
- `vendor_sensor.py` -- vendor sensor profiles and recipe prediction
- `ensure_reverse_tools.py` -- on-demand z3 / wabt / mitmproxy installers
- `bundle_taint.py` -- cross-chunk interprocedural taint
- `signature_knowledge.py` -- cross-site verified-recipe reuse
- `deep_hook.py` -- runtime fetch/XHR stack, timestamp, and device hook
- `reverse_lab.py` -- cross-capture signature / timestamp / device lab
- `deep_reverse_auto.py` -- one-command auto reverse orchestrator
- `replay_client.py` -- session-preserving replay of verified signatures
- `captcha_solver.py` -- OCR / service / manual CAPTCHA solving
- `captcha_queue.py` -- concurrent CAPTCHA task queue
- `browser_session.py` -- fingerprint browser with network capture
- `scrape_guard.py` -- rate-limited HTTP session policies
- `proxy_pool.py` -- rotating proxy pool with geo/protocol support
- `current_ip.py` -- STUN/HTTP public IP diagnostics
- `data_processor.py` -- declarative data shaping
- `web_data_pipeline.py` -- pipeline orchestrator
- `multi_site_pipeline.py` -- parallel multi-site full-site crawler
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
