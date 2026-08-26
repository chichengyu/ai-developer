# ai-developer

<p align="center">
  <img src="https://img.shields.io/badge/Java-17%2B-orange?logo=openjdk&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Node.js-18%2B-green?logo=nodedotjs&logoColor=white" />
  <img src="https://img.shields.io/badge/Codex-Skill-blueviolet" />
  <img src="https://img.shields.io/badge/Codex%20Plugin-v1.0.0-blueviolet" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
</p>

一个面向中文开发者的 Codex 技能与插件仓库：包含 9 个可独立安装的 Codex 技能，并打包成一个可整体安装的 `ai-developer-skill-plugin` 插件。技能源目录是 `skills/skills/`，插件位于 `plugin/ai-developer-skill-plugin/`，插件内部保存独立副本，不会影响原始技能。

<a id="toc"></a>
## 目录

- [项目简介](#项目简介)
- [目录结构](#目录结构)
- [技能清单](#技能清单)
  - [multi-db-analyzer](#multi-db-analyzer)
  - [java-superpowers-contract](#java-superpowers-contract)
  - [token-economizer](#token-economizer)
  - [desktop-app-dev](#desktop-app-dev)
  - [mobile-app-dev](#mobile-app-dev)
  - [scraper-unblocker](#scraper-unblocker)
  - [anti-bot-web-scraper](#anti-bot-web-scraper)
  - [manga-drama-video](#manga-drama-video)
  - [manga-drama-video-helper](#manga-drama-video-helper)
- [插件：ai-developer-skill-plugin](#插件ai-developer-skill-plugin)
- [刷新插件副本](#刷新插件副本)

<a id="项目简介"></a>
## 项目简介

本项目提供两种使用方式：

1. **Skills 方式**：从 `skills/skills/` 复制任意技能到 `~/.codex/skills/` 即可独立使用，技能包文档见 [skills/README.md](./skills/README.md)。
2. **Plugin 方式**：安装 `plugin/ai-developer-skill-plugin` 插件，一次获得全部 9 个技能；插件内的技能是独立副本，与源技能互不影响。

技能覆盖 Java 研发现控、跨平台桌面/移动应用交付、多数据库分析、合规网络采集与反爬、AI 漫剧视频制作、Token 输出压缩等场景。

<a id="目录结构"></a>
## 目录结构

```
ai-developer/
├── .agents/plugins/marketplace.json  # Codex marketplace
├── .claude-plugin/marketplace.json   # Claude marketplace
├── .cursor-plugin/marketplace.json   # Cursor marketplace
├── .opencode/INSTALL.md              # OpenCode 安装说明
├── README.md            # 本文件
├── plugin/              # 插件包（跨桌面 Agent）
│   └── ai-developer-skill-plugin/
│       ├── .codex-plugin/plugin.json
│       ├── README.md
│       └── skills/      # 技能独立副本
└── skills/              # 技能源（权威目录）
    ├── README.md
    └── skills/          # 9 个技能本体
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

<a id="技能清单"></a>
## 技能清单

| 技能 | 用途 | 入口 |
| --- | --- | --- |
| [multi-db-analyzer](#multi-db-analyzer) | 多数据库统一查询与分析：Schema、数据质量、FK 拓扑、执行计划、HTML 报告 | [SKILL.md](./skills/skills/multi-db-analyzer/SKILL.md) |
| [java-superpowers-contract](#java-superpowers-contract) | Java 研发现控契约：最小改动、环境隔离、SQL 回滚红线、强制审计 | [SKILL.md](./skills/skills/java-superpowers-contract/SKILL.md) |
| [token-economizer](#token-economizer) | 通用 Token 精约与响应压缩引擎 | [SKILL.md](./skills/skills/token-economizer/SKILL.md) |
| [desktop-app-dev](#desktop-app-dev) | 跨平台桌面 GUI 应用交付：需求分析、框架选型、打包、验证 | [SKILL.md](./skills/skills/desktop-app-dev/SKILL.md) |
| [mobile-app-dev](#mobile-app-dev) | 跨平台移动应用交付：iOS / Android / Flutter / RN 等自动选型 | [SKILL.md](./skills/skills/mobile-app-dev/SKILL.md) |
| [scraper-unblocker](#scraper-unblocker) | 合规网络采集与媒体深爬：403 / 429 / WAF / JS 挑战诊断 | [SKILL.md](./skills/skills/scraper-unblocker/SKILL.md) |
| [anti-bot-web-scraper](#anti-bot-web-scraper) | 深度反爬数据流水线：多后端自动升级、代理池、JS 逆向 | [SKILL.md](./skills/skills/anti-bot-web-scraper/SKILL.md) |
| [manga-drama-video](#manga-drama-video) | AI 漫剧视频完整流水线：10 步审批门禁、跨集一致、配音字幕成片 | [SKILL.md](./skills/skills/manga-drama-video/SKILL.md) |
| [manga-drama-video-helper](#manga-drama-video-helper) | 漫剧轻量制作助手：剧本、素材、配音与合成 | [SKILL.md](./skills/skills/manga-drama-video-helper/SKILL.md) |

### multi-db-analyzer

纯 Python 多数据库分析工具，覆盖 MySQL、PostgreSQL、SQLite、SQL Server、Oracle、TiDB、Redis、Elasticsearch、MongoDB、InfluxDB、TDengine、Qdrant 等，支持 Schema 扫描、数据质量检查、外键拓扑、执行计划与 HTML 报告。

### java-superpowers-contract

Java 项目研发现控契约：最小改动、环境物理隔离、SQL 回滚红线、两阶段工作流、方法级锚定与全时审计。

### token-economizer

全局 Token 精约与响应压缩引擎，自动强制极简输出模式，降低 Codex 每次响应的 Token 消耗。

### desktop-app-dev

跨平台桌面应用交付技能，提供 8 步工作流、框架选型、SendInput / 窗口枚举 / 多线程模板、打包与冒烟测试模板。

### mobile-app-dev

跨平台移动应用交付技能，支持 SwiftUI、Compose、Flutter、React Native、.NET MAUI、KMP、Capacitor、Tauri 等框架的自动选型与交付。

### scraper-unblocker

专业网页采集助手，自动诊断常见反爬障碍（403、429、503、JS 挑战、Cookie 墙、WAF），支持图片、视频、HLS 深爬与分类。

### anti-bot-web-scraper

深度反爬数据流水线，自动多后端处理 Cloudflare / WAF / Turnstile，支持代理池、CAPTCHA、JS 签名与设备指纹逆向。

### manga-drama-video

端到端 AI 漫剧视频流水线，严格 10 步检查点与阶段用户确认，覆盖剧本、分镜、图片/场景生成、配音、字幕、FFmpeg / VapourSynth 后期。

### manga-drama-video-helper

漫剧轻量制作助手，从一句话故事或完整剧本出发，自动完成多集剧本、人物/场景素材、配音配乐与最终视频合成。

<a id="插件ai-developer-skill-plugin"></a>
## 插件：ai-developer-skill-plugin

插件把全部 9 个技能打包为一个可整体安装的跨桌面 Agent 插件，适合直接分发或部署：

- 插件目录：[plugin/ai-developer-skill-plugin/](./plugin/ai-developer-skill-plugin)
- 插件清单：[plugin/ai-developer-skill-plugin/.codex-plugin/plugin.json](./plugin/ai-developer-skill-plugin/.codex-plugin/plugin.json)
- 插件说明：[plugin/ai-developer-skill-plugin/README.md](./plugin/ai-developer-skill-plugin/README.md)
- 技能副本：[plugin/ai-developer-skill-plugin/skills/](./plugin/ai-developer-skill-plugin/skills)

安装：

```bash
codex plugin marketplace add https://github.com/chichengyu/ai-developer.git
codex plugin add ai-developer-skill-plugin@ai-developer
```

本地开发调试可改用：

```bash
codex plugin install ./plugin/ai-developer-skill-plugin
```

### 通用安装（推荐）

任何桌面 Agent 都可以用同一种方式：克隆仓库后运行通用安装器，脚本会自动把 9 个技能复制到已检测到的 Agent skills 目录。

```bash
git clone https://github.com/chichengyu/ai-developer.git
python3 ai-developer/scripts/install_skills.py
```

脚本默认自动检测本机已安装的桌面 Agent；`--dry-run` 可先查看安装计划。

也可以安装到所有已知 Agent，或指定任意 Agent 的 skills 目录：

```bash
python3 ai-developer/scripts/install_skills.py --all
python3 ai-developer/scripts/install_skills.py --dest <你的Agent skills目录>
```

没有 Python 环境时，直接把 `skills/skills/*` 复制到目标 Agent 的 skills 目录即可。

校验：

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ./plugin/ai-developer-skill-plugin
```

仓库已生成 `.agents/plugins/marketplace.json`，`codex plugin add` 使用的市场名为 `ai-developer`。

### 各桌面 Agent 专属方式

技能本体是标准的 `SKILL.md` 目录，可复制到任何支持 Agent Skills 的桌面端；仓库同时提供 Codex、Claude、Cursor 三个 marketplace 入口。

| Agent | 安装方式 |
| --- | --- |
| Codex 桌面端 / CLI | `codex plugin marketplace add https://github.com/chichengyu/ai-developer.git`，再执行 `codex plugin add ai-developer-skill-plugin@ai-developer` |
| Claude Code / Desktop | `/plugin marketplace add https://github.com/chichengyu/ai-developer`，再执行 `/plugin install ai-developer-skill-plugin@ai-developer` |
| Cursor | 在插件市场添加 `https://github.com/chichengyu/ai-developer`，搜索并安装 `ai-developer-skill-plugin` |
| OpenCode | 按 [.opencode/INSTALL.md](./.opencode/INSTALL.md) 安装，或让 OpenCode 执行该文件的步骤 |
| 其他桌面 Agent | 克隆仓库后，把 `skills/skills/*` 复制到该 Agent 的 skills 目录并重启 |

<a id="刷新插件副本"></a>
## 刷新插件副本

插件内是独立副本而非软链，源技能更新后需要手动同步：

```bash
$src = "./skills/skills"; $dst = "./plugin/ai-developer-skill-plugin/skills";
foreach ($d in Get-ChildItem $src -Directory) {
  Copy-Item -Path $d.FullName -Destination $dst -Recurse -Force
}
```
