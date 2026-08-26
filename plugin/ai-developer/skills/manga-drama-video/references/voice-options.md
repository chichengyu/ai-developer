# Voice Options (Step 6)

Use this checklist before generating any audio. Always ask the user to pick the provider when more than one is available, and record the choice in `04_art_direction.md` under "Voice cast".

## 1. Pick the provider

| Provider | When it fits | How Codex reaches it |
| --- | --- | --- |
| Current model/API TTS | Default when configured and reachable | Use its documented speech endpoint; record provider/model in `engine_plan.json` |
| Installed `speech` skill | Fallback when current model/API lacks TTS | Call the `speech` skill directly |
| OpenAI TTS (gpt-4o-mini-tts, tts-1, tts-1-hd) | High quality, multiple voices, fast | `openai` audio speech endpoint via the Codex environment |
| Edge TTS (`edge-tts` Python) | Free, many Chinese voices (zh-CN, zh-HK), works offline-ish if preinstalled | Run the `edge-tts` CLI as a subprocess |
| Azure Speech | Enterprise / SSML control | Azure SDK if credentials are configured |
| ElevenLabs | Cinematic, voice cloning | ElevenLabs API key in env |
| Local (Piper / XTTS / CosyVoice) | Privacy, no API cost, works without network | Spawn the local CLI per line |

If you do not know which providers are reachable in the current Codex install, ask the user before guessing.

### Audio-reference cloning

When `reference_bundle.json` contains `audio.voice_timbre` or `audio.emotion_line`:

- Prefer a voice-cloning local provider: CosyVoice / GPT-SoVITS / XTTS, or ElevenLabs when the user allows API use.
- Use `voice_timbre` as the timbre reference and `emotion_line` as the delivery/emotion reference.
- Record the cloned `voice_id` in `06_voice/index.json` and in the character bible; the same voice id must be reused in later episodes.
- If no cloning provider is installed, ask the user before using a generic voice; never pretend a generic voice is the reference voice.

## 2. Pick the voice cast

Lock one narrator voice and one voice per speaking character. Use this template in `04_art_direction.md`:

```markdown
## Voice cast
- narrator: <voice id or name>
- <character A>: <voice id or name>
- <character B>: <voice id or name>
```

Rules:
- Keep the same voice across the whole video unless the user explicitly asks for a switch.
- For Chinese drama, prefer voices tagged `zh-CN` or 普通话 unless the user specifies a dialect.
- For male / female differentiation, sample at least one line per voice before locking it.

## 3. Per-line file naming

```
06_voice/<scene_id>__<line_index>.<ext>
```

Where `<line_index>` is zero-padded per scene (`01`, `02`, ...). Keep an `06_voice/index.json` of the form:

```json
[
  {
    "line_id": "S1_narration_01",
    "speaker": "narrator",
    "text": "这一次，他决定不再回头。",
    "file": "06_voice/S1__01.mp3",
    "duration_ms": 2400
  }
]
```

## 4. Failure handling

- If a TTS call returns an error, retry once with the same voice.
- If it still fails, retry with the documented fallback voice for that provider.
- If both attempts fail, surface the error to the user with the provider name and ask whether to switch providers, drop the line, or accept silence for that scene.

## 5. Sample rate / format targets

- Prefer `mp3` at 44.1 kHz, 128 kbps for portability, unless the provider only emits `wav` or `pcm`.
- When ffmpeg is available, normalize loudness with `loudnorm` before Step 8 so crossfades stay smooth.

## 6. De-AI voice check

- Reject robotic monotone, clipped sentence endings, flat emotion, and unnatural breath placement.
- Add natural pauses, sentence rhythm, and stress before accepting a line.
- If a TTS provider cannot express the required emotion, write a voice direction and regenerate with a different voice or provider.
- For talking-head shots, the mouth must follow the audio; any lip-sync mismatch is a `fail`.
- Lines that sound obviously AI-generated must be regenerated; do not ship them to Step 7.
