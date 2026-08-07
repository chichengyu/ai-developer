# 素材生成与视频合成

用于 Phase 2 和 Phase 3。所有产物必须写入 `assets/manifest.json` 或 `audio/manifest.json`。

## 能力边界与引擎模式

- 当前模型/API 支持媒体生成时，直接使用它完成图片、视频、配音、BGM 和嘴型同步。
- 当前模型/API 可以是用户购买的云模型，例如 Minimax/Hailuo、即梦/Seedance、豆包/Seedream，也可以是后续切换的其他模型；技能只记录当前选择，不写死。
- 云模式：当前模型/API + 可选补充服务，质量上限最高，适合追求即梦式电影效果。
- 混合模式：当前模型做策划和提示词，图片/视频/音频交给当前云模型或其他 API，后期用 ffmpeg 合成。
- 用户说“当前模型是 Minimax”或“我下月会换模型”时，只更新 `model_config.json` / `manifest.json` / `engine_overrides` 的模型名称、API 地址和密钥，不重写工作流。
- 用户明确选择“即梦”时，把 `engine_overrides` 写成 `jimeng/seedance`，生成 `05_jimeng_prompt_pack.md` 并在即梦平台执行。

## 图片生成优先级

1. 当前模型/API：如果用户配置的云模型支持文生图和图生视频，优先由它生成图片和视频。
2. Doubao Seedream API：当环境变量 `ARK_API_KEY` 存在时运行 `scripts/seedream_generate.py`，适合参考图融合、坐标编辑和原生文字控制。
3. Codex `imagegen` 技能：适合当前模型/API 不提供图片能力时生成原创角色、场景和风格参考。

常用命令：

```bash
python scripts/seedream_generate.py \
  --prompt "<七层 image_prompt>" \
  --image "assets/characters/lin_mu_front.png" \
  --image "assets/scenes/shanmen_wide.png" \
  --size 2K \
  --output "assets/scenes/shot_01.png"
```

精确编辑示例：

```bash
python scripts/seedream_generate.py \
  --prompt "把图1 <bbox>120 180 640 760</bbox> 区域内的左侧人物换成机器人，其余保持参考图不变" \
  --image "assets/scenes/shot_01.png" \
  --output "assets/scenes/shot_01_edit.png"
```

## 人物与场景参考

生成顺序：

1. 每个人物先出正脸 canonical ref，再出 3/4 侧面、表情、动作。
2. 每个场景先出 wide，再出 detail 和 style。
3. 所有参考图写入 `assets/manifest.json`，记录 `{character_id, file, prompt, seed, engine}`。
4. 后续镜头图片必须引用这些 refs，不能从文字重新发明角色。

## 配音生成优先级

1. 当前模型/API TTS，记录 provider/model 到 `audio/manifest.json`。
2. 已安装的 `speech` 或 TTS 技能。
3. Edge TTS / OpenAI TTS / Azure TTS。
4. 用户提供的真人录音，用于音色克隆。

每句台词生成 `audio/voice/<line_id>.mp3`，`line_id` 使用 `S1_01`、`N_01` 这类稳定编号。`audio/manifest.json` 记录：

```json
{
  "line_id": "S1_01",
  "speaker": "林暮",
  "text": "把剑放下。",
  "file": "audio/voice/S1_01.mp3",
  "start_at_s": 0.0,
  "emotion": "克制",
  "voice_id": "lin-mu-voice"
}
```

## 嘴型同步优先级

1. 当前模型/API 原生音频驱动：例如 MiniMax-H3 传 `audio_url` + 人物参考图/视频；音频用 WAV/MP3，单段 2-15 秒且不超过 15MB，必须配合图片或视频输入。
2. 云口型 API：HeyGen / D-ID 等，当前模型不支持时使用。

同一说话镜头只绑定对应 `line_id`，嘴型与音频偏差超过 100ms 判失败；非说话镜头嘴巴闭合。

如果必须保留前期 TTS/录音的精确音频，先验证当前模型/API 返回视频是否保留该音频；不能保留时，以模型原生生成音频为成片配音，或用云口型 API 做精确音频对齐。

## BGM 与音效

优先级：

1. 用户提供的音乐或版权清晰的配乐文件。
2. 可用音乐生成 API（云端音频模型或即梦音频）。
3. 无音乐模型时，用 ffmpeg 合成明确标注的“临时氛围垫”，例如低频 drone、雨声、心跳节拍，禁止伪装成正式配乐。

每场 BGM 写入 `audio/bgm/<scene_id>.mp3`。音效写入 `audio/sfx/<scene_id>_<beat>.mp3`，并在 `audio/manifest.json` 记录 `enter_at_s`。

## 运镜素材

每个镜头写 `assets/motion/<shot_id>_camera.json`：

```json
{
  "shot_id": "SH1.1",
  "camera_move": "push-in",
  "start": "medium shot, subject left-third, eye-level",
  "end": "close-up, subject center, low-angle",
  "duration_sec": 4,
  "easing": "ease-in-out",
  "focus": "rack focus from background to face",
  "reason": "从环境关系压向人物情绪"
}
```

打斗镜头额外写 `assets/motion/<shot_id>_fight.json`：

```json
{
  "shot_id": "SH3.2",
  "phases": {
    "prepare": "0-1s 重心下沉，握剑，呼吸停顿",
    "strike": "1-2.5s 蹬地发力，斜斩",
    "impact": "2.5-3s 命中兵器，冲击气浪",
    "reaction": "3-4s 对方后退，脚滑半步",
    "recover": "4-5s 收势，衣发余动"
  },
  "impact_frame": 2.8,
  "camera_effect": "碰撞瞬间轻微后坐"
}
```

## 视频合成

当前模型/API 有图生视频能力时，优先生成真实运动镜头；没有时再使用其他云 API 或即梦/Seedance。云端 API 都不可用时，用 `scripts/compose_video.py --cinematic` 做静态图 + 缓动运镜的降级方案：

```bash
python scripts/compose_video.py \
  <output_dir> \
  --output "video/final/<project-slug>_final.mp4" \
  --cinematic \
  --subs "scripts/06_subtitles_bilingual.srt"
```

`--cinematic` 使用缓动缩放，比直线 Ken Burns 更接近电影镜头；`--subs` 烧录中英双语字幕；脚本读取 `assets/manifest.json` 的 `shots` 和 `audio/manifest.json` 的 `voice`、`bgm`、`sfx`。

如果只生成无音频预览：

```bash
python scripts/compose_video.py <output_dir> --no-audio
```

## 字幕规范

- UTF-8 无 BOM。
- 中英双语字幕：中文在上，英文在下。
- 中文每行不超过 18 个汉字，英文每行不超过 36 个字符，一个 cue 最多 4 行。
- 旁白用 `[旁白]`，角色用 `[角色名]`。
- 字幕时间轴与 `audio/manifest.json` 的 `start_at_s` 对齐，偏差不超过 200ms。
- 生成命令：

```bash
python scripts/generate_subtitles.py <output_dir> --output scripts/06_subtitles_bilingual.srt
```

## 验收

- `ffprobe` 确认时长接近目标时长，音视频流存在。
- 每个 shot 的图片、语音、BGM 都在 manifest 中有来源。
- 人物脸型、服装、场景结构在最终视频中没有漂移。
- 说话镜头嘴型与 `audio/voice/` 的时间轴对齐，非说话镜头嘴巴闭合。
- 运镜有起点、终点、缓动和理由；打斗镜头包含预备、发力、接触、反应、收势。
