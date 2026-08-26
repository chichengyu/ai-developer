# 系列连续性与自动续写

用于多集漫剧、短剧和“下一集”续写。此文件是硬约束：没有完成上一集锁定时，不能开始下一集；没有复用 canonical refs 时，不能重新生成同一人物。

## 核心规则

1. 同一张脸永远同一张脸。人物 ID、脸型、发型、服装、体型、武器、声音和 seed 一旦锁定，所有后续集数必须复用，禁止只写“保持上一集一样”却不加载参考图。
2. 一集必须衔接一集。下一集以上一集结尾、未解决线索、人物状态和场景状态为起点，禁止每集重启剧情。
3. 自动生成剧本默认开启动态续写。用户要求“系列”“下一集”“继续拍”“写第二集”时，必须进入系列模式。
4. 用户没有明确指定模型时，使用当前模型完成剧本、分析和编排；用户指定外部模型后，模型信息写入系列清单。

## 系列文件

系列根目录必须包含：

```text
<series-dir>/
  00_series.json
  character-bible.md
  scene-bible.md
  episodes/EP01/
    manifest.json
    scripts/
    assets/characters/
    assets/scenes/
    audio/
    video/
  episodes/EP02/
    ...
```

`00_series.json` 至少包含：

```json
{
  "series_slug": "shanmen-jiange",
  "continuity_version": 1,
  "episodes": ["EP01"],
  "last_episode": "EP01",
  "model_default": "current",
  "flow_mode": "manual",
  "engine_overrides": {},
  "characters": {
    "lin-mu": {
      "name": "林暮",
      "seed": 1001,
      "refs": [
        "episodes/EP01/assets/characters/lin_mu_front.png",
        "episodes/EP01/assets/characters/lin_mu_three_quarter.png"
      ],
      "voice_id": "lin-mu-voice"
    }
  },
  "scenes": {
    "s1": {
      "name": "山门石阶",
      "seed": 2001,
      "refs": [
        "episodes/EP01/assets/scenes/s1_wide.png",
        "episodes/EP01/assets/scenes/s1_detail.png"
      ]
    }
  }
}
```

`character-bible.md` 和 `scene-bible.md` 沿用 `manga-drama-video` 的模板，记录每个常驻人物和场景的固定 `prompt_fragment`、seed、canonical refs、服装变体和禁止修改项。

## 自动续写流程

1. 读取 `00_series.json`、`character-bible.md`、`scene-bible.md`。
2. 读取上一集 `02_script.md`、`03_deep_analysis.json`、`04_storyboard.md` 和所有已批准 refs。
3. 生成上一集的 `episode_handoff.json`，写入每集 `scripts/`：

```json
{
  "episode": "EP01",
  "previous_episode": null,
  "previous_episode_summary": "林暮在山门发现师兄遗物，被神秘人盯上",
  "open_threads": ["遗物中的地图指向哪里", "神秘人为何监视山门", "妹妹是否卷入"],
  "character_state": {
    "lin-mu": "右手轻伤，已换上夜行衣"
  },
  "scene_state": {
    "s1": "山门被雨淋湿，石阶有脚印"
  },
  "next_episode_hooks": ["EP02 开场从石阶脚印开始"]
}
```

4. 下一集剧本必须引用 `open_threads` 和 `next_episode_hooks` 作为开头，并设置新的悬念供 EP03 继续。
5. 每集完成后更新 `00_series.json` 的 `episodes`、`last_episode` 和 `continuity_version`。

## 人物跨集锁定

同一人物在下一集出现时：

- `character_id` 不得改变。
- `front`、`three_quarter`、`expression`、`action` 参考图必须来自上一集已批准 refs。
- 固定 seed 不得改变。
- `prompt_fragment` 中关于脸型、发型、服装、配色、体型、武器和声音的措辞不得改变。
- 新服装、伤疤、发型变化必须先更新 `character-bible.md` 和 `00_series.json`，获得用户确认后，才生成新的变体 refs。
- 已批准变体可以在后续集数复用；未批准的变体不得出现在图片、视频或提示词中。

## 场景跨集锁定

- `scene_id` 不得改变。
- 场景结构、材质、标志物、配色和机位参考必须复用已批准 refs。
- 天气、灯光、季节可以在场景 bible 允许的范围内变化，但建筑结构和道具位置不能变。

## 声音与模型

- 同一角色的 `voice_id` 和音色全系列复用；换声必须更新角色表并得到用户确认。
- 用户未指定模型时使用当前模型；如果后续改用外部模型，必须在 `00_series.json` 的 `engine_overrides` 中记录，并检查是否会改变人物形象。
- 用户要求“全自动/用户只审核”时，`flow_mode` 设为 `auto_review`；自动模式仍按“剧本审核 -> 素材审核 -> 视频审核”执行，不跳过任何关卡。

## 续集检查清单

- [ ] 已加载 `00_series.json` 和上一集 refs。
- [ ] 每个常驻人物都有对应 canonical refs。
- [ ] 剧本开头承接上一集 `open_threads`。
- [ ] 新剧本结尾包含 `next_episode_hooks`。
- [ ] 人物 ID、seed、voice_id 未改变。
- [ ] 场景 ID、seed、结构未改变。
- [ ] 生成图片时引用 refs，而不是只靠文字描述。
- [ ] 出现 `mismatch` 时回退上一集 refs，不直接改文字硬凑。
