# Mini run reference — neon-cat-alley

This is a tiny reference project showing what early step outputs should look like. It includes Step 0-2 artifacts (character bible, scene bible, style lock, brief, script, character analysis) plus a STATE.md stub; Steps 3-8 depend on real imagegen / speech / ffmpeg runs and are intentionally omitted.

Use it to:
- See the JSON shape of `00_meta.json`.
- See the structure of `01_brief.md`, `02_script.md`, `STATE.md`.
- Read `outputs/00_meta.json` to see the machine-readable brief shape.
- Read `outputs/character-bible.md`, `outputs/scene-bible.md`, and `outputs/style-lock.json` to see the continuity-lock pattern.
- Read `outputs/resource_manifest.json` and `outputs/engine_plan.json` to see the resource/engine orchestration pattern.
- Read `outputs/01_brief.md`, `outputs/02_script.md`, and `outputs/02_character_analysis.md` to see the early-step document style.

To drive the example forward yourself, copy `outputs/` to a working directory and run `$manga-drama-video` from Step 4 onward.
