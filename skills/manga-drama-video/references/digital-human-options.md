# Digital Human (数字真人) Options

Use this when a scene uses `character_style: 数字真人`, or when the user wants a talking-head / face-cam scene inserted into an otherwise illustrated story.

## What "digital human" means in this skill

A photoreal AI-generated human that:
- can be either a still portrait (driven by Ken Burns + voiceover) or
- a fully lip-synced talking head (driven by audio + a face animation model).

The default pipeline uses the currently configured model/API: keyframe -> audio-driven video/lip sync -> composition. Local video diffusion is only used when the user explicitly selects local mode. Still-portrait + Ken Burns is only a downgrade mode when no video engine or face-animation tool is available.

## Provider matrix

| Provider | Type | Reach | Best for | Notes |
| --- | --- | --- | --- | --- |
| Built-in talking-head skill (Codex MCP) | online | If installed in this Codex | Quickest talking head | Check via `scripts/check_deps.sh` first |
| MiniMax-H3 (video API) | cloud | API key + outbound network | Audio-driven lip sync with a character image/video; native dialogue audio | 4-15s clips; long shots need frame-chain; action may blur |
| Seedance 2.0 (Jimeng) | cloud | API key or platform | Cinematic camera, motion and audio design | Use `@音频` references; online only when user explicitly selects it |
| HeyGen | API | API key + outbound network | Polished talking head, multilingual | Paid; produces mp4 with burned animation |
| D-ID | API | API key + outbound network | Single-portrait animation | Paid |
| SadTalker | local | ComfyUI or Python + checkpoints, GPU preferred | Free, offline | Audio-driven lip sync; heavier setup |
| LivePortrait | local | ComfyUI or Python + checkpoints, GPU preferred | Free, expressive | Head pose + expression; pair with audio for lip sync |
| Hallo | local | Python + checkpoints, GPU preferred | Free, audio-driven | Good lip sync |
| MuseTalk | local | Python + checkpoints, GPU preferred | Free, real-time capable | Good lip sync, lighter than SadTalker |
| AnimateDiff + portrait LoRA | local | Python + GPU | Stylized animation, not pure realism | Use only if user explicitly wants stylized |
| None (still portrait only) | n/a | Always | Last-resort fallback | No lip sync; only use after user accepts the downgrade |

## How to choose

1. Check `model_config.json` / `engine_plan.json` first and confirm which current model/API is reachable.
2. If the user said 数字真人, default to **video-diffusion + audio-driven lip sync** through the current model/API when available.
3. If the current model/API cannot drive lip sync, try a cloud talking-head API, then local tools only if the user explicitly selects local mode; do not silently switch engines.

## Prompt recipe for still digital humans

Use `references/character-styles.md` Section 2 prompt fragment, plus:

> photorealistic digital human, ultra-detailed skin with pores and fine hair, no stylization, no anime outlines, 85mm lens, shallow depth of field, shot on Sony A7IV, color graded for short-video vertical delivery, sharp eyes with catchlights, natural expression

Compose the face on a clean background (one solid color, RGB 200/200/200) so the Ken Burns pan and any face animation model can isolate the face cleanly.

## File layout for digital-human assets

```
05_images/refs/<name>_front.png         # anchor portrait
05_images/refs/<name>_three_quarter.png
05_images/refs/<name>_side.png
05_images/refs/<name>_expressions.png
05_images/refs/<name>.json              # seed, model, prompt, provider
05_images/SH<scene>.<shot>.png          # keyframe for video diffusion
05_video/SH<scene>.<shot>.mp4           # real-motion clip
06_voice/<scene>__<line>.<ext>          # voiceover or dialogue
06_face/<scene>.<shot>_lip.mp4          # lip-synced clip (speaking shots)
```

## When to fall back to still-portrait

If no talking-head provider is reachable:
- Ask the user first: configure a cloud lip-sync API, install a local talking-head tool (only when local mode is selected), accept voice-only, or stay on still-portrait.
- Use a stronger Ken Burns pan (push-in 8-12% over the shot duration) to compensate for the lack of facial motion.
- Add a 150 ms cross-dissolve on cuts to make the still portraits feel less static.
- Write the downgrade into `STATE.md.notes` and `04_art_direction.md`; never switch silently.
