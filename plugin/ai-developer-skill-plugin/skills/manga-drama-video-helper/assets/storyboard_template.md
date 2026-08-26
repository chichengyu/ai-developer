# Storyboard - <project-slug>

## Scene <S1> - <location>

### SH1.1 - <shot title>

- duration_sec: <n>
- shot_type: <extreme wide | wide | medium | close-up | extreme close-up | over-shoulder | POV | insert>
- camera_move: <static | push-in | pull-back | pan-L | pan-R | tilt-up | tilt-down | orbit | follow | handheld | whip-pan | dolly-zoom>
- camera_start: <shot size, position, subject placement>
- camera_end: <shot size, position, subject placement>
- easing: <ease-in | ease-out | ease-in-out | none>
- time_segments: <0-3s ... / 3-6s ... / 6-10s ...>
- environment_effects: <wind / grass / snow / rain / particles>
- music_cue: <{start_at_s, end_at_s, mood}>
- sfx: <[{name, enter_at_s}]>
- scene_id: <from analysis>
- character_style: <inherited or override>
- image_prompt: "<Seedream seven-layer prompt>"
- reference_usage: <{图片1: character_front, 图片2: scene_wide}>
- motion_text: "<Seedance formula>"
- start_pose: <previous pose>
- end_pose: <next pose>
- lip_motion: <speaking | closed>
- lip_sync_audio: <audio/voice/<line_id>.mp3 when speaking>
- expression_plan: <eyes / brows / mouth / breathing / body>
- emotion_transition: <emotion before -> after>
- subtitle_zh: <中文台词，<=18字/行>
- subtitle_en: <English subtitle, <=36 chars/line>
- character_layout:
  - character_id: <id>
    position: <left-front | center | right-back>
    pose: <pose>
    refs: [<assets/characters/<id>_front.png>]
- dialogue_lines: []
- narration_offset: 0.0
- narration_text: ""
- transition_in: <fade-in | cut | dissolve | whip-pan | match-cut>
- transition_out: <cut | dissolve | whip-pan | match-cut>
- transition_reason: <why>
- jimeng_prompt: "<optional @图片N/@视频N/@音频N prompt>"
- fight_beats: <optional; 预备/发力/接触/反应/收势 with time segments>
- impact_frame: <optional; seconds>

### SH1.2 - <shot title>

- ...
