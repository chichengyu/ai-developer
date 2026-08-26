---
name: manga-drama-video-helper
description: "从一句话故事、完整剧本或已有素材出发，自动生成连续多集漫剧/短剧剧本，保持人物跨集形象、声音与场景一致，完成深度分析、人物与场景素材生成、配音与BGM合成，并把剧本、素材和最终视频保存到用户指定目录。每个阶段必须保存并由用户明确确认后才继续；未指定模型时默认使用当前模型；触发场景：用户要求写漫剧剧本、做人物设定、分析人物/场景/转场/分镜、生成漫剧图片素材、生成配音/配乐/视频、续写下一集，或把故事做成可交付视频。"
---

# Manga Drama Video Helper

面向漫剧、漫画解说、短剧和抖音 9:16 竖屏视频的轻量制作助手。流程分为深度剧本分析、素材生成、视频合成三个阶段，每阶段完成后必须保存、展示并等待用户明确确认，禁止自动进入下一阶段。所有产物写入用户指定目录，并在 `manifest.json` 登记路径与来源。

## 强制审核关卡

1. 每次生成剧本后，必须把剧本、深度分析和分镜保存到用户指定目录，展示关键内容，然后停止。
2. 只有用户明确说出“继续”“继续下去”“approve”或“批准”时，才允许生成素材。
3. 素材生成后，必须把人物参考图、场景图、人物对话音频、BGM、音效、运镜方案等全部保存到用户指定目录，展示清单，然后再次停止。
4. 用户再次明确确认后，才使用当前模型生成视频时间线，并把嘴型、动作、运镜和音频对齐。
5. “好的”“可以”“不错”等回复不能代替明确确认；必须包含“继续/继续下去/approve/批准”才能解锁下一步。
6. 每次关卡状态写入 `manifest.json` 的 `phases`，当前值为 `waiting_script_review`、`waiting_asset_review` 或 `waiting_video_review`。

## 全自动执行模式

1. 用户说“全自动”“全程自动”“用户只审核”“自动流程”时，把 `manifest.json` 或 `00_series.json` 的 `flow_mode` 设为 `auto_review`。
2. 初始化项目时使用 `init_project.py --auto`，或在已有工程中直接设置 `flow_mode: auto_review`。
3. 自动模式下，Codex 自动完成 Phase 1 并保存，暂停等用户审核；用户说“继续”后自动完成 Phase 2 并保存，再暂停等审核；用户再次确认后自动完成 Phase 3。
4. 自动模式不要求用户提供额外素材、提示词或操作，用户只负责在每个关卡说“继续”或提出修改意见。
5. 多集项目每一集都重复同样流程：自动写下一集 -> 审核 -> 自动生成素材 -> 审核 -> 自动生成视频。

## 模型默认规则

1. 用户没有明确指定模型时，不做额外切换，使用当前模型完成剧本、深度分析、提示词设计和编排。
2. 用户明确指定外部模型时，才把该模型记录到 `manifest.json` 或 `00_series.json`，并在对应步骤调用它。
3. 用户只指定用途但没指定型号时，例如“用豆包生图”“用即梦生成视频”，优先使用当前可用的默认引擎和默认型号，并在 manifest 中写明实际使用的模型。
4. 同一项目内一旦选定模型，后续集数不得静默更换；更换模型必须更新 manifest 并告知用户。
5. 能力边界：当前模型/API 支持什么就使用什么。如果用户配置的云模型支持文生图、图生视频、配音、BGM 和嘴型同步，就直接由它完成对应媒体。
6. 当前模型/API 缺少某项媒体能力时，从其他云 API 或在线平台补齐，任何选择都写入 `manifest.json`，允许用户下月切换为其他模型。
7. 初始化时用 `--model-provider minimax-hailuo --model hailuo-02` 这类参数记录当前模型，或直接编辑 `model_config.json`；切换模型只改配置，不改工作流。

## 系列与续集

1. 用户要求多集、续集、下一集、系列或“继续拍下去”时，进入系列模式。
2. 新建系列运行：

```bash
python scripts/init_project.py --output-dir <series-dir> --slug <series-slug> --series --episode EP01 --aspect 9:16 --style 写实动漫
```

3. 每集开始前，先读取并锁定 `00_series.json`、`character-bible.md`、`scene-bible.md`、上一集脚本、已批准的人物/场景参考图和固定 seed。
4. 自动续写时，下一集必须承接上一集的结尾、未解决线索、人物状态和场景状态；禁止每集从零重启故事。
5. 所有跨集规则写入 `references/series-continuity.md`，Phase 1-3 都必须遵守。

## 目录与工程初始化

1. 确认或推断：故事前提、平台与画幅、目标时长、艺术风格、输出目录。
2. 若用户没有给输出目录，先问一次；不要静默写入未知位置。
3. 运行：

```bash
python scripts/init_project.py --output-dir <dir> --slug <project-slug> --aspect 9:16 --style 写实动漫
```

4. 固定工程结构：

```text
<output_dir>/
  manifest.json
  scripts/01_brief.md
  scripts/02_script.md
  scripts/03_deep_analysis.md
  scripts/04_storyboard.md
  scripts/05_jimeng_prompt_pack.md
  assets/characters/
  assets/scenes/
  assets/style/
  assets/motion/
  audio/voice/
  audio/bgm/
  audio/sfx/
  video/shots/
  video/final/
```

系列模式在 `<series-dir>` 下增加 `00_series.json`、`character-bible.md`、`scene-bible.md`，并把上述工程结构放到 `episodes/EP01/`、`episodes/EP02/` 等目录；每集有独立的 `manifest.json`，同时引用系列根目录的锁表。

## Phase 1 - 深度剧本分析

1. 读取 `references/deep-analysis-framework.md`、`references/series-continuity.md`、`references/cinematic-production.md`、`references/seedream-prompt-system.md`、`references/jimeng-seedance-prompt-system.md`。
2. 根据用户素材自动生成或改写完整剧本，写入 `scripts/02_script.md`；同时把创作要求写入 `scripts/01_brief.md`。多集项目按 `references/series-continuity.md` 生成，每集必须以 `episode_open_threads` 承接上一集，并以新的悬念结尾供下一集继续。
3. 对剧本做深度分析，写入 `scripts/03_deep_analysis.md` 和 `scripts/03_deep_analysis.json`，必须覆盖：
   - 人物：性格、动机、行为模式、外貌、声音、情绪弧线、动作节拍。
   - 场景：情绪基调、灯光、音乐、BGM 强度曲线、音效进入时间。
   - 环境：天气、风向/风速、草动、飘雪、雨、粒子、氛围层。
   - 转场：开场、切镜、叠化、甩镜、匹配剪辑，并写明原因。
   - 分镜：自动补充分镜数量、景别、运镜、镜头时长、画面提示、运动提示、音乐提示。
   - 表情情绪：每个关键镜头写人物的微表情、眼神、呼吸、眉毛和身体张力变化，禁止只写“面无表情”或“很生气”这种单一标签。
   - 跨集：本集承接了哪些线索、留给下一集哪些线索、人物状态和场景状态相比上一集发生了什么变化。
   - 运行 `python scripts/analyze_script.py <output_dir>` 自动产出确定性 `scripts/03_deep_analysis.{md,json}`（人物性格/动机/行为/外貌/声音/情绪弧线/动作节拍、场景情绪/灯光/BGM/强度曲线/音效进入时间、环境粒子、转场、镜头分镜和 image/motion prompt hint）；Codex 再基于 JSON 补全剧本特有叙事并写入 `04_storyboard.md`。系列模式下 `<output_dir>` 取集目录（`episodes/<EPNN>`），脚本会自动向上找到系列根的 `character-bible.md` 和 `scene-bible.md`。
4. 把每个镜头展开为 `scripts/04_storyboard.md`，每个镜头必须包含：
   - `shot_id`、`shot_type`、`camera_move`、`duration_sec`
   - Seedream 七层 `image_prompt`
   - Seedance 公式 `motion_text`
   - `music_cue`、`sfx`、`transition_in/out`、`transition_reason`
   - `expression_plan`、`emotion_transition`、`subtitle_zh`、`subtitle_en`
5. 保存文件并报告路径，把 `manifest.json` 的 `phases.phase_1_script` 设为 `waiting_script_review`，然后停止。用户明确确认后进入 Phase 2；用户要求修改时，修改后重新保存并再次等待确认。

## Phase 2 - 素材生成

1. 读取 `references/asset-generation.md`，按引擎优先级执行。
2. 图片素材：
   - 每个常驻人物生成 `assets/characters/<character_id>_front.png`、`_three_quarter.png`、`_expression.png`、`_action.png`。
   - 每个常驻场景生成 `assets/scenes/<scene_id>_wide.png`、`_detail.png`、`_style.png`。
   - 有上一集或系列 refs 时，必须直接复用已批准的 canonical refs，禁止用文字重新生成同一人物。
   - 用固定 seed、canonical refs 和 Seedream 多图引用锁定脸型、发型、服装、武器、场景结构；任何外观变化必须先更新角色表并获得用户确认。
3. 语音素材：
   - 旁白和每句台词各生成一个文件：`audio/voice/<line_id>.mp3`。
   - 音色、情绪和语速写入 `audio/manifest.json`，同一角色全系列复用同一音色，禁止跨集静默换声。
   - 每句台词同时写入 `text_en`，用于生成中英双语字幕。
4. 音乐素材：
   - 每场生成或选配 `audio/bgm/<scene_id>.mp3`。
   - 音效写入 `audio/sfx/<scene_id>_<beat>.mp3`，并记录进入时间。
5. 运镜素材：
   - 每个镜头生成 `assets/motion/<shot_id>_camera.json`，写入电影级运镜、镜头时长、缓动、景别、是否追焦。
   - 打斗镜头额外生成 `assets/motion/<shot_id>_fight.json`，写入预备、发力、接触、反应、收势的节拍和冲击帧。
6. 写 `assets/manifest.json` 和 `audio/manifest.json`，记录图片、音频、运镜素材的引擎、seed、prompt、来源。
7. 保存完成后展示素材清单，把 `phases.phase_2_assets` 设为 `waiting_asset_review`，然后停止。用户明确确认后才进入 Phase 3。
8. 若用户指定目录写入失败，立即停止并报告错误，不得假报已保存。

## Phase 3 - 视频合成

1. 读取 `references/cinematic-production.md` 和 `assets/motion/` 的运镜/打斗方案，再开始生成。
2. 当前模型/API 支持图生视频时，按 `04_storyboard.md` 的 `motion_text` 做图生视频，输出到 `video/shots/<shot_id>.mp4`。
3. 当前模型/API 不支持时，明确告知用户后使用 `scripts/compose_video.py --cinematic` 做静态图 + 电影缓动运镜的降级方案。
4. 说话镜头必须使用音频驱动嘴型：当前模型/API 支持时直接由它生成（例如 MiniMax-H3 `audio_url` + 人物参考图/视频），否则使用云口型 API。人物的张嘴、闭嘴、唇形变化与 `audio/voice/<line_id>.mp3` 的波形和停顿逐帧对齐；嘴型不同步视为失败。
5. 运镜使用电影级语言：推、拉、摇、移、跟、环绕、升降、甩镜都要有明确起点、终点、缓动和理由；禁止僵硬平移或镜头抖动。场景要呈现宏大空间、纵深和层次。
6. 打斗镜头必须按电影分镜拆解：预备 -> 发力 -> 接触/冲击 -> 反应 -> 收势，动作有重量、惯性、弧线和身体重心变化；禁止悬空、穿手、僵硬、四肢分离。
7. 表情和情绪必须真实：眼睛、眉毛、嘴角、呼吸、身体姿态和情绪灯光同步变化；情绪转折必须有人物内心过渡，不能瞬间换表情。
8. 生成中英双语字幕：每句台词中文一行、英文一行，时间轴与 `audio/voice/` 对齐，用 `scripts/generate_subtitles.py` 生成 SRT，并烧录到最终视频。
9. 按时间轴混合配音、BGM、音效，烧录中英双语字幕，输出 `video/final/<project-slug>_final.mp4`；系列项目输出到对应 `episodes/<EPNN>/video/final/`。
10. 用 `ffprobe` 校验时长、音视频流和缺失素材；再检查嘴型时间码、运镜流畅度、打斗连续性和双语字幕，任一失败都修复后重跑。
11. 保存最终视频，把 `phases.phase_3_video` 设为 `waiting_video_review`，展示最终视频路径并等待用户最终确认。

## 审核与降级

- 用户只要求剧本：只执行 Phase 1。
- 用户只要求素材：先运行 Phase 1 生成分析，再执行 Phase 2。
- 用户要求最终视频：仍然按 Phase 1 -> 审核 -> Phase 2 -> 审核 -> Phase 3 执行，任何阶段都不能自动跳过。
- 用户要求下一集或继续拍摄：必须先加载 `00_series.json`、角色表、场景表和上一集 refs，再生成下一集；不得重启剧情、不得重做人物长相。
- 任何 AI 生成物都要标注来源；用户提供的素材优先，禁止编造无法读取的参考资源。
- 同一个人物在任意一集出现时，都必须引用同一组 canonical refs 和 seed；跨集出现 `mismatch` 时，先回退到上一集已批准 refs，再决定是否重做。
- 若要完整 10 步审核、跨集连续性锁和更严格的 De-AI 审计，把本技能产物作为输入转交 `$manga-drama-video` 继续生产。

## Bundled resources

- `references/deep-analysis-framework.md` - 人物、场景、环境、转场、分镜深度分析模板。
- `references/series-continuity.md` - 多集自动续写、跨集人物/场景/声音锁定规则。
- `references/cinematic-production.md` - 电影级运镜、宏大场景、打斗分镜与嘴型同步规范。
- `references/seedream-prompt-system.md` - Seedream 5.0 Pro 分层提示词、参考图与坐标编辑规范。
- `references/jimeng-seedance-prompt-system.md` - 即梦 Seedance 2.0 多模态提示词、运镜与分时规范。
- `references/asset-generation.md` - 图片、配音、BGM、视频合成引擎优先级与命令。
- `assets/analysis_template.md` - 深度分析 Markdown 模板。
- `assets/storyboard_template.md` - 分镜表模板。
- `assets/jimeng_prompt_pack_template.md` - 即梦在线提示词包模板。
- `assets/series_manifest_template.json` - 系列连续性清单模板。
- `assets/asset_manifest_template.json` - 图片素材清单模板。
- `assets/audio_manifest_template.json` - 音频素材与时间轴模板。
- `scripts/init_project.py` - 初始化用户输出目录。
- `scripts/analyze_script.py` - 对已批准剧本自动产出确定性 `03_deep_analysis.{md,json}`（同主技能 Step 2 的分析器，自动读取 `scripts/02_script.md`、`manifest.json` 和系列根的 `character-bible.md`/`scene-bible.md`）。
- `scripts/seedream_generate.py` - 调用 Doubao Seedream API 生成或编辑图片。
- `scripts/compose_video.py` - 用 ffmpeg 合成最终视频。
- `scripts/generate_subtitles.py` - 从音频清单生成中英双语 SRT。
