# 当前模型/API 优先编排（Cloud Model Orchestration）

本文件用于 Step 0/1/5/6。默认使用用户当前配置的模型/API；本地 ComfyUI + Wan / HunyuanVideo / LTX-Video 只有在用户明确选择本地模式时才使用，不是默认。

## 当前模型配置

项目根目录（系列为系列根目录）使用 `model_config.json`：

```json
{
  "version": 1,
  "current": {
    "provider": "minimax-hailuo",
    "model": "MiniMax-H3",
    "roles": ["image", "video", "tts", "bgm", "lip_sync"],
    "selected_at": "2026-08-05T12:00:00",
    "note": "当前购买云模型，下月可切换"
  },
  "history": []
}
```

`roles` 只是能力声明，开始生产前仍要按真实 API 能力验证，不能只看配置。

## 优先级

1. 当前模型/API：支持哪项媒体就使用它完成哪项，包括文生图、图生视频、配音、BGM、音效和音频驱动嘴型。
2. 补充云 API：当前模型缺少某项能力时，从其他云 API 或在线平台补齐，并写入 `engine_plan.json`。
3. 本地引擎：只有用户明确说“本地”或明确选择 ComfyUI/Wan 时才检测、安装和使用。
4. 降级：`still-kenburns`、有声无口型等只能作为用户明确同意的降级。

切换模型只改 `model_config.json`，然后重新运行 `engine_plan.py`，不重写工作流。

## MiniMax / Hailuo

官方视频生成 V2 接口：`https://api.minimax.io/v2/video_generation`（可能因区域使用对应域名）。

- 多模态 `content[]` 支持 `text`、`image_url`、`video_url`、`audio_url`。
- 支持文生视频、图生视频、首尾帧图生视频、多模态参考生视频。
- 输出 768P / 2K，片段 4-15 秒，可带原生立体声。
- 音频输入必须是 WAV/MP3，单段 2-15 秒，不超过 15MB，必须配合图片或视频输入，不能单独传音频。
- MiniMax-H3 支持音频驱动人物嘴型：传人物参考图/视频 + 对话音频，一次调用即可生成嘴型与对话音频对应的说话镜头。
- 不需要像部分 Seedance 流程那样把台词塞进 prompt 或生成黑屏视频来驱动嘴型。
- 如果成片必须保留前期 TTS/录音的精确音频，先验证 H3 返回视频是否保留该音频；不能保留时，以 H3 原生生成音频为成片配音，或用云口型 API/本地工具做精确音频对齐。
- 动作场面可能比 Seedance 2.0 更容易出现动态模糊；长镜头要拆成 4-15 秒片段，用首尾帧链衔接。

## Doubao / Seedream

- Seedream 5.0 Pro 面向高精度图片生成：文生图、图生图、多图融合、坐标编辑。
- 图片生成优先走 `scripts/generate_images.py` 或 `scripts/process_image_assets.py`，参考图按 `reference_bundle.json` 槽位传递。
- 视频能力看当前配置的具体模型，不要默认 Doubao 一定支持全部视频功能。

## Jimeng / Seedance

- Seedance 2.0 支持多模态 `@图片/@视频/@音频` 提示词、运镜和分时段。
- 用户明确选择即梦在线工具时，生成 `jimeng_prompt_pack.md` 并写入 `user_overrides`。
- 没有明确选择时，不要求用户去网页手工回流素材。

## 口型同步规则

1. 当前模型/API 支持音频驱动嘴型时（例如 MiniMax-H3 `audio_url`），直接由它生成说话镜头。
2. 不支持时，先试云口型 API（HeyGen / D-ID 等），再考虑本地工具。
3. 本地工具只在用户明确选择本地模式时使用。
4. LivePortrait 只做表情迁移，不是音频驱动口型；不能把它的输出当作音画同步结果直接通过。
5. 任何口型结果都要与 `06_voice/index.json` 的时间码做偏差检查，偏差超过 100ms 判失败。
