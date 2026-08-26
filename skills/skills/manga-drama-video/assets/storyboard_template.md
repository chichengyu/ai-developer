# Storyboard / Brief / Script / Art Direction Templates

Copy each section into the matching `outputs/<project-slug>/` or `outputs/<series-slug>/episodes/<EPNN>/NN_*.md` file and fill it in.

---

## Section A — Brief (01_brief.md)

```markdown
# Brief — <project-slug>

- **Premise:** <one sentence>
- **Genre:** <genre>
- **Platform:** <抖音 | 小红书 | B站 | YouTube | other>
- **Aspect ratio:** <9:16 | 16:9 | 1:1>
- **Resolution:** <720p | 1080p | 4K>
- **Framerate:** <24 | 30 | 60>
- **Target length:** <seconds>
- **Number of shots:** <count>
- **Character style:** <写实动漫 | 数字真人 | 经典动漫 | 美漫 | 水墨 | 治愈手绘 | 赛博朋克 | ...>
- **Audience + tone:** <who, what feeling>
- **Art style keywords:** <comma-separated>
- **Voiceover language / style:** <language + narrator/dialogue/mixed>
- **Must-include:**
  - <character>
  - <prop>
  - <plot beat>
- **Project slug:** <lowercase-hyphen>
- **Output directory:** <absolute path or null; images/scripts/videos are exported here>
```

Pair `01_brief.md` with a `00_meta.json` of the same shape so downstream steps can read machine-readable values.

---

## Section B — Script (02_script.md)

```markdown
# Script — <project-slug>

Total duration: <seconds>

## S1 — <location>
- duration_sec: <n>
- character_style_override: <null | 写实动漫 | 数字真人>
- summary: <1-2 sentences>
- music: <bgm_mood / tempo / instruments / intensity_curve>
- environment: <weather / wind / grass / snow / rain / particles / atmosphere>
- shot_plan:
  - shot_id: <SH1.1>
    duration_sec: <n>
    shot_type: <extreme wide / wide / medium / close-up / extreme close-up / over-shoulder / POV / insert>
    camera_move: <static / pan-L / pan-R / tilt-up / tilt-down / push-in / pull-back / handheld / dolly-in / crash-zoom / whip-pan / orbit / dutch-angle>
    action_beat: <optional; e.g. 蓄力 / 横斩 / 格挡 / 反应>
    sfx: [<剑鸣 @2.5s>, <衣袂声持续>]
    lip_motion: <closed | speaking>
- dialogue:
  - speaker: <name>
    line: "<line>"
- narration: "<voiceover line, <=18 zh chars>"
- emotion_beat: <adjective>

## S2 — <location>
- ...
```

Sum of `duration_sec` must equal target length.

---

## Section B2 — Character Analysis (02_character_analysis.md)

```markdown
# Character Analysis — <project-slug>

## <character_id> — <角色>
- episode_goal: <目标>
- emotional_arc: <起势 -> 转折 -> 落点>
- actions: <动作列表>
- wardrobe_state: <same as bible | new variant: <variant_id>>
- voice_tone: <锁定 voice_id 和情绪>
- continuity_notes: <哪些已锁定/待生成/需复核>
```

---

## Section C — Storyboard (03_storyboard.md)

After Step 4, every `image_prompt` is prefixed with the global style statement plus the relevant character `prompt_fragment`.

```markdown
# Storyboard — <project-slug>

## Scene S1

### SH1.1 — <shot title>
- duration_sec: <n>
- shot_type: <extreme wide / wide / medium / close-up / extreme close-up / over-shoulder / POV / insert>
- camera_move: <static / pan-L / pan-R / tilt-up / tilt-down / push-in / pull-back / handheld / dolly-in / crash-zoom / whip-pan / orbit / dutch-angle>
- time_segments: <optional; 0-3s 蓄力, 3-6s 斩击, 6-10s 收势>
- environment_effects: <copy from 02_script_analysis: wind intensity/direction, grass motion, snow, rain, particles, atmosphere>
- music_cue: <copy from 02_script_analysis: BGM mood, tempo, instruments, intensity curve, SFX enter times>
- scene_id: <from scene-bible, for recurring locations>
- character_style: <inherited or override>
- image_prompt: "<Seedream 七层结构: 格式 + 主体 + 构图 + 光影 + 画面内文字 + 风格 + 锁定项；参考槽位按内容点名>"
- reference_usage: <optional; 例如 {图片1: "character_front 作为人物形象", 图片2: "scene_wide 作为场景背景"}>
- motion_text: "<Seedance 公式: 主体 + 场景 + 动作 + 运镜 + 分时段 + 转场特效 + 音频 + 风格氛围；非说话镜头嘴巴闭合>"
- start_pose: <起始姿势，跨镜头接续>
- end_pose: <结束姿势，跨镜头接续>
- physics_notes: <重力、武器、脚步、衣发>
- lip_motion: <speaking | closed>
- character_layout:
  - character_id: <from bible>
    position: <left-front / center / right-back / ...>
    pose: <动作姿势>
    refs: [<refs/<character_id>_front.png>]
- continuity_chain:
  - previous_last_frame: <05_video/SHx.y_last.png or null>
  - next_first_frame: <05_video/SHx.z_first.png or null>
- dialogue_lines: []
- narration_offset: 0.0
- narration_text: ""
- action_beat: <optional; e.g. 横斩 / 格挡 / 闪身>
- impact_frame: <true / false; required for fight shots>
- clip_target_ms: <optional; default duration_sec * 1000>
- sfx: []
- transition_in: <fade-in / cut / dissolve / whip / match-cut>
- transition_out: <cut / dissolve / whip / match-cut>
- jimeng_prompt: <optional; 仅用户明确选择即梦在线工具时生成，使用 @图片N/@视频N/@音频N 语法>

### SH1.2 — <shot title>
- ...

## Scene S2
- ...
```

---

## Section D — Art Direction (04_art_direction.md)

```markdown
# Art Direction — <project-slug>

## Character style
<写实动漫 | 数字真人 | 经典动漫 | 美漫 | 水墨 | 治愈手绘 | 赛博朋克>

## Global style statement
<3-5 sentences, paste the matching preset block from references/character-styles.md or references/art-style-presets.md>

## Color palette
- #RRGGBB — <name>
- #RRGGBB — <name>
- #RRGGBB — <name>
- #RRGGBB — <name>
- #RRGGBB — <name>

## Character sheets

### <Name>
- role: <protagonist / antagonist / supporting>
- silhouette: <one-line shape description>
- signature_colors: <hex list>
- recurring_props: <list>
- prompt_fragment: "<reusable 1-2 sentence prompt chunk>"
- reference_image: <filled in Step 5: refs/<character_id>_front.png>

## Background motifs
- <location A>: <how to render>
- <location B>: <how to render>

## Scene sheets

### <scene_id> — <场景>
- structure: <one-line>
- palette: <hex list>
- lighting: <default + allowed weather/time changes>
- recurring_props: <list>
- prompt_fragment: "<reusable 1-2 sentence scene prompt chunk>"
- reference_image: <filled in Step 5: refs/<scene_id>_wide.png>

## Do / Don't
- Do: <...>
- Don't: <...>

## Voice cast (filled in Step 6)
- narrator: <voice id or pending>
- <character>: <voice id or pending>
```
