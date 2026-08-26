# 深度剧本分析框架

用于 Phase 1。生成 `03_deep_analysis.md` 和 `03_deep_analysis.json` 时，每一场、每个人物、每个镜头都必须有可执行字段，禁止只写“氛围要好”之类的抽象描述。

## 人物卡

每个人物至少填写：

```yaml
character_id: lin-mu
name: 林暮
role: protagonist
personality: [冷静, 责任感强, 克制, 对亲近的人心软]
motivation: 替失踪的师兄查明真相，同时保护妹妹
behavior_patterns: [发现线索先观察再行动, 受伤时习惯隐瞒, 说话前会先停顿]
appearance:
  face: 窄长脸，剑眉，眼尾微挑
  hair: 黑色高马尾，额前碎发
  body: 修长，清瘦但不单薄
  costume: 青灰长袍，深蓝腰带，白色内衬
  props: [黑鞘长剑, 师兄留下的旧玉佩]
voice: 低磁男声，语速偏慢，紧张时气息短促
emotional_arc: 平静 -> 动摇 -> 愤怒 -> 克制 -> 释然
action_beats: [拔剑前先握剑柄, 收到线索时手指收紧, 结尾把玉佩系回剑柄]
expression_plan:
  - beat: 看到遗物
    eyes: 视线先落在玉佩，再转向空座位
    brows: 缓慢下压
    mouth: 嘴唇抿紧，喉结滚动
    breathing: 屏息后长出一口气
    body: 肩膀下沉，手指收进袖口
  - beat: 听到师兄死讯
    eyes: 瞳孔微缩，眼眶泛红但不落泪
    brows: 紧皱
    mouth: 嘴角微颤
    breathing: 鼻息加重
    body: 重心后移半寸
emotion_layers: [克制, 隐忍, 愤怒蓄积, 责任]
continuity: 锁 seed 与 canonical refs，禁止跨镜换脸
```

## 场景卡

每场填写：

```yaml
scene_id: s1
location: 山门石阶
emotional_tone: 压抑肃杀
lighting: 傍晚逆光，人物边缘暖金，背景冷青
emotion_lighting: 冷青基调，情绪转折时人物受光从冷转暖
music:
  bgm_mood: 低鸣弦乐
  tempo_bpm: 80
  instruments: [cello, low drone, ticking percussion]
  intensity_curve:
    - t: 0.0
      level: 0.4
    - t: 0.5
      level: 0.7
    - t: 1.0
      level: 0.95
sfx:
  - name: 剑鸣
    enter_at_s: 2.5
  - name: 衣袂风响
    enter_at_s: 0.0
```

## 环境卡

环境必须给出可驱动粒子和运镜的具体数值：

```yaml
weather: 阴转小雪
wind:
  enabled: true
  intensity: 中等
  direction: 从右后方吹向镜头
grass:
  enabled: true
  motion: 麦浪式起伏
  intensity: 中
snow:
  enabled: true
  density: 小到中
  fall_speed: 慢
rain:
  enabled: false
  density: null
particles: [落雪, 灰尘, 剑气余晖]
atmosphere: [远处山雾, 近景冷光, 人物周围轻微暖光]
```

## 转场表

每次切换必须写 `transition` 和 `reason`：

| 转场 | 何时使用 | 示例原因 |
| --- | --- | --- |
| `fade-in` | 开场或长段情绪建立 | 从黑场进入雨夜，先让观众听见雨声 |
| `cut` | 同场景连续动作 | 同一个石阶上持续打斗，不用多余叠化 |
| `dissolve` | 时间流逝或情绪软化 | 从愤怒对质过渡到回忆 |
| `whip-pan` | 突然打断或紧张升级 | 人物听到门响立即甩镜到门口 |
| `match-cut` | 动作或空间匹配 | 上一镜收剑，下一镜拔剑 |

## 分镜字段

镜头数量默认 `clamp(round(target_seconds / 4), 4, 16)`；用户指定数量时以用户为准。每个镜头必须包含：

- `shot_id`：例如 `SH1.1`
- `shot_type`：extreme wide / wide / medium / close-up / extreme close-up / over-shoulder / POV / insert
- `camera_move`：static / push-in / pull-back / pan-L / pan-R / tilt-up / tilt-down / orbit / follow / handheld / whip-pan / dolly-zoom
- `duration_sec`：默认 3-6 秒，超过 6 秒拆成首尾帧链
- `image_prompt`：按 Seedream 七层结构生成
- `motion_text`：按 Seedance 公式生成
- `music_cue`：`{start_at_s, end_at_s, mood}`
- `sfx`：`[{name, enter_at_s}]`
- `lip_motion`：`speaking` 或 `closed`
- `transition_in` / `transition_out` / `transition_reason`

## 输出顺序

`03_deep_analysis.md` 按此顺序组织：

1. 项目概况与锁定参数
2. 人物分析
3. 场景与环境分析
4. 音乐与音效总表
5. 转场表
6. 分镜表
7. 连续性注意事项
8. De-AI 注意事项

`03_deep_analysis.json` 保持同一结构，字段名使用上面的 snake_case。

系列项目还必须读取 `references/series-continuity.md`，并在分析中加入 `previous_episode_summary`、`open_threads`、`character_state`、`scene_state`、`next_episode_hooks`。没有这些字段时，不得开始下一集。
