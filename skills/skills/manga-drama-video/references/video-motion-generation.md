# 本地真动态视频生成（Video Motion Generation）

本文件用于 Step 3/5/6/8。目标是让分镜从“静态帧 + Ken Burns”升级为真正的动态镜头：人物会打、镜头会动、能说话，并且全部在本机完成，不依赖即梦等外部平台。

本文件只在用户明确选择本地模式时生效。默认模式使用当前模型/API，规则见 `references/cloud-model-orchestration.md`。

## 运动模式

| 模式 | 说明 | 产物 |
| --- | --- | --- |
| `video-diffusion`（本地模式首选） | 用本地视频扩散模型生成动态镜头 | `05_video/<shot_id>.mp4` |
| `talking-head` | 用音频驱动口型和面部动画 | `06_face/<shot_id>_lip.mp4` |
| `still-kenburns`（降级） | 静态帧 + ffmpeg 运镜 | `08_final.mp4` 内实时合成 |

`00_meta.json` 增加 `motion_mode` 字段：`video-diffusion | talking-head-only | still-kenburns`。用户没有指定时默认 `video-diffusion`，由当前模型/API 生成；只有用户明确选择本地模式时才按本文件确认本地视频引擎可用。不可用时要暂停询问，禁止静默降级。

## 本地视频扩散引擎

推荐走 ComfyUI API，图像引擎和视频引擎共用同一个 `http://127.0.0.1:8188` 实例。模型按优先级选择：

1. **Wan 2.1 / 2.2**：仙侠、人物、镜头运动表现均衡，I2V 质量高，中文场景和武打表现最好。
2. **HunyuanVideo**：长镜头和复杂运镜好，显存和生成时间成本高。
3. **LTX-Video**：速度快、显存低，适合短镜头和快速迭代。

需要的 ComfyUI 自定义节点：

- `ComfyUI-WanVideoWrapper`
- `ComfyUI-HunyuanVideoWrapper`
- `ComfyUI-VideoHelperSuite`
- `ComfyUI-VideoCombine` 或同类输出节点

缺少节点时运行：

```powershell
python scripts/install_video_engine.py <project_dir> --check
python scripts/install_video_engine.py <project_dir> --auto
```

`--auto` 会按当前硬件自动安装 ComfyUI、Wan、LTX-Video、LivePortrait 并启动引擎。只想补 LTX 快速迭代通道时运行：

```powershell
python scripts/install_video_engine.py <project_dir> --install --models ltx
```

LTX 模型文件放在 `models/checkpoints/`，T5 文本编码器放在 `models/text_encoders/`；8GB 显存优先使用 fp8 T5。模型扫描结果写入 `video_engine_report.json` 和 `engine_plan.json` 的 `engines.video_gen.params.model_dir`。

## 硬件自适应

运行 `python scripts/hardware_profile.py` 可查看当前显卡显存、系统内存和推荐参数。`generate_video.py` 默认使用 `--profile auto`：

- `wan-low`（显存 < 7.5GB）：384x384、9 帧、8 步，优先 LTX-Video（已安装时），否则 Wan 最低配置。
- `wan-8gb`（显存 8-11GB，例如 RTX 4060）：480x832、25 帧、12 步，`block_swap=20`，文本编码走 CPU。
- `wan-12gb`（显存 12-15GB）：480x832、33 帧、16 步，`block_swap=12`。
- `wan-high`（显存 >= 16GB）：832x480、49 帧、20 步，`block_swap=6`，文本编码走 GPU。

系统内存 >= 32GB 时允许更高的 block-swap，内存 < 16GB 时自动降低帧数和步数。用户显式传入 `--width`、`--height`、`--frames`、`--steps` 时，以用户参数为准。

8GB 显存机器做快速分镜验证时，可显式切换 LTX 并把参数降到冒烟档：

```powershell
python scripts/generate_video.py --prompt "<motion_text>" --image 05_images/SH1.1.png --output 05_video/SH1.1.mp4 --seed 101 --model ltx --profile wan-low
```

## 生成规则

### 1. 先生成关键帧

每个镜头先按 Step 5 生成 `05_images/<shot_id>.png`，作为 I2V 的首帧。关键帧必须通过 continuity audit 和 De-AI image audit，不能带着错误脸和错误场景去做视频。

### 2. 再生成动态镜头

```powershell
python scripts/generate_video.py `
  --prompt "<motion prompt>" `
  --image 05_images/SH1.1.png `
  --output 05_video/SH1.1.mp4 `
  --seed 101 `
  --fps 24 `
  --model auto --profile auto
```

Wan 2.1 480P 模型的竖屏上限建议 `480x832`（9:16）或 `832x480`（16:9），不要在 480P 模型上直接生成 1080x1920。长镜头接续时追加 `--start-image <上段最后一帧> --end-image <下段第一帧>`，由 ComfyUI 的首尾帧编码节点锁定衔接。下载失败时安装脚本会自动尝试 hf-mirror 与 ModelScope 两个源。

参数写入 `05_video/manifest.json`：`{shot_id, keyframe, clip, seed, model, prompt, frames, fps, duration_ms, status}`。

### 3. 运动提示词结构

每个镜头的 `motion_text` 必须是完整的一句话，包含：

- 主体动作：谁在做什么，从什么姿势到什么姿势。
- 物理约束：重力、惯性、武器朝向、脚步不滑。
- 镜头语言：机位如何移动，景别是否变化。
- 时间跨度：动作在多少秒内完成。
- 口型约束：非说话镜头嘴巴闭合，说话镜头配合台词。

即梦 Seedance 2.0 的多模态提示词体系已整合进本文件：`motion_text` 按 `[主体] + [场景] + [动作] + [运镜] + [分时段] + [转场特效] + [音频] + [风格氛围]` 书写，参考包用 `reference_usage` 把 `@图片N/@视频N/@音频N` 映射到 9 图 + 3 视频 + 3 音频槽位。完整规则见 `references/jimeng-seedance-motion-language.md`；只有用户明确选择即梦在线工具时才生成 `jimeng_prompt_pack.md`，默认始终走当前模型/API，只有用户明确选择本地模式时才走本机引擎。

示例：

> The swordsman steps forward in a low lunge, dragging the blade in a rising diagonal cut from lower left to upper right, weight shifts from back foot to front foot, blade edge stays inside the hand, cape and hair follow the motion with gravity, camera pushes in from medium to close-up over 3 seconds, mouth stays closed, no foot sliding, no floating.

### 4. 打斗连续性

- 同一场打斗的关键帧必须复用同一组 canonical refs、seed、角色朝向、武器状态。
- 每个 `action_beat` 都写成“预备 -> 发力 -> 击中 -> 反应 -> 收势”中的具体动作名。
- `impact_frame: true` 的镜头让视频模型在中间帧完成碰撞，前后帧不能出现瞬移。
- 相邻镜头首尾帧要能接上：位置、朝向、受伤状态、光照方向。

### 5. 镜头运动

`camera_move` 直接写进 `motion_text`，让视频扩散模型原生生成运镜：

- `push-in`：camera dollies toward the subject over the shot.
- `whip-pan`：fast whip pan at the beat, motion blur on the mid-frame.
- `orbit`：camera orbits 20-30 degrees around the subject.
- `dutch-angle`：camera gradually tilts to a 10-degree dutch angle.

不要只依赖 ffmpeg zoompan 做运镜；`video-diffusion` 模式下 Ken Burns 只在镜头需要二次强调时才叠加。

## 口型驱动

Step 6 配音完成后，说话镜头必须走口型驱动。当前模型/API 支持音频驱动时（例如 MiniMax-H3 `audio_url` + 人物参考图/视频），优先由它生成；本地模式使用以下命令和工具：

```powershell
python scripts/lip_sync.py <project_dir> --shot SH1.1 --engine auto --require-audio-sync
```

本地模式工具优先级：

1. 真正音频驱动：Wan 2.2 audio-to-video / SadTalker / MuseTalk / Wav2Lip / Hallo。
2. ComfyUI 自定义音频口型工作流（必须输入音频并输出嘴型）。
3. LivePortrait：只做表情和头部运动迁移，适合非台词面部表演，不能把“合入音频”当作口型同步。

产物：

```
06_face/<shot_id>_lip.mp4
06_face/index.json
06_face/lip_sync_report.md
```

规则：

- 只对 `dialogue_lines` 非空或 `narration` 落在该镜头的说话镜头做口型。
- 口型时间必须与 `06_voice/index.json` 的 `duration_ms` 对齐。
- 口型完成后重跑 De-AI 口型检查；音画不同步判 `fail`。
- 没有当前模型/API、云口型 API 或本地音频驱动工作流时，停止 Step 6 并询问是否配置云口型 API、安装本地工具（仅用户选择本地模式时）或接受有声无口型；禁止把 LivePortrait 的 `_lip.mp4` 当作音画同步产物直接通过。
- 本地模式下，数字真人镜头优先用 SadTalker / MuseTalk / Wav2Lip / Hallo，写实动漫镜头优先用 Wan 2.2 audio-to-video 或等价音频口型工作流。

## 降级与用户确认

- 视频引擎不可达：停止 Step 5，展示 `engine_plan.json` 检测结果，问用户是否安装模型、改用 `still-kenburns`，或只做关键帧。
- 口型引擎不可达：停止 Step 6 口型步骤，问用户是否配置云口型 API、安装本地工具（仅用户选择本地模式时）、接受“有声无口型”，或只对关键特写做口型。
- 显存不足：降低 `--frames` 到 25-33、分辨率降到 640x960，或换 LTX-Video。
- 任何降级都必须写进 `STATE.md.notes` 和 `04_art_direction.md` 技术说明，不能无声切换。

## De-AI 运动检查

视频镜头在 Step 5/6/8 必须逐项检查：

- 帧间不闪烁、不跳变、不溶解变形。
- 人物不瞬移、不穿模、不滑步，手脚有重力感。
- 武器始终握在正确位置，不出框、不穿手。
- 镜头运动连续，不出现机械匀速或反向抖动。
- 说话镜头口型与音频对齐，非说话镜头嘴巴闭合。
- 人物脸型、服装、场景和关键帧一致，不能“动起来就换脸”。
- 失败镜头最多重试 2 次，仍失败则暂停询问。
