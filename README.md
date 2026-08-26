# ai-developer

<p align="center">
  <img src="https://img.shields.io/badge/Java-17%2B-orange?logo=openjdk&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Node.js-18%2B-green?logo=nodedotjs&logoColor=white" />
  <img src="https://img.shields.io/badge/Codex-Skill-blueviolet" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

A personal Codex workspace that ships nine curated skills and bundles them into a single installable plugin. The source of truth for every skill is `skills/`; the plugin at `plugin/ai-developer/` carries its own independent copy under `plugin/ai-developer/skills/`.
## Layout
```
ai-developer/
├── README.md            # This file
├── plugin/              # Codex plugin bundles
│   └── ai-developer/
│       ├── .codex-plugin/plugin.json
│       ├── README.md
│       └── skills/      # Independent copy of every source skill
└── skills/              # Source skills (canonical)
    ├── README.md
    └── skills/
        ├── anti-bot-web-scraper/
        ├── desktop-app-dev/
        ├── java-superpowers-contract/
        ├── manga-drama-video/
        ├── manga-drama-video-helper/
        ├── mobile-app-dev/
        ├── multi-db-analyzer/
        ├── scraper-unblocker/
        └── token-economizer/
```
## Contents
- [Skills](#skills)
  - [anti-bot-web-scraper](#anti-bot-web-scraper)
  - [desktop-app-dev](#desktop-app-dev)
  - [java-superpowers-contract](#java-superpowers-contract)
  - [manga-drama-video](#manga-drama-video)
  - [manga-drama-video-helper](#manga-drama-video-helper)
  - [mobile-app-dev](#mobile-app-dev)
  - [multi-db-analyzer](#multi-db-analyzer)
  - [scraper-unblocker](#scraper-unblocker)
  - [token-economizer](#token-economizer)
- [Plugin](#plugin)
  - [ai-developer (plugin)](#ai-developer-plugin)
- [Refreshing the plugin bundle](#refreshing-the-plugin-bundle)
# Skills
The nine canonical skills live under [`skills/`](./skills). Each is a self-contained Codex skill with its own `SKILL.md`, templates, scripts and references.
### anti-bot-web-scraper
Build robust web scrapers and data-collection pipelines with automatic multi-backend anti-bot handling. Use for Cloudflare / WAF / Turnstile bypass, page/API collection, deep crawling, CAPTCHA solving, proxy rotation, and declarative data processing. See [skills/anti-bot-web-scraper/SKILL.md](./skills/skills/anti-bot-web-scraper/SKILL.md).
### desktop-app-dev
Consultative Codex skill for shipping native cross-platform desktop GUI applications (Windows / macOS / Linux) via an 8-step workflow: requirements analysis, framework selection, task decomposition, UI responsiveness, hardware input, packaging, verification, handoff. See [skills/desktop-app-dev/SKILL.md](./skills/skills/desktop-app-dev/SKILL.md).
### java-superpowers-contract
Java engineering contract: minimal change, environment isolation, SQL rollback rules, two-phase workflow, method-level anchoring, full-time audit. See [skills/java-superpowers-contract/SKILL.md](./skills/skills/java-superpowers-contract/SKILL.md).
### manga-drama-video
End-to-end AI manga-drama video pipeline with strict 10-step checkpoints and user review between every step. Covers script, character analysis, storyboard, image/scene generation, voice acting, subtitles, final composition and FFmpeg / VapourSynth post-processing. See [skills/manga-drama-video/SKILL.md](./skills/skills/manga-drama-video/SKILL.md).
### manga-drama-video-helper
Companion helper that drives script writing, asset generation, dubbing and final composition for multi-episode manga-drama projects, with per-stage user confirmation. See [skills/manga-drama-video-helper/SKILL.md](./skills/skills/manga-drama-video-helper/SKILL.md).
### mobile-app-dev
Consultative Codex skill for shipping mobile applications across iOS / iPadOS / Android / visionOS / Wear OS via an 8-step workflow with framework auto-selection (SwiftUI, Compose, Flutter, React Native, .NET MAUI, KMP, Capacitor, Tauri). See [skills/mobile-app-dev/SKILL.md](./skills/skills/mobile-app-dev/SKILL.md).
### multi-db-analyzer
Pure Python multi-DB query and analysis tool: SQL (MySQL, PostgreSQL, SQLite, SQL Server, Oracle, MariaDB, TiDB) plus NoSQL (Redis, Elasticsearch, MongoDB), TimeSeries (InfluxDB, TDengine) and VectorDB (Qdrant). Includes schema introspection, data-quality checks, FK topology, explain plans and HTML reports. See [skills/multi-db-analyzer/SKILL.md](./skills/skills/multi-db-analyzer/SKILL.md).
### scraper-unblocker
Professional web scraping assistant that builds robust crawlers, automatically diagnoses common anti-bot obstacles (403 / 429 / 503 / JS challenges / cookie walls / Cloudflare) and deep-crawls media with classification. See [skills/scraper-unblocker/SKILL.md](./skills/skills/scraper-unblocker/SKILL.md).
### token-economizer
Global Token-compression engine. Auto-loads to minimise output across every Codex task: zero-fluff, compact formatting, batched tool calls, context compression. See [skills/token-economizer/SKILL.md](./skills/skills/token-economizer/SKILL.md).
# Plugin
### ai-developer (plugin)
A personal Codex plugin that bundles all nine skills into one installable unit. Lives at [plugin/ai-developer/](./plugin/ai-developer) and ships an independent copy of every skill under [plugin/ai-developer/skills/](./plugin/ai-developer/skills). The manifest is at [plugin/ai-developer/.codex-plugin/plugin.json](./plugin/ai-developer/.codex-plugin/plugin.json); the bundle description is at [plugin/ai-developer/README.md](./plugin/ai-developer/README.md).
Install:
```bash
codex plugin install ./plugin/ai-developer
```
Validate:
```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ./plugin/ai-developer
```
# Refreshing the plugin bundle
The plugin is a copy, not a symlink, so it must be refreshed whenever a source skill changes. To rebuild:
```bash
$src = "./skills/skills"; $dst = "./plugin/ai-developer/skills";
foreach ($d in Get-ChildItem $src -Directory) {
  Copy-Item -Path $d.FullName -Destination $dst -Recurse -Force
}
```
