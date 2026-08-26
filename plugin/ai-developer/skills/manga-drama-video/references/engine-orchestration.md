# 引擎自动编排（Engine Orchestration）

本文件用于 Step 0/1 及每个生产步骤开始前。默认使用当前模型/API，本地引擎不是默认；用户指定引擎时，用户选择优先并被锁定在 `engine_plan.json` 中，禁止静默替换。

## 默认引擎映射

| 产物 | 默认自动引擎 | 可选引擎 / 回退 |
| --- | --- | --- |
| 图片 | 当前模型/API -> Codex imagegen -> 本地（仅用户选择） | 当前模型缺图片能力时回退其他云 API；本地仅显式选择 |
| 动态视频 | 当前模型/API（Minimax/Hailuo、Seedance、Doubao 等）-> 其他云 API -> 本地（仅用户选择） | 不可用时暂停询问，允许显式降级 `still-kenburns` |
| 视频合成 | ffmpeg + ffprobe | 无 ffmpeg 时停止 Step 8 并提示安装 |
| 配音 | 当前模型/API TTS -> speech skill -> OpenAI TTS -> Edge TTS -> 本地 | 按 `references/voice-options.md` 回退 |
| 数字真人 | 当前模型/API 音频驱动嘴型 -> 云口型 API -> 本地（仅用户选择） | 静止肖像 + Ken Burns 只能显式降级 |
| 音频口型 | 当前模型/API 原生音频驱动（如 MiniMax-H3 `audio_url`）-> 云口型 API -> 本地（仅用户选择） | LivePortrait 只算表情迁移，不能当作音频口型 |
| 运镜 | `scripts/compose.py` ffmpeg filters | 无滤镜支持时回退 static |
| 字幕 | `scripts/compose.py` subtitles filter | 无 CJK 字体时提示指定字体 |
| 资源读取 | browser / open_page / curl / ffmpeg / ASR / OCR | 按 `references/resource-ingestion.md` 处理 |

## `engine_plan.json` schema

```json
{
  "engine_plan_version": 1,
  "auto": true,
  "engines": {
    "image": {"name": "imagegen", "status": "available | unavailable | user_specified", "params": {}},
    "video_gen": {"name": "current-model-api", "status": "available | configured | unavailable | user_specified", "params": {}},
    "video": {"name": "ffmpeg", "status": "available", "params": {}},
    "audio_tts": {"name": "speech", "status": "available", "params": {}},
    "digital_human": {"name": "current-model-audio-to-video", "status": "configured | available | unavailable | user_specified", "params": {}},
    "camera_motion": {"name": "ffmpeg-ken-burns", "status": "available", "params": {}},
    "subtitles": {"name": "ffmpeg-subtitles", "status": "available", "params": {}},
    "resource_reader": {"name": "codex-tools", "status": "available", "params": {}}
  },
  "fallbacks": {},
  "user_overrides": {},
  "notes": []
}
```

`model_config.json` 中的当前模型会自动写入 `cloud_model`；`engine_plan.py` 会把已配置的云视频/口型能力标为 `configured`，生产前必须验证 API key 和端点可达。切换模型只改配置并重跑脚本。

## 自动编排规则

1. 所有字段默认自动生成，用户可对任意字段指定值。
2. 用户指定引擎后，在 `user_overrides` 中记录，例如 `{"audio_tts": {"name": "ElevenLabs"}}`，后续步骤必须遵守。
3. 自动引擎不可用时，先使用 fallback；fallback 不可用时停止对应步骤并告诉用户。
4. 每个生产步骤开始前运行 `python scripts/engine_plan.py <project_or_series_dir>` 生成或刷新 `engine_plan.json`。
5. 使用真动态视频时，Step 0/5 还要运行 `python scripts/engine_plan.py <project_or_series_dir> --check --require-motion`，确认 `motion_mode: video-diffusion` 所需的视频引擎可用；不可用时暂停询问，禁止静默降级。
6. 禁止在未更新 `engine_plan.json` 的情况下跨步骤切换引擎。
7. 数字真人、配音、运镜、字幕等引擎选择要写进 `04_art_direction.md` 的 Voice cast / 技术说明，便于用户审核。
8. 用户明确选择即梦/Seedance 在线工具时，把 `video_gen` 写入 `user_overrides`，只额外生成 `jimeng_prompt_pack.md` 提示词包；图片和默认视频仍走当前模型/API，只有用户明确选择本地模式时才走本机引擎，禁止把外部生成图片手工回流到项目。

## 何时必须暂停

- 用户指定引擎不存在或不可达：暂停，给出可用替代，让用户选择。
- 自动选择引擎时发现多个可用项：按默认优先级选择，并在 notes 中说明；如用户有偏好，尊重用户。
- 任何引擎结果出现明显 AI 味或质量问题：回到对应生产步骤重做，不靠换引擎跳过 De-AI Audit。
