#!/usr/bin/env python3
"""Generate a bilingual Chinese-English SRT from the audio manifest."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def probe_duration(path):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, OSError):
        return None


def chunk_text(text, max_chars):
    if not text:
        return []
    return [text[index:index + max_chars] for index in range(0, len(text), max_chars)]


def chunk_english(text, max_chars):
    words = text.split()
    if not words:
        return []
    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def format_srt_time(seconds):
    total_ms = max(int(round(seconds * 1000)), 0)
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def main(argv):
    parser = argparse.ArgumentParser(description="Generate bilingual Chinese-English SRT from audio/manifest.json.")
    parser.add_argument("project_dir", help="Project root created by init_project.py.")
    parser.add_argument("--output", help="Output SRT path relative to project root.")
    args = parser.parse_args(argv)

    root = Path(args.project_dir).resolve()
    manifest_path = root / "audio" / "manifest.json"
    manifest = load_json(manifest_path)
    if not manifest:
        print(f"missing audio manifest: {manifest_path}", file=sys.stderr)
        return 1

    voice = manifest.get("voice") or []
    if not voice:
        print("audio/manifest.json has no voice entries", file=sys.stderr)
        return 1

    cues = []
    for index, entry in enumerate(voice):
        text_zh = str(entry.get("text", "")).strip()
        text_en = str(entry.get("text_en", "")).strip()
        if not text_zh or not text_en:
            print(f"voice entry {index} must contain text and text_en", file=sys.stderr)
            return 1
        audio_path = root / entry["file"]
        start = float(entry.get("start_at_s", 0.0))
        duration = float(entry.get("duration_sec", 0.0))
        if duration <= 0:
            if entry.get("end_at_s") is not None:
                duration = max(float(entry["end_at_s"]) - start, 0.5)
            else:
                duration = probe_duration(audio_path) or 2.0
        end = start + max(duration, 0.5)

        speaker = str(entry.get("speaker", "")).strip()
        prefix = f"[{speaker}] " if speaker else ""
        zh_lines = chunk_text(text_zh, 18)
        en_lines = chunk_english(text_en, 36)
        subtitle_lines = [
            f"{prefix}{line}" if index == 0 else line
            for index, line in enumerate(zh_lines)
        ]
        subtitle_lines += en_lines
        cues.append({
            "start": start,
            "end": end,
            "lines": subtitle_lines,
        })

    cues.sort(key=lambda item: item["start"])
    output_path = root / (args.output or "scripts/06_subtitles_bilingual.srt")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    blocks = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(str(index))
        blocks.append(f"{format_srt_time(cue['start'])} --> {format_srt_time(cue['end'])}")
        blocks.extend(cue["lines"])
        blocks.append("")

    output_path.write_text("\n".join(blocks).rstrip() + "\n", encoding="utf-8-sig")
    print(f"wrote: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
