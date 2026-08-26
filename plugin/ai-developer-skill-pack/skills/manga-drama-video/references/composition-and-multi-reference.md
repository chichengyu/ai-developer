# 多人构图与混合参考（9 图 + 3 视频 + 3 音频）

本文件用于 Step 0/3/5/6。目标是让复杂多人场景、动态镜头和长镜头一致性比即梦更可控：每个角色、每个场景、每种动作和每个声音都有独立参考，生成时按参考包混合驱动。

## 参考包结构

每个项目或系列在 Step 0 建立 `reference_bundle.json`，固定 9 图、3 视频、3 音频：

| 类别 | 槽位 | 用途 |
| --- | --- | --- |
| 图片 | `character_front` | 正面脸型与服装 |
| 图片 | `character_three_quarter` | 3/4 侧脸，表情与头型 |
| 图片 | `character_side` | 侧面轮廓 |
| 图片 | `character_expression` | 情绪与嘴型范围 |
| 图片 | `character_action` | 招牌动作、武器、打斗姿势 |
| 图片 | `scene_wide` | 场景全局结构与构图 |
| 图片 | `scene_detail` | 材质、道具、光影细节 |
| 图片 | `style_reference` | 画风、线条、调色 |
| 图片 | `composition_reference` | 多人站位、景别、机位模板 |
| 视频 | `motion_primary` | 角色基本运动节奏与惯性 |
| 视频 | `action_beat` | 招式的完整“预备-发力-击中-反应-收势” |
| 视频 | `camera_move` | 运镜节奏、推拉摇移、甩镜 |
| 音频 | `voice_timbre` | 音色与口音，用于 TTS 克隆 |
| 音频 | `emotion_line` | 情绪化的参考台词 |
| 音频 | `ambience_sfx` | 环境音、风声、剑鸣、BGM 质感 |

用户没有提供素材时，Codex 在 Step 0 自动生成前 6 个图片槽位（角色和场景 canonical refs），风格和构图槽位从 `04_art_direction.md` 渲染，视频槽位在 Step 5 从已批准的动作片段回填，音频槽位在 Step 6 从已批准配音回填。

## 处理入口

用户把素材放进 `resources/` 后运行：

```powershell
python scripts/process_reference_bundle.py <project_dir>
python scripts/extract_frames.py refs/motion_primary.mp4 --output refs/frames --first --last --every 0.5
```

脚本会：

- 按文件名关键词匹配 9/3/3 槽位。
- 统一图片为 PNG、视频为 MP4、音频为 MP3。
- 写 `reference_bundle.json` 和 `reference_bundle_report.md`。
- 用 ffprobe 记录视频/音频时长，供后续对齐。

## 多人场景

每个多人镜头在 storyboard 中必须写 `character_layout`：

```json
{
  "shot_id": "SH3.2",
  "character_layout": [
    {"character_id": "jian-wu", "position": "left-front", "pose": "低姿持剑", "refs": ["refs/jian-wu_front.png"]},
    {"character_id": "mo-jiao", "position": "right-back", "pose": "悬空掌法", "refs": ["refs/mo-jiao_action.png"]}
  ]
}
```

规则：

- 一个镜头最多 3 个主要人物 + 群演；超过 3 个主角时拆成 wide + 分组镜头。
- 每个人物必须引用自己的 canonical refs，禁止用“同风格路人”代替。
- `image_prompt` 按 `character_layout` 顺序逐人写：人物、位置、朝向、动作、服装状态。
- 构图参考优先于自由构图；人物之间的视线、遮挡、武器关系必须写清。
- 多人镜头用 IPAdapter/ControlNet 多参考时，每个参考图绑定一个角色；参考不足时暂停，不硬拼。

## 长镜头一致性

长镜头不能一次生成到底。拆分规则：

1. 超过 6 秒的镜头按动作节拍拆成 2-4 个连续片段，片段间用“首尾帧锁链”连接。
2. 每个片段保存 `first_frame` 和 `last_frame`；下一个片段必须以 `last_frame` 作为 `start_image`。
3. `generate_video.py` 支持 `--start-image` / `--end-image`，ComfyUI 工作流用 `{start_image}` / `{end_image}` 占位。
4. 片段之间的 seed 使用同一角色 seed + 递增片段序号，避免角色漂移。
5. 合成时检查相邻片段的最后一帧和第一帧：人物位置、朝向、受伤状态、光照不能跳变。
6. 长镜头的运镜参考从 `camera_move` 视频提取，首尾帧也用 `extract_frames.py` 生成。

Wan 默认工作流会把 9 张图片参考和 3 个视频参考的首帧合并成参考网格，再通过 CLIP Vision 嵌入到 I2V 编码；`composition_reference` 存在时作为第二张构图参考。3 个音频参考在 Step 6 配音克隆和 Step 8 BGM/音效混音中消费。完整的多参考仍可通过自定义 `video_workflow.json` 的 `{ref_image_1..9}`、`{ref_video_1..3}`、`{ref_audio_1..3}` 占位符精细控制。

## 超出即梦的路线

- 即梦的多参考较弱，本管线用固定槽位的 9 图 + 3 视频 + 3 音频做“每个语义都有参考”，并把参考写入 `engine_plan.json` 可追溯。
- 即梦长镜头一致性靠模型内部记忆，本管线用显式的首尾帧锁链和跨片段审计，结果可检查、可重做。
- 即梦不支持精细控制多人站位，本管线用 `character_layout` + 构图参考 + 每角色 refs，把构图决策前置到分镜审核。
- 每个参考、每个 seed、每段运动文本都落到文件里，任何镜头不一致都能定位到具体参考和参数。
