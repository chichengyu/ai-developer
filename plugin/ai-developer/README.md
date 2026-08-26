# AI Developer Plugin
A personal Codex plugin that bundles the nine skills shipped in this repository into a single installable unit. The plugin lives at `plugin/ai-developer/` and ships its own copy of every skill under `./skills/` so it can be packaged and installed independently of the source tree.
## Layout
```
plugin/ai-developer/
├── .codex-plugin/
│   └── plugin.json        # Plugin manifest consumed by Codex
├── README.md              # This file
└── skills/                # Independent copy of every source skill
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
## Bundled skills
| Skill | Trigger / Use case |
| --- | --- |
| [anti-bot-web-scraper](./skills/anti-bot-web-scraper/SKILL.md) | Cloudflare / WAF / Turnstile bypass, CAPTCHA solving, proxy rotation, declarative data processing |
| [desktop-app-dev](./skills/desktop-app-dev/SKILL.md) | Ship native cross-platform desktop GUI apps (Windows / macOS / Linux) via an 8-step workflow |
| [java-superpowers-contract](./skills/java-superpowers-contract/SKILL.md) | Java engineering contract: minimal change, environment isolation, SQL rollback rules, audit trail |
| [manga-drama-video](./skills/manga-drama-video/SKILL.md) | End-to-end AI manga-drama video pipeline with strict checkpoints and user-review gates |
| [manga-drama-video-helper](./skills/manga-drama-video-helper/SKILL.md) | Companion helper that drives script writing, asset generation, dubbing and final composition |
| [mobile-app-dev](./skills/mobile-app-dev/SKILL.md) | Ship iOS / iPadOS / Android / visionOS / Wear OS apps with framework auto-selection |
| [multi-db-analyzer](./skills/multi-db-analyzer/SKILL.md) | Multi-DB SQL / NoSQL / TimeSeries / VectorDB query and reporting tool |
| [scraper-unblocker](./skills/scraper-unblocker/SKILL.md) | Robust web crawler with automatic anti-bot diagnostics and multi-backend retries |
| [token-economizer](./skills/token-economizer/SKILL.md) | Global output-compression engine that auto-loads to minimise token usage |
## Install
The plugin is local and currently ships without a marketplace entry. Point Codex at the manifest directly:
```bash
codex plugin install ./plugin/ai-developer
```
To regenerate the personal marketplace entry instead, use the plugin-creator scaffold with `--with-marketplace`.
## Validate
```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ./plugin/ai-developer
```
## Relationship to the source skills
The nine skill folders under `plugin/ai-developer/skills/` are byte-for-byte copies of the originals under [`skills/`](../../skills/skills). They are maintained as an independent snapshot so the plugin can be installed, versioned and shipped on its own cadence. To refresh the bundled copy, re-run the copy step in the repository root README.
