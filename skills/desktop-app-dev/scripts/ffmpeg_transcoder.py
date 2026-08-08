"""ffmpeg / ffprobe wrapper with live progress for the desktop UI."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from media_downloader import CancelToken


class TranscodeError(RuntimeError):
    """Raised when ffmpeg exits non-zero."""


@dataclass
class MediaInfo:
    duration_s: float | None
    format_name: str | None
    streams: list[dict]


@dataclass
class TranscodeProgress:
    task_id: int | str | None
    stage: str
    percent: float | None
    out_time_s: float | None
    speed: str | None


def probe_media(path: str | Path, ffprobe_path: str = "ffprobe") -> MediaInfo | None:
    """Return duration and stream info; None when ffprobe is unavailable."""
    if not shutil.which(ffprobe_path):
        return None
    command = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    duration_text = data.get("format", {}).get("duration")
    duration = float(duration_text) if duration_text else None
    return MediaInfo(
        duration_s=duration,
        format_name=data.get("format", {}).get("format_name"),
        streams=data.get("streams", []),
    )


def transcode_file(
    src: str | Path,
    dst: str | Path,
    video_codec: str = "libx264",
    video_preset: str = "medium",
    crf: int = 23,
    audio_codec: str = "aac",
    extra_args: list[str] | None = None,
    progress: Callable[[TranscodeProgress], None] | None = None,
    cancel: CancelToken | None = None,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    task_id: int | str | None = None,
) -> Path:
    """Transcode a media file and emit progress from ffmpeg -progress."""
    if not shutil.which(ffmpeg_path):
        raise TranscodeError("ffmpeg not found on PATH")
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    info = probe_media(src, ffprobe_path=ffprobe_path)
    duration = info.duration_s if info else None

    args = [
        ffmpeg_path,
        "-y",
        "-i",
        str(src),
        "-c:v",
        video_codec,
        "-preset",
        video_preset,
        "-crf",
        str(crf),
        "-c:a",
        audio_codec,
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    if extra_args:
        args.extend(extra_args)
    args.append(str(dst))

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_lines: list[str] = []

    def drain_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            stderr_lines.append(line)

    thread = threading.Thread(target=drain_stderr, daemon=True)
    thread.start()

    out_time: float | None = None
    speed: str | None = None
    if process.stdout is not None:
        for line in process.stdout:
            if cancel and cancel.cancelled:
                process.kill()
                raise TranscodeError("transcode cancelled")
            key, _, value = line.strip().partition("=")
            if key == "out_time_ms" and value:
                with suppress(ValueError):
                    out_time = int(value) / 1_000_000
            elif key == "speed":
                speed = value
            if progress:
                percent = None
                if duration and out_time is not None:
                    percent = min(1.0, out_time / duration)
                progress(
                    TranscodeProgress(
                        task_id=task_id,
                        stage="transcode",
                        percent=percent,
                        out_time_s=out_time,
                        speed=speed,
                    )
                )

    process.wait()
    thread.join()
    if process.returncode != 0:
        raise TranscodeError("".join(stderr_lines)[-1000:])
    return dst


if __name__ == "__main__":
    print("desktop-app-dev ffmpeg_transcoder: import transcode_file() for ffmpeg transcoding.")
