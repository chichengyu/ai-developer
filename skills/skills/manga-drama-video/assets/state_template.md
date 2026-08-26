# STATE — <project-slug>

- last_completed_step: <0..9 | none>
- next_pending_step: <1..9>
- step_0_approved: <yes | no | pending>
- step_1_approved: <yes | no | pending>
- step_2_approved: <yes | no | pending>
- step_3_approved: <yes | no | pending>
- step_4_approved: <yes | no | pending>
- step_5_approved: <yes | no | pending>
- step_6_approved: <yes | no | pending>
- step_7_approved: <yes | no | pending>
- step_8_approved: <yes | no | pending>
- step_9_approved: <yes | no | pending>
- series_slug: <series-slug or null>
- episode_number: <EPNN or null>
- output_root: <absolute dir or null>
- continuity_version: <n>
- aspect_ratio: <9:16 | 16:9 | 1:1>
- resolution: <720p | 1080p | 4K>
- framerate: <24 | 30 | 60>
- target_length_sec: <n>
- motion_mode: <video-diffusion | talking-head-only | still-kenburns>
- character_style: <写实动漫 | 数字真人 | 经典动漫 | 美漫 | 水墨 | 治愈手绘 | 赛博朋克 | ...>
- tts_provider: <id or pending>
- voice_cast:
  - narrator: <voice id or pending>
  - <character>: <voice id or pending>
- shots_total: <n>
- shots_approved: <n>
- continuity_audit: <pending | match | needs_review | mismatch>
- deai_audit: <pending | pass | fail>
- resource_manifest: <pending | ok | blocked>
- engine_plan: <pending | ok>
- reference_bundle: <pending | ok | blocked>
- postprocess_plan: <pending | ok | blocked>
- output_export: <pending | ok | blocked>
- notes: <free text, e.g. user asked to redo SH2.3 with warmer lighting>

## Resume instructions

1. Re-read `00_meta.json` to confirm platform / style / length / output_root.
2. For series, re-read `00_series.json`, `character-bible.md`, `scene-bible.md`, and canonical refs before any image work.
3. Read the last completed step artifact and check whether the user approved it.
4. Skip to the next pending step. Do not re-run a completed step unless the user asks.
5. Re-pause for approval at the end of the resumed step.
