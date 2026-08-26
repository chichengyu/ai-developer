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
proxies, login, media/HLS/DASH/Smooth acquisition, container metadata and
subtitle parsing, CSS/JS/font/data asset crawling, deep crawling, API
discovery, WebSocket/SSE real-time capture, DOM/JS event capture, data
processing, deep JS reverse engineering (signatures, timestamp provenance,
device fingerprints), runtime request-stack capture, automatic parameter
recognition and fill, metrics, and daemonized production runs.

The pipeline defaults to `auto` mode: adaptive HTTP backends, consistent
fingerprinting, stealth-browser escalation on blocks, and no-key CAPTCHA
handling. Without a CAPTCHA API key it still runs: browser auto-click for
non-interactive Cloudflare/Turnstile challenges and auto-discovered local OCR
for image CAPTCHAs. Optional provider keys and proxy pools remain compatible.

Reverse engineering is a mandatory pipeline stage: every captured page is
analyzed by `deep_reverse.py`, and all captures are passed to `reverse_lab.py`.
The runtime deep hook is adaptive by default: protected or blocked pages are
collected without hook injection for stealth, while clean pages get a deep
hook reload for request provenance. Set `reverse.hook: false` or
`reverse.stealth: ultimate` for strict ultimate stealth; `reverse.hook: true`
forces hooking always. The combined report is written to `reverse_report.json`,
or to the path configured as `reverse_output`.

The reverse stage also deepens automatically when a site needs it:

- AST data-flow edges (`ast_dataflow.py`) are produced when acorn is available
  or when strong obfuscation enables auto-install.
- Browser function-level tracing (`function_probe.py`) wraps candidate
  signature/device functions and records real arguments and return values.
- Oracle-guided active differential verification (`active_diff.py`) mutates
  one field at a time and replays the request to determine what is signed.
- Deep deobfuscation (`deep_deobfuscation.py`) runs on strong obfuscation
  (score >= 70) and adds dynamic string-array decoding, acorn validation, and
  webcrack when available.
- Whole-bundle execution (`bundle_runner.py`) runs the JS bundle in a Node VM
  with browser stubs and traces candidate functions.
- Secret inference now combines JS literals, storage, headers, response
  fields, known patterns, and bounded brute force.
- CDP breakpoint probing (`cdp_probe.py`) dumps real call frames at static
  source locations, including webpack closures.
- Call-chain replay (`call_chain.py`) replays stack-matched functions with
  real probe arguments and verifies the result against captured signatures.
- Webpack module tables are executed directly (`bundle_runner.py`), and WASM
  exports are hooked, parsed, and probed (`wasm_hook.py`).
- Verified signature recipes persist across hosts/vendor variants through
  `signature_knowledge.py`.
- CDP return-value probing (`cdp_probe.py`) captures entry args and return
  values with step-out; precise coverage (`coverage_probe.py`) filters out
  candidates that never execute.
- Native API probes (`native_probe.py`) trace `Date.now`, `crypto.subtle`,
  `TextEncoder`, storage, and WASM memory calls; symbolic tracing
  (`symbolic_probe.py`) adds constraint output with optional z3 solving.
- Oracle-guided active diff converges on an accepted request, and
  `bundle_taint.py` propagates taint across chunks. Knowledge entries
  auto-expire, deprecate, and migrate.
- Bounded concolic tracing (`concolic_runner.py`) finds which args feed a
  signature; execution traces (`replay_trace.py`) are replayed in Node.
- Raw request-byte comparison (`byte_capture.py`), dual-browser injection
  diff (`browser_diff.py`), and vendor sensor/recipe prediction
  (`vendor_sensor.py`) close the remaining validation and targeting gaps.
- Optional reverse tools (`ensure_reverse_tools.py`) install z3-solver,
  wabt/wasm2c, and mitmproxy automatically when their feature is used.

When normal bypass still leaves a capture blocked, the pipeline automatically
builds fresh signed requests from the reverse report and retries them. A
successful reverse retry is added back as a recovered capture and the reverse
report is rebuilt. When no recipe or verified secret is available, the retry
stage also auto-brute-forces short signature secrets (up to two characters by
default). Blocked API fetches are retried the same way with reverse-built
signatures during both normal and chained API fetching. API risk handling is
per endpoint: only a blocked API is marked risky/ultimate stealth and has its
session reset; clean API endpoints keep the original identity.

Adaptive hooking only runs after a page is confirmed clean: no block, no
security finding, no CAPTCHA. A page that shows any risk skips hook injection
for that page only; clean pages later in the same run still get the adaptive
hook. The run-level summary keeps `adaptive_stealth_switched` as an
informational flag for any risk seen, not as a hook lock.

## Quick start

Install optional dependencies automatically:

```powershell
python scripts/ensure_web_fetch_dependencies.py
```

In `auto` mode, missing HTTP, OCR, and browser dependencies are also
installed on demand when a feature is first used.

Run one JSON-config pipeline:

```powershell
python scripts/web_data_pipeline.py --config config.json
```

Every run writes a mandatory deep reverse report. The default path is
`reverse_report.json`; use `reverse_output` in the config or
`--reverse-output` on the CLI to change it.

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
| Browser containers | `Browser containers` |
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
| One-URL full-site crawl | `One-URL full-site crawl` |
| Multi-site parallel crawl | `Multi-site parallel crawl` |
| Risk-aware pacing / backoff | `Multi-site parallel crawl` |
| Site-level retry with backoff | `Multi-site parallel crawl` |
| Blocked-page recovery / backend rotation | `One-URL full-site crawl` |
| API-level block retry / proxy rotation | `API fetching and pagination` |
| Subpage API parameter augmentation | `Subpage API parameter augmentation` |
| Whole-site API index | `Subpage API parameter augmentation` |
| Response-driven parameter chaining | `Response-driven parameter chaining` |
| Deep JS deobfuscation and signature extraction | `Deep reverse engineering` |
| Reverse-engineer a captured API request | `Deep reverse engineering` |
| Device fingerprint reverse analysis | `Deep reverse engineering` |
| Timestamp / nonce provenance | `Deep reverse engineering` |
| Request source data-flow graph | `Deep reverse engineering` |
| Source map position recovery | `Deep reverse engineering` |
| Obfuscation entropy stats | `Deep reverse engineering` |
| Bundle framework detection | `Deep reverse engineering` |
| Dynamic `_0x` string decoder | `Deep reverse engineering` |
| acorn AST parsing | `Deep reverse engineering` |
| jsbeautifier auto-install | `Deep reverse engineering` |
| Webpack module table extraction | `Deep reverse engineering` |
| Cross-script reference tracing | `Deep reverse engineering` |
| One-command auto reverse | `Deep reverse engineering` |
| AST data-flow tracing | `Deep reverse engineering` |
| Browser function probe | `Runtime deep hook` |
| Active differential verification | `Reverse engineering lab` |
| Deep deobfuscation / whole-bundle execution | `Deep reverse engineering` |
| CDP breakpoint probe / call-chain replay | `Runtime deep hook` |
| WASM boundary hook | `Deep reverse engineering` |
| Cross-site signature knowledge | `Reverse engineering lab` |
| CDP return-value probe / coverage filtering | `Runtime deep hook` |
| Native API probe / symbolic flow / oracle convergence | `Deep reverse engineering` |
| Interprocedural taint / knowledge evolution | `Deep reverse engineering` |
| Concolic / execution replay / byte compare | `Deep reverse engineering` |
| Dual-browser diff / vendor recipe prediction | `Deep reverse engineering` |
| Reverse tool auto-install | `Dependency bootstrap` |
| Session-preserving replay | `Deep reverse engineering` |
| Cross-request signature cracking | `Reverse engineering lab` |
| Multi-sample signature consistency | `Reverse engineering lab` |
| Short secret brute force | `Reverse engineering lab` |
| Full request replay generation | `Reverse engineering lab` |
| Signature coverage analysis | `Reverse engineering lab` |
| Node full request replay | `Reverse engineering lab` |
| Nested JSON signature verification | `Reverse engineering lab` |
| Raw JSON body signature verification | `Reverse engineering lab` |
| Secret literal auto-extraction | `Reverse engineering lab` |
| Device fingerprint Python generator | `Reverse engineering lab` |
| Dynamic JS function verification | `Reverse engineering lab` |
| Request diff / constant detection | `Reverse engineering lab` |
| Device snapshot hashing | `Reverse engineering lab` |
| Server clock offset analysis | `Reverse engineering lab` |
| Timestamp server sync detection | `Reverse engineering lab` |
| Header timestamp correlation | `Reverse engineering lab` |
| Response error oracle | `Reverse engineering lab` |
| Extended signature serializations | `Reverse engineering lab` |
| Storage token rotation diff | `Reverse engineering lab` |
| Runtime request stack hook | `Runtime deep hook` |
| WebSocket frame provenance | `Runtime deep hook` |
| API header fingerprinting | `API fetching and pagination` |
| JS body / GraphQL parsing | `Page/API analysis` |
| WebSocket / SSE parsing | `Page/API analysis` |
| Real-time event capture | `Real-time event capture` |
| DOM / JS event discovery | `Page/API analysis` |
| Browser event trigger / storage params | `Real-time event capture` |
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

`web_data_pipeline.py` always runs the deep reverse chain after collection:
`deep_reverse.py` per-page analysis, `reverse_lab.py` cross-capture
verification, then a combined `reverse_report.json`. `deep_hook.py` runtime
capture is adaptive by default and is skipped automatically on protected or
blocked pages. Blocked captures are then retried with reverse-built signature
requests before normal API discovery continues.

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
