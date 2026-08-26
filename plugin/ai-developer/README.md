# AI Developer 插件

一个 Codex 个人插件，把仓库内的 9 个技能打包为单一可安装单元。插件目录为 `plugin/ai-developer/`，并在 `./skills/` 下保存全部技能的独立副本，可脱离源技能树单独打包、分发和安装。

## 目录结构

```
plugin/ai-developer/
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

| 技能 | 用途 | 入口 |
| --- | --- |
| [anti-bot-web-scraper](./skills/anti-bot-web-scraper/SKILL.md) | Cloudflare / WAF / Turnstile 绕过、CAPTCHA 处理、代理轮换、声明式数据处理 | [SKILL.md](./skills/anti-bot-web-scraper/SKILL.md) |
| [desktop-app-dev](./skills/desktop-app-dev/SKILL.md) | 跨平台桌面 GUI 应用交付（Windows / macOS / Linux），8 步工作流 | [SKILL.md](./skills/desktop-app-dev/SKILL.md) |
| [java-superpowers-contract](./skills/java-superpowers-contract/SKILL.md) | Java 研发现控契约：最小改动、环境隔离、SQL 回滚红线、审计 | [SKILL.md](./skills/java-superpowers-contract/SKILL.md) |
| [manga-drama-video](./skills/manga-drama-video/SKILL.md) | AI 漫剧视频端到端流水线，严格检查点与用户确认门禁 | [SKILL.md](./skills/manga-drama-video/SKILL.md) |
| [manga-drama-video-helper](./skills/manga-drama-video-helper/SKILL.md) | 漫剧制作助手：剧本、素材生成、配音与最终合成 | [SKILL.md](./skills/manga-drama-video-helper/SKILL.md) |
| [mobile-app-dev](./skills/mobile-app-dev/SKILL.md) | 跨平台移动应用交付：iOS / Android / visionOS / Wear OS 自动选型 | [SKILL.md](./skills/mobile-app-dev/SKILL.md) |
| [multi-db-analyzer](./skills/multi-db-analyzer/SKILL.md) | 多数据库分析：SQL / NoSQL / 时序 / 向量库查询与报告 | [SKILL.md](./skills/multi-db-analyzer/SKILL.md) |
| [scraper-unblocker](./skills/scraper-unblocker/SKILL.md) | 稳健爬虫：自动反爬诊断与多后端重试 | [SKILL.md](./skills/scraper-unblocker/SKILL.md) |
| [token-economizer](./skills/token-economizer/SKILL.md) | 全局 Token 精约与响应压缩引擎 | [SKILL.md](./skills/token-economizer/SKILL.md) |

## 安装

插件为本地插件，当前未生成 `marketplace.json`，可直接让 Codex 读取插件清单：

```bash
codex plugin install ./plugin/ai-developer
```

如需生成个人市场条目，可用 plugin-creator 脚手架重跑并加上 `--with-marketplace`。

## 校验

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py ./plugin/ai-developer
```

## 与源技能的关系

`plugin/ai-developer/skills/` 下的 9 个技能目录是 [`skills/`](../../skills/skills) 原始目录的独立副本，用于保证插件可以独立安装、版本化和分发。插件副本与源技能互不影响；源技能更新后，需要重新同步副本：

```powershell
$src = "../../skills/skills"; $dst = "./skills";
foreach ($d in Get-ChildItem $src -Directory) {
  Copy-Item -Path $d.FullName -Destination $dst -Recurse -Force
}
```
