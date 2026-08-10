"""Lightweight media/file probing for downloaded resources.

Uses container magic bytes and simple box parsing so metadata is available
without requiring ffprobe. When ffprobe exists it is preferred for duration
and stream information.
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Any


def sniff_media_type(path: str | Path) -> str | None:
    """Return a short media type from container magic bytes."""
    try:
        head = Path(path).read_bytes()[:64]
    except OSError:
        return None
    if not head:
        return None
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "webm" if b"webm" in head.lower() else "matroska"
    if head.startswith(b"\x00\x00\x00") and head[4:8] == b"ftyp":
        brand = head[8:12].lower()
        if brand in {b"m4a ", b"m4b ", b"m4p "}:
            return "m4a"
        return "mp4"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"fLaC"):
        return "flac"
    if head.startswith(b"ID3") or head.startswith((b"\xff\xfb", b"\xff\xf3")):
        return "mp3"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return "avi"
    if head.startswith(b"FLV"):
        return "flv"
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"GIF8"):
        return "gif"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"WEBP"):
        return "webp"
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if len(head) >= 376 and head[0] == 0x47 and head[188] == 0x47:
        return "ts"
    return None


def _box_children(data: bytes, box_type: bytes) -> list[tuple[bytes, bytes]]:
    children: list[tuple[bytes, bytes]] = []
    offset = 0
    while offset + 8 <= len(data):
        size = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        if size < 8:
            break
        payload = data[offset + 8 : offset + size]
        if kind == box_type:
            children.append((kind, payload))
        offset += size
    return children


def _find_box(data: bytes, box_type: bytes) -> bytes | None:
    for _kind, payload in _box_children(data, box_type):
        return payload
    return None


def parse_mp4_metadata(path: str | Path) -> dict[str, Any]:
    """Parse duration from an MP4/M4A mvhd box when available."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        return {"error": str(exc)}
    moov = _find_box(data, b"moov")
    if not moov:
        return {}
    mvhd = _find_box(moov, b"mvhd")
    if not mvhd or len(mvhd) < 24:
        return {}
    try:
        version = mvhd[0]
        if version == 1:
            timescale = struct.unpack(">I", mvhd[20:24])[0]
            duration = struct.unpack(">Q", mvhd[24:32])[0]
        else:
            timescale = struct.unpack(">I", mvhd[12:16])[0]
            duration = struct.unpack(">I", mvhd[16:20])[0]
    except struct.error as exc:
        return {"error": str(exc)}
    if not timescale:
        return {}
    return {
        "duration_seconds": round(duration / timescale, 3),
        "timescale": timescale,
        "duration_ticks": duration,
    }


def parse_subtitle_file(path: str | Path) -> dict[str, Any]:
    """Detect WebVTT/SRT/ASS and return basic cue counts."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8", errors="replace")[:512 * 1024]
    except OSError as exc:
        return {"error": str(exc)}
    lower = text.lstrip()
    if lower.startswith("WEBVTT"):
        return {
            "format": "webvtt",
            "cues": sum(1 for line in text.splitlines() if "-->" in line),
        }
    if lower.startswith(("[Script Info]", "[V4+ Styles]")):
        return {
            "format": "ass",
            "cues": sum(
                1 for line in text.splitlines() if line.startswith("Dialogue:")
            ),
        }
    if "-->" in text and re_match_srt(text):
        return {
            "format": "srt",
            "cues": sum(1 for line in text.splitlines() if "-->" in line),
        }
    return {"format": "unknown"}


def re_match_srt(text: str) -> bool:
    import re

    return bool(re.search(r"^\s*\d+\s*$", text, re.MULTILINE))


def _probe_with_ffprobe(path: str | Path) -> dict[str, Any] | None:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout or "{}")
    except Exception:
        return None
    return None


def _image_dimensions(path: str | Path) -> dict[str, int] | None:
    try:
        data = Path(path).read_bytes()[:64]
    except OSError:
        return None
    if data.startswith(b"\x89PNG") and len(data) >= 24:
        return {
            "width": struct.unpack(">I", data[16:20])[0],
            "height": struct.unpack(">I", data[20:24])[0],
        }
    if data.startswith(b"GIF8") and len(data) >= 10:
        return {
            "width": struct.unpack("<H", data[6:8])[0],
            "height": struct.unpack("<H", data[8:10])[0],
        }
    if data.startswith(b"\xff\xd8\xff"):
        with suppress(Exception):
            data_full = Path(path).read_bytes()[: 2 * 1024 * 1024]
            index = 2
            while index + 9 < len(data_full):
                if data_full[index] != 0xFF:
                    index += 1
                    continue
                marker = data_full[index + 1]
                if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    height = struct.unpack(">H", data_full[index + 5 : index + 7])[0]
                    width = struct.unpack(">H", data_full[index + 7 : index + 9])[0]
                    return {"width": width, "height": height}
                length = struct.unpack(">H", data_full[index + 2 : index + 4])[0]
                index += 2 + length
    return None


def probe_media_file(path: str | Path) -> dict[str, Any]:
    """Probe a downloaded file and return a small metadata dict."""
    target = Path(path)
    result: dict[str, Any] = {
        "size": target.stat().st_size if target.exists() else 0,
        "media_type": sniff_media_type(target),
    }
    suffix = target.suffix.lower()
    if suffix in {".vtt", ".srt", ".ass", ".ssa"}:
        result.update(parse_subtitle_file(target))
        return result
    if result["media_type"] in {"mp4", "m4a"}:
        result.update(parse_mp4_metadata(target))
    if result["media_type"] in {"png", "gif", "jpeg", "webp"}:
        dimensions = _image_dimensions(target)
        if dimensions:
            result["dimensions"] = dimensions
    ffprobe = _probe_with_ffprobe(target)
    if ffprobe:
        result["ffprobe"] = {
            "format": ffprobe.get("format", {}).get("format_name"),
            "duration_seconds": float(
                ffprobe.get("format", {}).get("duration") or 0
            )
            or None,
            "streams": [
                {
                    "codec_type": stream.get("codec_type"),
                    "codec_name": stream.get("codec_name"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "duration_seconds": float(stream.get("duration") or 0) or None,
                }
                for stream in ffprobe.get("streams") or []
            ],
        }
    return result


if __name__ == "__main__":
    print("media_metadata: probe_media_file() / sniff_media_type() helpers")
