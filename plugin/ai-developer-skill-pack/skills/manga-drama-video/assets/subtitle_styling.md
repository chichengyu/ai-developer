# Subtitle Styling Notes

Read these when generating `07_subtitles.srt`. They are kept separate from the SRT template so the template file stays a clean playable .srt.

## Encoding

- File must be UTF-8 **without BOM** so ffmpeg reads it correctly. PowerShell `Set-Content -Encoding UTF8` and many editors add a BOM by default; strip it before saving.

## Speaker tags

- Use `[旁白]` for narrator lines, `[女主]`, `[男主]`, `[路人]` etc. for characters. Keep the bracket tag consistent within one project.

## Hard limits per cue

- <= 18 zh chars per line
- <= 2 lines per cue
- <= 36 zh chars total per cue
- If a line exceeds this, break it into two cues with a 200 ms gap.

## Pacing

- If dialogue is rapid-fire, merge two consecutive cues into one if total chars stay under the limit, so the viewer is not reading too fast.
- Bottom margin: keep `MarginV=24` or larger; never overlap lower-third graphics.

## Burned-in subtitle styling (compose.py)

- Default font preference list: Noto Sans CJK SC, Noto Sans SC, Source Han Sans SC, PingFang SC, Microsoft YaHei, Arial Unicode MS.
- Force style: white primary, black outline, BorderStyle=1, Outline=2, Shadow=1, FontSize=24, MarginV=24.
- Override per project with `python compose.py <project_dir> --font <name>`.

## De-AI subtitle check

- File must remain UTF-8 without BOM; no mojibake, no replacement characters, no zero-width characters.
- Speaker tags must match the locked voice cast; do not swap `[旁白]` and `[男主]`.
- Cue timing must align with the audio; no early/late starts and no overlapping cues.
- Punctuation must be complete; no machine-translation word order, no duplicated filler, no gibberish.
- Keep each cue to 2 lines max and 18 Chinese characters per line; never cover a face or key action.
- Stage directions, action descriptions, and emoji must not appear in burned subtitles.
