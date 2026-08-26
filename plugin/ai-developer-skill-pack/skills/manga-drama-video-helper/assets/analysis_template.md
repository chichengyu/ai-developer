# Deep Analysis - <project-slug>

## Project lock

- project_slug: <slug>
- output_root: <absolute path>
- aspect_ratio: <9:16 | 16:9 | 1:1>
- character_style: <写实动漫 | 数字真人 | 经典动漫 | 其他>
- target_length_sec: <n>
- engine_overrides: <null | user-specified>

## Series continuity

- series_slug: <null | slug>
- episode_number: <null | EP01>
- continuity_version: <n>
- previous_episode: <null | EP00>
- previous_episode_summary: <last episode ending>
- open_threads: <unresolved clues to continue>
- next_episode_hooks: <new suspense for next episode>
- character_state: <status changes per character>
- scene_state: <status changes per scene>

## Characters

### <character_id> - <name>

- role: <protagonist | antagonist | supporting>
- personality: <3-5 traits>
- motivation: <goal>
- behavior_patterns: <list>
- appearance: <face / hair / body / costume / props>
- voice: <tone and TTS id>
- emotional_arc: <start -> turn -> end>
- action_beats: <list>
- expression_plan: <[{beat, eyes, brows, mouth, breathing, body}]>
- emotion_layers: <list of layered emotions>
- continuity: <locked seed and refs>
- locked_refs: <previous episode canonical refs to reuse>
- voice_id: <same voice across all episodes>

## Scenes

### <scene_id> - <location>

- emotional_tone: <adjective>
- lighting: <light source, direction, color>
- emotion_lighting: <how lighting changes with emotional beats>
- music:
  - bgm_mood: <mood>
  - tempo_bpm: <number>
  - instruments: <list>
  - intensity_curve: <[{t, level}]>
- sfx: <[{name, enter_at_s}]>

## Environment

- weather: <type>
- wind: <enabled / direction / intensity>
- grass: <enabled / motion / intensity>
- snow: <enabled / density / fall_speed>
- rain: <enabled / density / angle>
- particles: <list>
- atmosphere: <list>

## Transitions

- from: <open | scene_id>
- to: <scene_id>
- transition: <fade-in | cut | dissolve | whip-pan | match-cut>
- reason: <why>

## Storyboard

### SH<scene>.<shot>

- shot_type: <wide | medium | close-up | ...>
- camera_move: <push-in | pan-L | ...>
- camera_start: <start shot size and framing>
- camera_end: <end shot size and framing>
- easing: <ease-in | ease-out | ease-in-out>
- duration_sec: <n>
- image_prompt: <Seedream seven layers>
- motion_text: <Seedance formula>
- music_cue: <{start_at_s, end_at_s, mood}>
- sfx: <[{name, enter_at_s}]>
- lip_motion: <speaking | closed>
- lip_sync_audio: <audio/voice/<line_id>.mp3 when speaking>
- expression_plan: <micro-expressions for this shot>
- emotion_transition: <emotional state before -> after>
- transition_in: <type>
- transition_out: <type>
- transition_reason: <why>
- fight_beats: <optional; prepare/strike/impact/reaction/recover>
- impact_frame: <optional; seconds>

## Continuity & De-AI notes

- <character and scene refs must be reused>
- <non-speaking shots keep mouth closed>
- <motion must obey gravity, no foot sliding>
- <particles and sfx must align with timeline>
