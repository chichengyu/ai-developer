# AI Developer Skill Plugin 插件

<p align="center">
  <img src="https://img.shields.io/badge/Codex%20Plugin-v1.0.0-blueviolet" alt="Codex Plugin" />
  <img src="https://img.shields.io/badge/Built-in%20Skills-9-blue" alt="9 built-in skills" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" />
</p>

一个跨桌面 Agent 的技能插件包，把仓库内的 9 个技能打包为单一可安装单元。插件目录为 `plugin/ai-developer-skill-plugin/`，并在 `./skills/` 下保存全部技能的独立副本，可脱离源技能树单独打包、分发和安装。

## 目录结构

```
plugin/ai-developer-skill-plugin/
├── .codex-plugin/
│   └── plugin.json        # Codex 插件清单
├── README.md              # 本文件
└── skills/                # 源技能的独立副本
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

## 内置技能

插件一次安装 9 个技能，按使用场景分为 4 组：

| 场景 | 技能 |
| --- | --- |
| **研发工程** | [`java-superpowers-contract`](./skills/java-superpowers-contract/SKILL.md) · [`multi-db-analyzer`](./skills/multi-db-analyzer/SKILL.md) · [`token-economizer`](./skills/token-economizer/SKILL.md) |
| **应用交付** | [`desktop-app-dev`](./skills/desktop-app-dev/SKILL.md) · [`mobile-app-dev`](./skills/mobile-app-dev/SKILL.md) |
| **网络采集** | [`scraper-unblocker`](./skills/scraper-unblocker/SKILL.md) · [`anti-bot-web-scraper`](./skills/anti-bot-web-scraper/SKILL.md) |
| **漫剧视频** | [`manga-drama-video`](./skills/manga-drama-video/SKILL.md) · [`manga-drama-video-helper`](./skills/manga-drama-video-helper/SKILL.md) |

### 研发工程

| 技能 | 说明 | 入口 |
| --- | --- | --- |
| [java-superpowers-contract](./skills/java-superpowers-contract/SKILL.md) | Java 研发现控契约：最小改动、环境隔离、SQL 回滚红线、审计 | [SKILL.md](./skills/java-superpowers-contract/SKILL.md) |
| [multi-db-analyzer](./skills/multi-db-analyzer/SKILL.md) | 多数据库分析：SQL / NoSQL / 时序 / 向量库查询与报告 | [SKILL.md](./skills/multi-db-analyzer/SKILL.md) |
| [token-economizer](./skills/token-economizer/SKILL.md) | 全局 Token 精约与响应压缩引擎 | [SKILL.md](./skills/token-economizer/SKILL.md) |

### 应用交付

| 技能 | 说明 | 入口 |
| --- | --- | --- |
| [desktop-app-dev](./skills/desktop-app-dev/SKILL.md) | 跨平台桌面 GUI 应用交付（Windows / macOS / Linux），8 步工作流 | [SKILL.md](./skills/desktop-app-dev/SKILL.md) |
| [mobile-app-dev](./skills/mobile-app-dev/SKILL.md) | 跨平台移动应用交付：iOS / Android / visionOS / Wear OS 自动选型 | [SKILL.md](./skills/mobile-app-dev/SKILL.md) |

### 网络采集

| 技能 | 说明 | 入口 |
| --- | --- | --- |
| [scraper-unblocker](./skills/scraper-unblocker/SKILL.md) | 稳健爬虫：自动反爬诊断与多后端重试 | [SKILL.md](./skills/scraper-unblocker/SKILL.md) |
| [anti-bot-web-scraper](./skills/anti-bot-web-scraper/SKILL.md) | 深度反爬数据流水线：Cloudflare / WAF / Turnstile、代理池、JS 逆向 | [SKILL.md](./skills/anti-bot-web-scraper/SKILL.md) |

### 漫剧视频

| 技能 | 说明 | 入口 |
| --- | --- | --- |
| [manga-drama-video](./skills/manga-drama-video/SKILL.md) | AI 漫剧视频端到端流水线，严格检查点与用户确认门禁 | [SKILL.md](./skills/manga-drama-video/SKILL.md) |
| [manga-drama-video-helper](./skills/manga-drama-video-helper/SKILL.md) | 漫剧制作助手：剧本、素材生成、配音与最终合成 | [SKILL.md](./skills/manga-drama-video-helper/SKILL.md) |

## 安装

仓库根目录已提供 Codex、Claude、Cursor 三个 marketplace 入口，可直接从远程仓库安装：

```bash
codex plugin marketplace add https://github.com/chichengyu/ai-developer.git
codex plugin add ai-developer-skill-plugin@ai-developer
```

本地开发调试可改用：

```bash
codex plugin install ./plugin/ai-developer-skill-plugin
```

### 远程安装（所有桌面 Agent）

所有远程安装方式都不依赖 Python：

| Agent | 远程安装方式 |
| --- | --- |
| Claude Code / Desktop | `/plugin marketplace add chichengyu/ai-developer`，再执行 `/plugin install ai-developer-skill-plugin@ai-developer` |
| Cursor | 在插件市场添加 `https://github.com/chichengyu/ai-developer`，搜索并安装 `ai-developer-skill-plugin` |
| OpenCode | 按 [.opencode/INSTALL.md](../../.opencode/INSTALL.md) 安装 |
| 其他支持 Git marketplace 的 Agent | 添加 `https://github.com/chichengyu/ai-developer`，再安装 `ai-developer-skill-plugin` |

OpenCode 可以直接输入：

```text
Fetch and follow instructions from https://raw.githubusercontent.com/chichengyu/ai-developer/main/.opencode/INSTALL.md
```

## 校验

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ./plugin/ai-developer-skill-plugin
```

## 与源技能的关系

`plugin/ai-developer-skill-plugin/skills/` 下的 9 个技能目录是 [`skills/`](../../skills/skills) 原始目录的独立副本，用于保证插件可以独立安装、版本化和分发。插件副本与源技能互不影响；源技能更新后，需要重新同步副本：

```powershell
$src = "../../skills/skills"; $dst = "./skills";
foreach ($d in Get-ChildItem $src -Directory) {
  Copy-Item -Path $d.FullName -Destination $dst -Recurse -Force
}
```
