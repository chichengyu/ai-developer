---
name: manga-drama-video
description: "Generate a 漫剧 / manga-style drama video end-to-end with strict 10-step checkpoints and mandatory user review between every step, including resource ingestion, engine orchestration, series continuity lock, script, character analysis, storyboard, fight/camera breakdown, art direction, image and scene generation, voice acting / 配音, subtitles, final composition, and FFmpeg/VapourSynth post-processing. Cross-episode consistency and de-AI checks are mandatory: canonical refs and seeds lock every face forever, and images, motions, lip sync, subtitles, and final cuts must pass anti-AI checks. Use when the user asks to make a 漫剧, 漫剧视频, 漫画解说视频, 2026 爆款 AI 漫剧, 3D 国风动漫, 国漫仙侠, AI manga drama, 写实动漫, 数字真人 短视频, 抖音漫剧, 9:16 vertical manga video, or any story-to-video pipeline that pauses for user approval at each stage. Default character style is 写实动漫 (hyper-real anime) with 真实逼真、轮廓分明 rendering; supports 数字真人 (photoreal digital human) mode and 经典动漫 / 美漫 / 水墨 / 治愈手绘 / 赛博朋克 / 2026 AI 漫剧爆款男主风格 / 3D 国风仙侠 variants."
---

# Manga Drama Video (漫剧视频) Workflow

Strict, gated, 10-step pipeline (Step 0-9) that turns a one-line idea into a finished manga-drama video, including multi-episode series continuity. Every step produces a real artifact in `outputs/`, pauses, and waits for the user to approve or revise before the next step begins. Motion is generated through the currently configured model/engine: cloud models/APIs such as Minimax/Hailuo, Jimeng/Seedance, and Doubao are supported; local ComfyUI + Wan / HunyuanVideo / LTX-Video is only one optional mode. Static frames + Ken Burns remain an explicitly approved fallback. Voice acting (配音) is mandatory. Default character look is **写实动漫** (hyper-real anime, sharp outlines, lifelike skin); the user can opt into full **数字真人** (photoreal digital human) per scene.

## Trigger

Activate when the user says things like:

- 做一条漫剧 / 漫剧视频 / 漫画解说视频 / 写实动漫 / 数字真人短视频
- 抖音漫剧 / 小红书漫剧 / B站漫剧
- 做漫剧系列 / 下一集 / 第2集 / 继续上一集的人物和场景
- make a manga drama / comic drama short / AI panel-style short / vertical 9:16 AI manga
- from this story make a 30s talking-head manga video with voiceover
- Use $manga-drama-video to ...

If only a single stage is wanted (e.g. just images, just voice), confirm scope; still run Step 0 bible lock when any recurring character or scene is involved, then run only that stage, with a review gate at the end.

## Hard rules

1. **Never skip a step.** Do not start step N+1 until step N is approved. Step 0 is mandatory for every project.
2. **Never merge steps.** Script, storyboard, art direction, images, voice, subtitles, composition are separate artifacts.
3. **Always pause for review.** Present the artifact, list options, stop. Wait for an explicit reply.
4. **Always write to disk before pausing.** Save one-off artifacts under `outputs/<project-slug>/`; save series artifacts under `outputs/<series-slug>/episodes/<episode-slug>/`.
5. **Always include 配音.** Ask at Step 6 if the user has not named a TTS provider.
6. **Never auto-proceed on a bare ok.** Echo back which artifact is being locked and require an explicit `approve step N` or `revise step N: <change>`.
7. **Default character style is 写实动漫.** Pre-realistic anime with 真实逼真 skin texture and 轮廓分明 2-3px outlines, plus modern cinematic lighting. Never use plastic or oily beauty filters. Switch to 数字真人 per scene only if the user asks.
8. **Aspect ratio and platform are decided in Step 1.** Step 5, 7, 8 read them from the brief, never re-ask.
9. **Cross-episode consistency is mandatory.** Every series must have `00_series.json`, `character-bible.md`, `scene-bible.md`, `style-lock.json`, and canonical reference images. A new episode must load the previous episode's approved refs and seeds before generating anything.
10. **Locked faces never change silently.** If the user changes a character's appearance, update the bible first, bump `continuity_version`, regenerate canonical refs, and ask whether old episodes must be redone.
11. **自动生成草稿后再审核。** Codex 自动生成剧本、人物分析、分镜、打斗镜头、运镜、场景绘制、参考图和分镜图草稿；每一阶段必须先写文件，再暂停等待用户审核。禁止给用户空模板。
12. **去 AI 味是硬性要求。** 每一张图、每段动作、每个口型、每句配音、每条字幕和最终成片都必须通过 `references/deai-artifact-removal.md` 检查；任何 `fail` 都不能进入下一阶段。
13. **所有内容可自动生成，也可由用户指定。** 用户提供的 URL、视频、音频、图片、文本、字幕或已有项目必须先被自动读取、分析并登记；用户指定引擎后必须写入 `engine_plan.json` 并遵守，禁止静默替换。
14. **真动态优先。** 默认 `motion_mode: video-diffusion`：每镜头先生成关键帧，再用当前配置的模型/API 生成真动态片段，说话镜头再用音频驱动口型。`still-kenburns` 只能作为用户明确同意的降级模式。
15. **禁止静默降级。** 当前模型/API、视频引擎或口型引擎不可用时，必须先暂停、展示检测结果，问用户配置云 API、安装本地引擎、接受降级还是跳过；任何降级都要写进 `STATE.md.notes` 和 `04_art_direction.md`。
16. **用户指定目录优先落盘。** 用户提供输出目录时，`00_meta.json` 写入 `output_root`；每个步骤写完真实产物后，同步到 `<output_root>/scripts/<slug>`、`<output_root>/images/<slug>`、`<output_root>/videos/<slug>`（音频到 `<output_root>/audio/<slug>`）。未指定时继续使用 `outputs/<slug>/` 工作区，不改变既有流程。
17. **脚本化审批门禁。** 每一步开始前运行 `python scripts/approval_gate.py <project_dir> --step N --action check`，返回 0 才继续；用户明确批准后运行 `python scripts/approval_gate.py <project_dir> --step N --action approve`；用户要求修改时运行 `python scripts/approval_gate.py <project_dir> --step N --action revise` 后重做当前步骤。首次执行 Step 0 且 `STATE.md` 不存在时，先写基础 STATE，再在用户批准后标记。

## 最高约束：跨集人物一致性

1. **同一张脸，永远是同一张脸。** 张三在 EP01 长什么样，EP02、EP10 就必须长什么样。人物的脸型、五官比例、发型、体型、服装配色、声音、seed 和 canonical refs 一旦在 Step 0 锁定，就不能在后续集数中“重新生成”。
2. **canonical refs 是唯一允许的脸部来源。** 新一集开始前，必须先加载 `outputs/<series-slug>/refs/` 中已批准的参考图；禁止只写“保持上一集一样”但不传参考图，禁止用文字重新创建角色。
3. **任何外观变更必须走流程。** 用户想改发型、服装、脸型、体型或换数字真人模式时，必须先更新 `character-bible.md` / `scene-bible.md`，在 Step 0 获得 `approve continuity change`，再重新生成 canonical refs，并询问是否回炉重做旧集。
4. **一致性 mismatch 是硬阻断。** 任何角色或场景在 Step 5 审计中出现 `mismatch`，不得进入 Step 6，更不得进入 Step 8；必须用 canonical refs 和锁定 seed 重做对应镜头。
5. **自动划分也必須继承一致性。** 剧本、人物分析、分镜、打斗镜头、运镜和场景绘制都使用同一套 character/scene `prompt_fragment`，禁止某一集单独换建模语言。

## 最高约束：去 AI 味

1. **每个 image_prompt 必须追加去 AI 味 Prompt anchor。** 自然姿势、正确肢体、自然手部、闭合嘴型、真实皮肤、无乱码文字、光影一致。
2. **动作必须有重量和连续性。** 禁止悬浮、僵硬、四肢分离、武器穿手、动作断点；打斗必须按“预备 -> 发力 -> 击中 -> 反应 -> 收势”拆解。
3. **口型必须和配音匹配。** 非说话镜头嘴巴闭合；说话/喊叫镜头才张嘴；数字真人口型驱动必须音画同步。
4. **配音、字幕、成片都要过 De-AI Audit。** 机器人式 TTS、错误说话人、错位时间码、机翻字幕、跳帧、音画不同步都直接判 `fail`。

## 最高约束：资源与引擎

1. **用户资源必须自动读取。** URL、视频、音频、图片、文本、字幕和已有项目都按 `references/resource-ingestion.md` 处理，并写入 `resource_manifest.json` 和 `00_resources.md`。
2. **默认自动，用户指定优先。** 所有字段默认由 Codex 自动生成；用户指定引擎时写入 `engine_plan.json` 的 `user_overrides`，后续步骤必须使用该引擎。
3. **资源读取失败不能编造。** URL 被反爬、视频无法解码、音频无法转写时，标记 `blocked`，向用户要正文、截图或本地文件。
4. **引擎编排必须有记录。** `engine_plan.json` 是 Step 0 必产物，生产步骤开始前必须读取或刷新。
5. **图片引擎必须自持，禁止外部手工回流。** Step 5 直接调用当前配置的模型/API、Codex imagegen skill/MCP 或本机图片引擎生成图片素材；禁止要求用户复制提示词到外部网站再放回文件夹，除非用户明确选择手工回流并写入 `engine_plan.json` 的 `user_overrides`。

## Output layout

`outputs/<slug>` 永远是引擎工作区。用户指定 `output_root` 后，每个步骤在暂停前运行 `scripts/export_outputs.py`，把已生成/待审产物同步到四类用户目录：

```text
# User-facing output root (when output_root is set)
<output_root>/
  manifest.json
  scripts/<slug>/      01_brief.md, 02_script.md, 02_script_analysis.md, 03_storyboard.md, 04_art_direction.md,
                       character-bible.md, engine_plan.json, 07_subtitles.srt, ...
  images/<slug>/       refs/, 05_images/
  videos/<slug>/       05_video/, 06_face/, 08_final*.mp4, 09_final_enhanced*.mp4
  audio/<slug>/        06_voice/
```

```
# Series (multi-episode)
outputs/<series-slug>/
  00_series.json
  character-bible.md
  scene-bible.md
  style-lock.json
  00_resources.md
  resource_manifest.json
  engine_plan.json
  reference_bundle.json
  reference_bundle_report.md
  resources/
  refs/<character_id>_*.png
  refs/<scene_id>_*.png
  episodes/EP01/
    00_meta.json
    STATE.md
    01_brief.md
    02_script.md
    02_character_analysis.md
    02_script_analysis.md
    02_script_analysis.json
    03_storyboard.md
    04_art_direction.md
    05_images/<shot_id>.png
    05_images/manifest.json
    05_images/continuity_audit.md
    05_images/deai_audit.md
    05_video/<shot_id>.mp4
    05_video/manifest.json
    05_video/continuity_audit.md
    05_video/deai_audit.md
    06_voice/<scene_id>__<line_index>.<ext>
    06_voice/index.json
    06_face/<shot_id>_lip.mp4
    06_face/index.json
    06_face/lip_sync_report.md
    07_subtitles.srt
    07_timeline.json
    video_workflow.json
    talking_head_workflow.json
    08_final.mp4
    08_final_with_subs.mp4
    08_deai_check.md
    09_final_enhanced.mp4
    09_final_enhanced_with_subs.mp4
    09_postprocess_report.md
    09_install_report.md
    09_deai_check.md

# One-off (single video)
outputs/<project-slug>/
  character-bible.md
  scene-bible.md
  style-lock.json
  00_resources.md
  resource_manifest.json
  engine_plan.json
  reference_bundle.json
  reference_bundle_report.md
  resources/
  00_meta.json
  STATE.md
  01_brief.md
  02_script.md
  02_character_analysis.md
  02_script_analysis.md
  02_script_analysis.json
  03_storyboard.md
  04_art_direction.md
  05_images/<shot_id>.png
  05_images/manifest.json
  05_images/continuity_audit.md
  05_images/deai_audit.md
  05_video/<shot_id>.mp4
  05_video/manifest.json
  05_video/continuity_audit.md
  05_video/deai_audit.md
  06_voice/<scene_id>__<line_index>.<ext>
  06_voice/index.json
  06_face/<shot_id>_lip.mp4
  06_face/index.json
  06_face/lip_sync_report.md
  07_subtitles.srt
  07_timeline.json
  video_workflow.json
  talking_head_workflow.json
  08_final.mp4
  08_final_with_subs.mp4
  08_deai_check.md
  09_final_enhanced.mp4
  09_final_enhanced_with_subs.mp4
  09_postprocess_report.md
  09_install_report.md
  09_deai_check.md
```

Slug rules: lowercase, hyphenated, <= 40 chars. If the user does not supply one, derive from the premise. For a series, create `outputs/<series-slug>/` in Step 0 and the episode folder in Step 1. Write `00_meta.json` at the same time with the locked Step 1 values so downstream steps never re-ask.

`STATE.md` schema (write whenever the user says `stop`, or whenever the workflow resumes):

```markdown
# STATE — <project-slug>

- last_completed_step: <0..9>
- next_pending_step: <1..9>
- series_slug: <series-slug or null>
- episode_number: <EPNN or null>
- output_root: <absolute dir or null>
- continuity_version: <n>
- aspect_ratio: <9:16 | 16:9 | 1:1>
- resolution: <720p | 1080p | 4K>
- framerate: <24 | 30 | 60>
- target_length_sec: <n>
- motion_mode: <video-diffusion | talking-head-only | still-kenburns>
- character_style: <写实动漫 | 数字真人 | 经典动漫 | 美漫 | 水墨 | 治愈手绘 | 赛博朋克 | ...>
- tts_provider: <id>
- voice_cast: {narrator: <id>, ...}
- shots_total: <n>
- shots_approved: <n>
- continuity_audit: <pending | match | needs_review | mismatch>
- deai_audit: <pending | pass | fail>
- resource_manifest: <pending | ok | blocked>
- engine_plan: <pending | ok>
- reference_bundle: <pending | ok | blocked>
- postprocess_plan: <pending | ok | blocked>
- output_export: <pending | ok | blocked>
- notes: <free text>
```

## Step 0 — Series continuity & character bible

Mandatory for every project. This step decides whether characters and scenes are locked for a single video or across a whole series.

1. Determine project type:
   - One-off: create `character-bible.md` and `scene-bible.md` in `outputs/<project-slug>/`. They can be lightweight, but every recurring character and recurring location must still be locked before image generation.
   - Series: use `outputs/<series-slug>/` and `outputs/<series-slug>/episodes/<EPNN>/`. If the series already exists, load `00_series.json`, `character-bible.md`, `scene-bible.md`, `style-lock.json`, and every canonical ref from `refs/` before doing anything else.
2. If this is a new series, analyze the premise and auto-generate:
   - `00_series.json` from `assets/series_manifest_template.json`
   - `character-bible.md` from `assets/character_bible_template.md`
   - `scene-bible.md` from `assets/scene_bible_template.md`
   - `style-lock.json` with the locked `character_style`, global `style_seed`, palette, and anti-drift rules
   - Set `episodes: ["EP01"]` and `last_episode: "EP01"`; every later episode must append itself to `00_series.json.episodes` before generating images.
3. For every recurring character, define a stable `character_id`, name, role, face geometry, hairstyle, body type, wardrobe variants, palette, props, voice placeholder, and reusable `prompt_fragment`. Never use a display name that changes between episodes.
4. For every recurring scene, define `scene_id`, structure, palette, lighting, props, and reusable `prompt_fragment`. Lock one seed per scene for the series.
5. Read `references/resource-ingestion.md`, `references/composition-and-multi-reference.md`, `references/seedream-prompt-system.md`, and `references/jimeng-seedance-motion-language.md`, then process every user-provided resource (URL / video / audio / image / text / subtitle / existing project) and write `resource_manifest.json` + `00_resources.md`. Run `python scripts/process_reference_bundle.py <project_dir> --input resources` to build the 9-image / 3-video / 3-audio `reference_bundle.json`; each slot keeps its Seedream/Seedance semantic (identity, scene, style, composition, motion, camera, voice, SFX). Blocked resources must be listed without fabricating content, missing reference slots stay `null` and are filled by generated refs after Step 5.
6. Read `references/engine-orchestration.md` and `references/cloud-model-orchestration.md`, then record the current model in `model_config.json` (same schema as `manga-drama-video-helper`; provider/model/roles) and run `python scripts/engine_plan.py <project_or_series_dir>` (use `python` first; `py -3` only when the Python launcher is installed) to generate `engine_plan.json`. If the user has configured a current cloud model/API (Minimax/Hailuo, Jimeng/Seedance, Doubao, etc.), record it under `engines` and `user_overrides`, then verify the API key and endpoint are reachable. Only install local video engines when the user explicitly selects local mode; in that case read `references/video-motion-generation.md` and run `python scripts/install_video_engine.py <project_or_series_dir> --check` first. If the project will use real motion, the configured model/API or local engine must pass `python scripts/engine_plan.py <project_or_series_dir> --check --require-motion` before Step 1.
7. Read `references/series-continuity.md` before finishing this step. Do not skip the cross-episode rules.
8. Pause.

Pause. Ask: `Approve Step 0 bible, resources, and engine plan, or revise? Reply with "approve step 0" or "revise step 0: <changes>".`

## Step 1 — Creative brief (`01_brief.md`, `00_meta.json`)

Collect, in this exact order, and write both files:

1. Premise (one sentence).
2. Genre (都市 / 古风 / 悬疑 / 校园 / 玄幻 / 科幻 / 治愈 / other).
3. Platform and aspect ratio:
   - 抖音 / 小红书 / YouTube Shorts → **9:16**, 1080x1920.
   - B站 / YouTube → **16:9**, 1920x1080.
   - 小红书横版 / 公众号 → **1:1**, 1080x1080.
   - Other → ask.
4. Resolution (720p / 1080p / 4K; default 1080p).
5. Framerate (24 / 30 / 60; default 30).
6. Target length (15 / 30 / 60 / 90s; default 30).
7. Motion mode (default `video-diffusion`; `talking-head-only` for static frames plus lip-synced faces; `still-kenburns` only after user confirms no current video model/API). Write it as `motion_mode` in `00_meta.json`.
8. Number of shots = clamp(round(length / 4), 4, 16). Write this value as `shots_total` in `00_meta.json`.
9. Character style (default **写实动漫**; switch to **数字真人** if the user wants photoreal humans).
10. Audience + tone.
11. Art style keywords.
12. Voiceover language and style (普通话 / 粤语 / English; narrator / dialogue / mixed).
13. Must-include elements.
14. If series: `is_series: true`, `series_slug`, `episode_number`, `continuity_version` must come from Step 0 and be written into `00_meta.json`.
15. If one-off: `is_series: false` and `continuity_version: 1`.
16. Every field defaults to auto-generation; the user may specify any field. User-specified values are locked in `00_meta.json` and `engine_plan.json`, and must not be silently overwritten.
17. Output directory (optional). Ask for one path; if provided, write `output_root` as an absolute path and write `output_dirs` (`scripts` / `images` / `videos` / `audio`) into `00_meta.json`. Downstream steps use `scripts/export_outputs.py` to sync artifacts there.

Write `00_meta.json` first; downstream steps read from it. For a series, write it inside `outputs/<series-slug>/episodes/<EPNN>/`. Write `01_brief.md` using `assets/storyboard_template.md` Section A.
After writing the brief, run `python scripts/export_outputs.py <project_dir> --kind scripts` so `00_meta.json` and `01_brief.md` appear in `<output_root>/scripts/<slug>/` when a directory was specified.

Pause. Ask: `Approve Step 1 brief, or revise? Reply with "approve step 1" or "revise step 1: <changes>".`

## Step 2 — Script (`02_script.md`)

Auto-generate the full scene-level script and the episode character analysis before pausing. Do not present a blank template.

1. Read `00_meta.json`, `00_resources.md`, `resource_manifest.json`, `references/seedream-prompt-system.md`, `references/jimeng-seedance-motion-language.md`, and, for series, `character-bible.md`.
2. Generate `02_script.md`. Each scene:

- `scene_id` (S1, S2, ...)
- `location`
- `duration_sec`
- `character_style_override` (optional; `null` inherits Step 1 default, set to `数字真人` for a live-action close-up, or `写实动漫` to force hyper-real anime).
- `summary` (1-2 sentences)
- `music` (optional; `analyze_script.py` auto-fills BGM mood, tempo, instruments, intensity curve)
- `environment` (optional; `analyze_script.py` auto-fills weather, wind, grass, snow, rain, particles, atmosphere)
- `shot_plan` (list of {shot_id, duration_sec, shot_type, camera_move, action_beat, sfx, lip_motion}; the shot durations must sum to the scene duration, and the total to target length)
- `dialogue` (list of {speaker, line})
- `narration` (TTS-friendly, <= 18 zh chars or <= 14 en words; declarative, no stage directions)
- `emotion_beat` (single adjective)
- `no_vo` (true for visual-only scenes)

3. Sum of `duration_sec` must equal target length. If it does not, rebalance before pausing.
4. Write `02_script.json` with the same scene data as machine-readable output; `shot_plan` is mandatory so Step 3 starts from a shootable structure instead of prose.
5. Generate `02_character_analysis.md`, one block per appearing character:
   - `character_id` (must match the bible)
   - `episode_goal`
   - `emotional_arc`
   - `actions`
   - `wardrobe_state` (same outfit / new variant)
   - `voice_tone`
   - `continuity_notes` (nothing here may change locked appearance)
6. For series episodes, the script and analysis must reuse the same character IDs and voice cast as previous episodes.

After writing `02_script.md` / `02_script.json` / `02_character_analysis.md`, run `python scripts/analyze_script.py <project_dir>` to automatically generate `02_script_analysis.md` and `02_script_analysis.json`. The analyzer fills character personality/behavior/appearance, scene music, wind/grass/snow/rain environment dynamics, transitions, and shot-level image/motion prompt hints without asking the user to fill anything in. Then run `python scripts/export_outputs.py <project_dir> --kind scripts` before pausing.

Pause. Ask: `Approve Step 2 script, character analysis, and deep analysis, or revise?`

## Step 3 — Storyboard (`03_storyboard.md`)

Auto-generate the complete shot-level storyboard before pausing. Read `references/shot-camera-and-fight-language.md`, `references/video-motion-generation.md`, `references/seedream-prompt-system.md`, `references/jimeng-seedance-motion-language.md`, `02_script_analysis.md`, and `engine_plan.json` first, then divide the script's `shot_plan` and the analyzer's scene environment/music/transition data into full shots automatically. If the selected camera engine is unavailable, use its fallback and tell the user.

For each shot:

- `shot_id` (SH1.1, SH1.2 within scene)
- `duration_sec`
- `shot_type` (extreme wide / wide / medium / close-up / extreme close-up / over-shoulder / POV / insert)
- `camera_move` (static / pan-L / pan-R / tilt-up / tilt-down / push-in / pull-back / handheld / dolly-in / crash-zoom / whip-pan / orbit / dutch-angle)
- `time_segments` (for 10s+ shots: 0-3s / 3-6s / 6-10s / 10-15s)
- `environment_effects` (copy from `02_script_analysis`: wind intensity/direction, grass motion, snow density/fall speed, rain, particles, atmosphere)
- `music_cue` (copy from `02_script_analysis`: BGM mood, tempo, instruments, intensity curve, SFX enter times)
- `image_prompt` (Seedream seven-layer structure: format + subject + composition + lighting + in-image text + style + lock clause; reference slots are addressed by content, e.g. "参考图中的白发剑修作为人物形象")
- `reference_usage` (map `@图片N` / `@视频N` / `@音频N` to `reference_bundle.json` slots; used both by local engines and optional Jimeng prompt packs)
- `motion_text` (Seedance formula: subject + scene + action + camera language + time segments + transition/effect + audio + style; include start pose, action, end pose, physics, mouth state)
- `start_pose` / `end_pose` (for cross-shot continuity)
- `physics_notes` (gravity, inertia, weapon grip, foot sliding, cloth/hair)
- `lip_motion` (`speaking` only when dialogue or narration lands in this shot; otherwise `closed`)
- `character_layout` (multi-person: max 3 main characters + extras; each character references canonical refs)
- `continuity_chain` (previous_last_frame / next_first_frame)
- `dialogue_lines`, `narration_offset`, `narration_text`
- `action_beat` and `impact_frame` (fight shots)
- `transition_in` / `transition_out` (fade-in / cut / dissolve / whip / match-cut; copy from `02_script_analysis`)
- `jimeng_prompt` (optional; only when the user explicitly selected Jimeng online, use strict `@图片N/@视频N/@音频N` syntax)

Long shots over 6 seconds must be split into 2-4 connected segments using first/last frame chaining.

Write `03_storyboard.md` and, when downstream tooling needs it, `03_storyboard.json` with the same fields. Then run `python scripts/export_outputs.py <project_dir> --kind scripts` before pausing.

Pause. Ask: `Approve Step 3 storyboard, or revise?`

## Step 4 — Art direction (`04_art_direction.md`)

One page that locks visual style so all images stay consistent across shots and episodes:

1. Read `references/art-style-presets.md`, `references/character-styles.md`, `references/2026-ai-manga-character-bank.md`, and `references/seedream-prompt-system.md`. Paste the matching preset into the doc.
2. Write the global style statement, color palette, character sheets, scene sheets, background motifs, Do/Don't list, and voice cast placeholder. Image prompts in Step 3/5 must follow the Seedream seven-layer structure defined in `references/seedream-prompt-system.md`.
3. For every recurring character, write `prompt_fragment` and `lock_clause` exactly as they will be used in image prompts. Do not change wording between shots.
4. If the user mentions 2026 爆款 AI 漫剧 or names 李观棋 / 陈默 / 魏逆生 / 蚩衍 / 萧征 / 韩信, first read `references/2026-ai-manga-character-bank.md` and copy the matching prompt fragments into the character sheets. Keep 真实逼真 + 轮廓分明 unless the user explicitly selects 数字真人.
5. If the user asks for 3D 国风动漫 / 国漫仙侠 / 高质量仙侠人物、场景、角色提示词, first read `references/3d-guofeng-xianxia-prompts.md`, paste the selected character or scene template into the prompt, then append the universal quality block and the character-consistency block. Keep 真实逼真 + 轮廓分明 unless the user explicitly selects 数字真人.
6. Write `reference_image` placeholders that will be filled in Step 5, and map each `reference_bundle.json` slot to its content so `reference_usage` stays unambiguous.

After writing `04_art_direction.md`, run `python scripts/export_outputs.py <project_dir> --kind scripts` before pausing.

Pause. Ask: `Approve Step 4 art direction, or revise?`

## Step 5 — Image and motion generation (`05_images/`, `05_video/`)

1. Read `engine_plan.json`, `references/cloud-model-orchestration.md`, `references/seedream-prompt-system.md`, and `references/jimeng-seedance-motion-language.md`. Then run `python scripts/check_deps.py` (or `scripts/check_deps.sh` on Linux/macOS) and `python scripts/engine_plan.py <project_dir> --check` to confirm the configured model/API or image engine is reachable. If `00_meta.json.motion_mode == "video-diffusion"`, also run `python scripts/engine_plan.py <project_dir> --check --require-motion`; when the user explicitly selects local mode, read `references/video-motion-generation.md` and run `python scripts/install_video_engine.py <project_dir> --check`.
2. Generate images only through the approved engine:
   - Preferred order: current configured model/API -> Codex imagegen skill/MCP -> local ComfyUI/SD WebUI API (local only when user selects it).
   - `image_prompt` comes from the approved storyboard and uses the Seedream layered formula; every reference is addressed by content and by `reference_usage`.
   - For every approved keyframe, run `python scripts/generate_images.py --prompt "<image_prompt>" --output 05_images/<shot_id>.png --seed <locked_seed> --width <W> --height <H> --steps <24> --ref-bundle reference_bundle.json`. If a custom multi-reference workflow is needed, also pass `--workflow <video_workflow.json>`. 角色一致性关键帧必须加 `--require-reference`；没有可用的自定义多参考 workflow 时命令会失败并明确提示，禁止把“参考未生效”当成一致性锁定。
   - 本地模式使用 SDXL 生图要真正使用多参考时，先运行 `python scripts/install_image_engine.py --install-ref-nodes` 安装 IPAdapter 节点；没有 IPAdapter 模型或自定义 workflow 时，必须明确提示“参考未生效”，不能假装角色一致性已经锁定。
3. Generate canonical refs first for every recurring character and scene, then generate shot keyframes. Save `05_images/manifest.json` with `{shot_id, file, prompt, seed, model, width, height, status}`.
4. Run the continuity audit and De-AI image audit; any `mismatch` or `fail` blocks the next step.
   - After the image audits pass, run `python scripts/export_outputs.py <project_dir> --kind images` so approved keyframes and refs are available under `<output_root>/images/<slug>/`.
5. **Real motion generation** (only when `motion_mode != still-kenburns`):
   - `motion_text` comes from the approved storyboard and uses the Seedance formula: subject + scene + action + camera + time segments + transition/effect + audio + style.
   - Cloud/API mode: call the configured current model/API for image-to-video, passing `motion_text`, keyframe, refs, and seed; save to `05_video/<shot_id>.mp4`. Local mode: run `python scripts/generate_video.py --prompt "<motion_text>" --image 05_images/<shot_id>.png --output 05_video/<shot_id>.mp4 --seed <locked_seed> --model auto --profile auto --project-dir <project_dir> --ref-bundle reference_bundle.json`.
   - Use `--start-image <previous_last_frame>` and `--end-image <next_first_frame>` for long-shot chaining.
   - Pass `reference_bundle.json` (`--ref-bundle`) so the workflow can mix character/style/composition image refs and motion video refs; cloud APIs receive the same semantic slots through their reference fields. Local mode follows the ComfyUI reference workflow documented in `references/video-motion-generation.md`; if the built-in local workflow template fails, ask the user to export `video_workflow.json` and retry.
   - Maintain `05_video/manifest.json` with `{shot_id, keyframe, clip, seed, model, prompt, frames, fps, duration_ms, status, start_image, end_image, reference_bundle}`.
6. Run `05_video/continuity_audit.md` and `05_video/deai_audit.md`; any mismatch or fail blocks Step 6.
   - If `engine_plan.json` has a user-specified external video override (e.g. Jimeng), also assemble `jimeng_prompt_pack.md` from the approved storyboard `jimeng_prompt` fields and run `python scripts/export_outputs.py <project_dir> --kind scripts`.
   - After the video audits pass, run `python scripts/export_outputs.py <project_dir> --kind videos` so approved motion clips are available under `<output_root>/videos/<slug>/`.

Pause. Ask: `Approve Step 5 images and motion, or revise?`

## Step 6 — Voice acting (配音)

1. Use `references/voice-options.md` to pick a TTS provider. Default order: current model/API TTS, then installed `speech` skill, then OpenAI TTS, then Edge TTS, then Azure, ElevenLabs, local.
2. Lock one narrator voice and one voice per speaking character. Write the choice under "Voice cast" in `04_art_direction.md`.
3. For series, reuse the `voice_id` recorded in `00_series.json` / `character-bible.md`. Do not silently switch a character's voice in a later episode; any voice change must be approved.
4. For every narration line and every dialogue line, produce one audio file: `06_voice/<scene_id>__<line_index>.<ext>`. Write `06_voice/index.json` with `{line_id, speaker, text, file, duration_ms}`.
5. When `reference_bundle.json.audio.voice_timbre` or `emotion_line` exists, prefer a voice-cloning-capable local provider (CosyVoice / GPT-SoVITS / XTTS) and use those audio refs for timbre and emotion; record the cloned voice id in `06_voice/index.json`.
6. Run the De-AI voice check: no robotic monotone, clipped endings, flat emotion, or unnatural breath.

**Lip sync speaking shots** (mandatory when `audio_lip_sync` is available or an audio-driven workflow exists, and `motion_mode != still-kenburns`):

Cloud/API mode: call the current model/API with `audio_url` plus the approved character reference image/video (for example MiniMax-H3) and save the returned talking clip as `06_face/<shot_id>_lip.mp4`.

Local mode (only when the user explicitly selected it):

```powershell
python scripts/lip_sync.py <project_dir> --shot SH1.1 --engine auto --require-audio-sync
```

Write `06_face/<shot_id>_lip.mp4`, `06_face/index.json`, and `06_face/lip_sync_report.md`. Lip timing must align with `06_voice/index.json`; any mismatch is a `fail`. If the current model/API supports audio-driven lip sync (for example MiniMax-H3 via `audio_url` plus a character reference image/video), call it directly and record provider/model in `06_face/index.json`. Otherwise, if the user explicitly selected local mode, run `python scripts/install_video_engine.py <project_dir> --install --models wav2lip` when only LivePortrait is available locally, or install SadTalker / MuseTalk / Hallo / a Wan 2.2 audio-to-video workflow; before local installation, ask the user whether to configure a cloud lip-sync API or accept voice-only.

After the voice check, run `python scripts/export_outputs.py <project_dir> --kind audio`. After lip sync, run `python scripts/export_outputs.py <project_dir> --kind videos`.

Pause. Ask: `Approve Step 6 voice and lip sync, or revise?`

## Step 7 — Subtitles and timeline (`07_subtitles.srt`, `07_timeline.json`)

1. Generate `07_subtitles.srt` from the approved script, using `assets/subtitle_template.srt` and `assets/subtitle_styling.md`.
2. Write `07_timeline.json` describing per-shot `{shot_id, image, clip, voice_lines, subtitle_cue_id, transition_out}`.
3. Run the De-AI subtitle check: no BOM/encoding errors, correct speaker tags, aligned timecodes, complete punctuation, no machine-translation errors, no face occlusion.

Run `python scripts/export_outputs.py <project_dir> --kind scripts` before pausing.

Pause. Ask: `Approve Step 7 subtitles and timeline, or revise?`

## Step 8 — Composition (`08_final.mp4`, `08_final_with_subs.mp4`)

1. Re-read `engine_plan.json`, `05_images/continuity_audit.md`, and `05_images/deai_audit.md`; if any character or scene is `mismatch` or any de-AI item is `fail`, stop and return to Step 5.
2. Confirm dependencies with `python scripts/check_deps.py`. If ffmpeg is missing, stop and tell the user how to install it.
3. Run `python scripts/compose.py <project_dir>`:
   - Use approved real-motion clips when available; only fall back to image + Ken Burns after explicit approval.
   - Layer voice lines, optional BGM, and burn subtitles into `08_final_with_subs.mp4`.
4. Run `ffprobe` to confirm duration and audio stream.
5. Write `08_deai_check.md` using `assets/deai_audit_template.md`.

Run `python scripts/export_outputs.py <project_dir> --kind videos` and `python scripts/export_outputs.py <project_dir> --kind scripts` before pausing.

Pause. Ask: `Approve Step 8 final video, or revise?`

## Step 9 — Post-processing (`09_final_enhanced*.mp4`)

1. Read `references/postprocessing.md` and generate `postprocess_plan.json` (profile: light / balanced / extreme; user overrides win).
2. Run `python scripts/setup_postprocess.py <project_dir> --install-models --model-dir <dir>` to detect/install FFmpeg, VapourSynth, plugins, and models.
3. Run `python scripts/postprocess.py <project_dir>` to stabilize, deinterlace, denoise, sharpen, color grade, upscale, and add film grain as planned.
4. Verify continuity and De-AI again; enhanced output must not change face or lip sync.
5. Write `09_postprocess_report.md` and `09_deai_check.md`.

Run `python scripts/export_outputs.py <project_dir> --kind videos` and `python scripts/export_outputs.py <project_dir> --kind scripts` before pausing.

Pause. Ask: `Approve Step 9 enhanced final, or revise?`

## Bundled resources

- `assets/character_bible_template.md` — cross-episode character lock template (face, wardrobe, seed, prompt fragment).
- `assets/scene_bible_template.md` — recurring scene lock template.
- `assets/series_manifest_template.json` — series continuity manifest schema.
- `assets/engine_plan_template.json` — engine orchestration plan schema.
- `assets/resource_manifest_template.json` — resource ingestion manifest schema.
- `assets/reference_bundle_template.json` — 9-image / 3-video / 3-audio mixed reference bundle schema.
- `assets/storyboard_template.md` — brief, script, storyboard, art direction templates.
- `assets/subtitle_template.srt` — SRT example with style notes.
- `assets/subtitle_styling.md` — subtitle styling and De-AI subtitle rules.
- `assets/state_template.md` — STATE.md skeleton.
- `assets/continuity_audit_template.md` — per-episode character/scene consistency audit.
- `assets/deai_audit_template.md` — De-AI audit for images, motion, voice, subtitles, and final cut.
- `assets/postprocess_plan_template.json` — FFmpeg/VapourSynth post-process plan schema.
- `references/2026-ai-manga-character-bank.md` — 2026 爆款 AI 漫剧男主素材库与历史国风韩信风格，含逐字 Prompt fragment.
- `references/3d-guofeng-xianxia-prompts.md` — 知乎 3D 国风动漫/国漫仙侠人物、场景、角色提示词大全，含通用画质词、一致性词与万能公式.
- `references/art-style-presets.md` — full scene-style presets (赛博朋克, 古风水墨, 治愈手绘, 日漫热血, 美漫黑白, plus 2026 爆款男主、历史国风与 3D 国风仙侠预设).
- `references/character-styles.md` — character style presets (写实动漫, 数字真人, 经典动漫, 半写实, 2026 爆款男主, 3D 国风动漫).
- `references/digital-human-options.md` — digital-human provider guide (current model/API, D-ID, HeyGen, SadTalker, LivePortrait, local).
- `references/voice-options.md` — TTS provider and voice-cast guide.
- `references/video-motion-generation.md` — local-only real-motion pipeline, used when the user explicitly selects local mode: Wan / HunyuanVideo / LTX-Video, ComfyUI workflows, motion prompts, fight continuity, lip sync, and downgrade rules.
- `references/seedream-prompt-system.md` — Seedream 5.0 Pro 图像提示词分层结构、参考图锁定、多图融合，整合为本机 `image_prompt` 规范.
- `references/jimeng-seedance-motion-language.md` — 即梦 Seedance 2.0 多模态 `@图片/@视频/@音频` 提示词、运镜、分时段、音频设计，整合为本机 `motion_text` 规范.
- `references/composition-and-multi-reference.md` — 9 图 + 3 视频 + 3 音频混合参考、多人构图、长镜头一致性.
- `references/shot-camera-and-fight-language.md` — camera moves and fight language.
- `references/series-continuity.md` — cross-episode consistency rules.
- `references/resource-ingestion.md` — URL/video/audio/image/text ingestion and blocked-resource rules.
- `references/engine-orchestration.md` — engine detection, fallback, and `engine_plan.json` rules.
- `references/cloud-model-orchestration.md` — pluggable current cloud model/API orchestration (Minimax/Hailuo, Seedance, Doubao, etc.) and switching rules.
- `references/deai-artifact-removal.md` — De-AI audit for every artifact.
- `references/postprocessing.md` — FFmpeg / VapourSynth post-processing guide.
- `references/auto-install.md` — automatic dependency install guide.
- `scripts/install_ffmpeg_vapoursynth.py` — detect or install FFmpeg / VapourSynth.
- `scripts/setup_postprocess.py` — install post-process models and plugins.
- `scripts/postprocess.py` — run the post-process plan.
- `scripts/install_image_engine.py` — detect or auto-install a local realistic image engine (ComfyUI + RealVisXL) when Codex imagegen is unavailable.
- `scripts/generate_images.py` — generate images with the installed local engine (diffusers/ComfyUI/SD WebUI).
- `scripts/install_video_engine.py` — detect/install ComfyUI video-diffusion custom nodes and Wan/HunyuanVideo/LTX models, plus talking-head tools; `--auto` installs missing software/models for the current hardware.
- `scripts/generate_video.py` — generate real-motion shot clips from keyframes via the local ComfyUI video engine.
- `scripts/hardware_profile.py` — detect VRAM/RAM and recommend the optimal Wan/LTX resolution, frame count, step count, and block-swap profile.
- `scripts/lip_sync.py` — drive talking-head lip sync for speaking shots.
- `scripts/process_reference_bundle.py` — ingest, normalize, and register the 9/3/3 mixed reference bundle.
- `scripts/extract_frames.py` — extract first/last frames for long-shot chaining.
- `scripts/compose.py` — render `08_final.mp4` and `08_final_with_subs.mp4`.
- `scripts/analyze_script.py` — 自动生成剧本深度分析：人物性格/行为/外貌、场景音乐、风吹/草动/飘雪/雨/粒子、转场、分镜提示.
- `scripts/export_outputs.py` — 把剧本、图片、视频、音频按用户指定目录分别落盘.
- `scripts/validate_outputs.py` — sanity-check the artifacts directory before final delivery.
- `scripts/approval_gate.py` — scripted 10-step approval gate backed by `STATE.md`; `check` / `approve` / `revise`.
- `scripts/check_deps.py` — cross-platform dependency check.
- `examples/neon-cat-alley/` — tiny reference project showing Step 0-2 artifacts (bibles, style lock, resource manifest, engine plan, brief, script, character analysis, STATE stub).
- `examples/2026-ai-manga-styles/README.md` — sample style usage for the 2026 AI 漫剧 male-lead family.

Read these only when the corresponding step starts.

## Failure recovery

- Image generation unusable twice in a row on the same shot: stop Step 5, ask user (switch style / accept prompt-only / skip the shot).
- All TTS providers fail: ask user to paste a local recording or accept silent scenes.
- ffmpeg missing: stop Step 8, list install instructions (apt / brew / winget).
- imagegen skill missing: fall back to prompt-only mode and tell the user up front.
- Character or scene continuity mismatch in a series: stop immediately, return to Step 5, regenerate only the mismatched shots using the canonical refs and locked seeds. Do not proceed to Step 8.
- De-AI audit `fail`: stop at the failing stage, regenerate or repair that artifact, then rerun the audit. Do not deliver a video with unresolved AI artifacts.
- Resource `blocked`: stop that resource use, record it in `resource_manifest.json`, and ask the user for a readable copy or screenshot before continuing.
- Engine unavailable: stop the affected step, use the fallback from `engine_plan.json`, and tell the user which engine was replaced.
- Local video workflow template failed: stop Step 5, ask the user to export the local `video_workflow.json` or switch to the configured cloud model/API; do not fake a motion clip.
- Audio-driven lip-sync engine missing: stop Step 6 lip sync, ask the user to configure a cloud lip-sync API, install SadTalker / MuseTalk / Wav2Lip / Hallo / a Wan 2.2 audio-to-video workflow, or accept voice-only; the downgrade must be recorded in `STATE.md.notes`.
- Reference bundle blocked: stop Step 0, keep the blocked slots `null` in `reference_bundle.json`, and ask the user for a readable copy; never generate a character from a missing reference without explicit approval.
- Long-shot frame chain mismatch: stop Step 5, regenerate only the mismatched segment using the previous `last_frame` as `start_image`; never cut around the discontinuity.
- Output root write fails: stop the step, report the path or permission error, fix `output_root`, and rerun `scripts/export_outputs.py` before pausing; never tell the user the files were saved when they were not.
- User says `stop` at any time: write `STATE.md` with the last completed step and the next pending one, then end the turn.
