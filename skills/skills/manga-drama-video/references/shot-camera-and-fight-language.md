# 分镜、运镜与打斗镜头语言

本文件用于 Step 2/3 的自动生成。Codex 必须先按本规则生成完整草稿，再交给用户审核；禁止只给出“大概分几个镜头”的空话。

## 自动生成顺序

1. 创意 brief 已批准。
2. 自动生成剧本：premise -> 剧情主线 -> 场景拆解 -> 每场 dialogue/narration -> 情绪节拍。
3. 自动分析人物：每集出场角色、目标、冲突、情绪变化、动作、服装状态、是否出现新造型。
4. 自动划分镜头：剧本节拍 -> 镜头数量 -> shot_type -> camera_move -> transition -> sfx。
5. 自动生成画面 prompt：全局风格 + 人物 prompt_fragment + 场景 prompt_fragment + 镜头描述。
6. 用户审核每步产物，批准后才进入下一步。

## 镜头数量分配

- 目标总镜头数来自 `00_meta.json.shots_total`。
- 按场景时长比例分配，同时按剧情节拍加权重：高潮场景可多 20-30% 镜头。
- 每个场景至少 3 个镜头；对话场景至少 4 个；打斗场景至少 5 个。
- 15 秒短剧：6-8 个镜头；30 秒：8-12 个；60 秒：12-18 个；90 秒：16-24 个。

## Shot type 用途

| Shot type | 什么时候用 |
| --- | --- |
| extreme wide | 建立场景、城池、宗门、战场、环境转折 |
| wide | 展示人物与场景关系、追逐、群体冲突 |
| medium | 对话、动作主体、普通叙事 |
| close-up | 情绪、反应、关键台词 |
| extreme close-up | 眼睛、手、武器、伤疤、道具细节 |
| over-shoulder | 对峙、对话双方、权谋压迫 |
| POV | 主角视线、发现、追击、坠入 |
| insert | 信物、剑、玉佩、药、血滴、机关 |

## Camera move 运镜库

| Camera move | 效果与用途 |
| --- | --- |
| static | 严肃对话、静止压迫、定格反转 |
| pan-L / pan-R | 横向揭示场景、跟踪移动 |
| tilt-up | 从脚下到头顶，展示威压、气势 |
| tilt-down | 从高处到人物，展示渺小、坠落 |
| push-in | 情绪升级、真相逼近、攻击前摇 |
| pull-back | 揭示大局、战后收束、孤独感 |
| handheld | 追逐、混乱、打斗、恐慌 |
| dolly-in | 连续逼近，长对话压力递增 |
| crash zoom | 冲击、爆发、发现 |
| whip-pan | 快速转场、打斗换招 |
| Dutch angle | 不安、危险、失衡 |
| orbit | 展示角色建模、庄严登场、大招 |

## 真动态镜头字段（Step 3 必写）

每个镜头必须写 `motion_text`：完整的一句话，包含主体动作、起止姿势、物理约束、镜头语言、时间跨度和口型约束；非说话镜头嘴巴闭合，说话镜头配合台词。`start_pose` / `end_pose` 用于跨镜头接续；打斗镜头写 `action_beat` 和 `impact_frame`。长镜头超过 6 秒拆成 2-4 段，用 `continuity_chain` 的首尾帧锁链连接，下一段必须以 `last_frame` 作为 `start_image`。

## 自动分镜规则

### 对话场景

1. wide 建立空间与人物关系。
2. over-shoulder 进入对话。
3. medium 给主要说话者。
4. close-up 给关键反应或台词。
5. 情绪升级时 push-in，停顿/反转时 static + close-up。

### 打斗场景

每场打斗至少按这个结构拆 5-8 个镜头：

1. `wide`：交代战场、双方距离、地形。
2. `medium`：起手式，pre-strike，tilt-down 或 dolly-in。
3. `impact frame`：碰撞瞬间，crash zoom / push-in，配 speed lines。
4. `close-up`：受击方表情、眼睛、痛感。
5. `insert`：武器、伤口、断裂、飞沙、碎片。
6. `POV`：对手逼近、追击、闪避。
7. `wide`：招式范围、环境破坏。
8. `pull-back`：打完后的结果、胜负关系。

每个打斗镜头必须写：

- `action_beat`：动作名称，例如“横斩/格挡/闪身/贴脸”
- `impact_frame`：`true/false`
- `sfx`：例如 `whoosh`, `clang`, `thud`, `glass-break`
- `transition_out`：打斗建议用 `whip` / `cut`，慢镜头用 `dissolve`

### 场景绘制一致性

重复出现的场景不能每集重新生成成另一个地方：

- 在 `scene-bible.md` 中为每个常驻场景锁定 `scene_id`、seed、canonical refs。
- 新一集先加载旧集的场景 refs，再生成本集画面。
- 同一场景只能改时间、天气、人物状态，不能改建筑结构、配色、材质。

## 自动 prompt 组装公式

```
全局风格 + 人物 prompt_fragment + 场景 prompt_fragment
+ shot_type + camera_move + action_beat
+ 时间/天气/光照 + 情绪 + 一致性词 + 画质词
```

## 用户审核

以下每一项都必须写成真实文件并暂停：

- `02_script.md`：剧本。
- `02_character_analysis.md`：本集人物分析。
- `03_storyboard.md`：完整分镜，含打斗、运镜、转场。
- `04_art_direction.md`：风格锁定与人物/场景 sheet。
- `05_images/`：参考图和每镜头成图。

用户说 `approve` 之后才能进入下一步；`revise` 时只改指定内容，并重跑受影响的下游草稿。
