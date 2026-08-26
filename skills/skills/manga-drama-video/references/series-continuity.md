# 系列跨集一致性锁 (Series Continuity Lock)

本文件是 **最高优先级约束**。只要项目是系列剧，或用户说要继续做下一集，就必须先读取本文件，再执行 Step 0。

## 核心原则

张三在第 1 集长什么样，第 10 集就必须长什么样。人物、场景、服装、配色、脸型、体型、声音、Prompt fragment、seed、参考图都不能在下一集被“重新生成”成另一张脸。

## 必须存在的系列目录

```
outputs/<series-slug>/
  00_series.json
  character-bible.md
  scene-bible.md
  style-lock.json
  refs/
    <character_id>_front.png
    <character_id>_three_quarter.png
    <character_id>_side.png
    <character_id>_expressions.png
    <scene_id>_wide.png
    <scene_id>_detail.png
  episodes/
    EP01/
      00_meta.json
      ...
    EP02/
      00_meta.json
      ...
```

单集项目仍使用 `outputs/<project-slug>/`；但用户一旦表示这是系列剧，必须升级为上述目录，禁止继续把每一集散落在独立目录里。

## `00_series.json` schema

```json
{
  "series_slug": "zhang-san-legend",
  "series_title": "张三传奇",
  "character_style": "写实动漫",
  "style_seed": 20260801,
  "continuity_version": 1,
  "characters": [
    {
      "character_id": "zhang-san",
      "name": "张三",
      "role": "protagonist",
      "canonical_refs": [
        "refs/zhang-san_front.png",
        "refs/zhang-san_three_quarter.png",
        "refs/zhang-san_side.png",
        "refs/zhang-san_expressions.png"
      ],
      "seed": 1001,
      "prompt_fragment": "同一人物设定，同一张脸，同一发型，同一服装，同一配色，同一体型，同一五官比例，角色一致性",
      "voice_id": "pending",
      "first_episode": "EP01",
      "last_episode": "EP01",
      "locked": true
    }
  ],
  "locations": [
    {
      "scene_id": "zhang-home",
      "name": "张三老宅",
      "canonical_refs": ["refs/zhang-home_wide.png"],
      "seed": 2001,
      "prompt_fragment": "同一场景设定，同一建筑结构，同一配色，同一光照风格，同一材质，场景一致性"
    }
  ],
  "palette": [],
  "rules": [
    "不得跨集更换已锁定角色的脸型、五官比例、发型、服装配色。",
    "新一集必须加载上一集已批准的 canonical refs 与 seed。",
    "任何角色外观变更必须先在 character-bible.md 中说明，经用户批准后才可生成新参考图。"
  ]
}
```

## 新一集启动流程（Step 0）

1. 读取 `outputs/<series-slug>/00_series.json`。
2. 读取 `character-bible.md` 和 `scene-bible.md`。
3. 读取 `refs/` 下所有 canonical refs，并记住每个角色的 seed、Prompt fragment、voice_id。
4. 创建 `episodes/<EPNN>/`，并把上一集的 `04_art_direction.md`、`05_images/refs/`、`06_voice/index.json` 的 voice cast 作为本集起点。
5. 只有在上一步全部加载成功后，才允许生成新的剧本和图片。
6. 如果用户说“换一个风格”“换一张脸”，视为整剧设计变更：更新 bible、bump `continuity_version`、重新生成 canonical refs，并询问是否回溯重做旧集。

## 禁止事项

- 禁止只靠文字“类似上一集”重新生成人物，必须传入已批准参考图。
- 禁止在新一集里给同一角色改名字、改 character_id、改 seed。
- 禁止只改 prompt 里的一句“保持同一人物”却不加载参考图。
- 禁止在同一集或跨集混用 3D 国风动漫 / 写实动漫 / 数字真人 / 经典动漫。
- 禁止在未更新 bible 的情况下新增“看起来像换人”的服装、发型或体型。

## 跨集一致性审计

每次 Step 5 图片生成完成、以及 Step 8 成片前，都必须写 `05_images/continuity_audit.md`：

- 逐角色列出 canonical ref 文件、seed、本集使用次数。
- 逐张截图与本集 canonical ref 对比，标注 `match / mismatch / needs_review`。
- 任何 `mismatch` 必须重做，不得进入下一阶段。
- 若跨集比较发现差异，立即暂停并列出差异来源：光照、服装、发型、脸型、seed、风格词。

## 用户批准要求

- Step 0 的 bible 必须经用户批准。
- 新一集启动时必须让用户确认“本集继续使用已锁定角色，不换脸”。
- 任何角色设计变更必须单独获得 `approve continuity change`，不能混在 Step N 的普通修改里。
