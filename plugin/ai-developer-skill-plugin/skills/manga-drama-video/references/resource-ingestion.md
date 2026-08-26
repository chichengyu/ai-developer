# 资源自动读取与运用（Resource Ingestion）

本文件用于 Step 0/1。用户提供的任何资源都必须先被 AI 自动读取、分析、总结并登记，之后才能用于剧本、人物、场景、风格、配音或成片。资源无法读取时，如实记录为 `blocked`，禁止编造内容。

## 支持的资源类型

| 类型 | 示例 | 自动处理方式 |
| --- | --- | --- |
| URL / 网页 | 知乎文章、B站页、视频页、图片页 | 浏览器 / open_page / curl 读取正文、标题、标签、元数据 |
| 视频 | mp4、mov、mkv、视频链接 | ffprobe 读时长/分辨率；ffmpeg 抽关键帧、抽音频、抽字幕 |
| 音频 | mp3、wav、m4a、音频链接 | ffprobe 读时长；ASR 转写；分析人声风格、BGM、情绪 |
| 图片 | png、jpg、webp、参考图 | 直接查看；提取人物、场景、配色、镜头、材质、风格 |
| 文本 | 小说、剧本、设定、聊天记录、PDF、docx | 读取并总结角色、主线、台词、世界观、文风 |
| 字幕 | srt、ass、vtt | 读取时间码和台词，作为对白/节奏参考 |
| 已有项目 | 本 skill 的 outputs | 读取 `00_series.json`、bibles、style-lock、engine_plan |

## 必写文件

每次资源处理完成后必须写入：

- `resource_manifest.json`：机器可读的资源登记表。
- `00_resources.md`：人类可读的资源总结，写明每条资源如何被使用。

文件放在 Step 0 所在的根目录：单集放 `outputs/<project-slug>/`，系列放 `outputs/<series-slug>/`。

## `resource_manifest.json` schema

```json
{
  "resource_manifest_version": 1,
  "resources": [
    {
      "resource_id": "r1",
      "type": "url | video | audio | image | text | subtitle | project",
      "source": "原始地址或路径",
      "local_path": "本地副本，可为 null",
      "status": "ok | partial | blocked",
      "summary": "AI 分析总结，2-5 句",
      "usage": ["character_ref", "scene_ref", "style_ref", "voice_ref", "bgm", "script_ref", "motion_ref"],
      "engines": ["browser", "ffmpeg", "asr", "ocr", "imagegen", "speech"]
    }
  ],
  "blocked": ["无法读取的资源及原因"]
}
```

## 读取规则

1. **先保存，再分析。** 远程资源尽量下载或复制到 `outputs/.../resources/`，无法保存时记录 `source` 和读取结果。
2. **URL 被反爬/验证码拦截**：标记 `blocked`，说明状态码和原因，向用户要正文、截图或本地文件，不编造内容。
3. **视频资源**：用 ffprobe 读时长、分辨率、音轨；用 ffmpeg 抽 3-5 张关键帧和一段音频；需要时用 ASR 转写台词。
4. **音频资源**：分析时长、语速、情绪、音色、BGM；作为配音或音乐参考时要标注用途。
5. **图片资源**：分析人物、脸型、服装、配色、场景、镜头、材质；作为 canonical ref 或 style ref 时必须登记并锁定 seed。
6. **文本资源**：提取人物关系、主线、分集结构、对白风格、世界观；原文较长时先总结再选用。
7. **已有项目资源**：直接读取 bibles、style-lock、engine_plan，不重新发明人物和场景。
8. **版权处理**：用户资源只做风格、设定和参考，不直接复制受版权保护的剧照、配音或完整文案。

## 如何运用到项目

- 人物资源 -> Step 0 `character-bible.md` 的 `prompt_fragment`、canonical refs。
- 场景资源 -> Step 0 `scene-bible.md`。
- 风格资源 -> Step 4 `04_art_direction.md` 和 `style-lock.json`。
- 声音资源 -> Step 6 voice cast / BGM。
- 文本/剧本资源 -> Step 2 `02_script.md` 和 `02_character_analysis.md`。
- 视频运镜资源 -> Step 3 分镜和 `references/shot-camera-and-fight-language.md`。
- 用户明确指定某资源必须使用某引擎时，写入 `engine_plan.json` 的 `user_overrides`。
