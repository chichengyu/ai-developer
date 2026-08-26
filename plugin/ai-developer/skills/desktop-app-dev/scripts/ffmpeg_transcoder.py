"""ffmpeg / ffprobe wrapper with live progress for the desktop UI.

Ships named format presets, GPU encoder auto-detection, smart remux/copy
decisions, and a one-shot CLI in addition to the library API.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_downloader import CancelToken


class TranscodeError(RuntimeError):
    """Raised when ffmpeg exits non-zero."""


@dataclass
class MediaInfo:
    duration_s: float | None
    format_name: str | None
    streams: list[dict]
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int | None = None
    bit_rate: int | None = None


@dataclass
class TranscodeProgress:
    task_id: int | str | None
    stage: str
    percent: float | None
    out_time_s: float | None
    speed: str | None
    fps: float | None = None
    bitrate: str | None = None
    input_size: int | None = None
    output_size: int | None = None
    duration_s: float | None = None
    remaining_s: float | None = None
    frame: int | None = None
    state: str | None = None


@dataclass
class TranscodeOptions:
    video_codec: str = "libx264"
    video_preset: str = "medium"
    crf: int = 23
    audio_codec: str = "aac"
    audio_bitrate: str | None = None
    video_bitrate: str | None = None
    resolution: str | None = None
    fps: str | None = None
    audio_channels: int | None = None
    audio_sample_rate: int | None = None
    faststart: bool = True
    hardware: bool | str = False
    smart_copy: bool = True
    audio_only: bool = False
    extra_args: list[str] | None = None
    start_time: str | None = None
    duration: str | None = None
    threads: int | None = None


TRANSCODE_PROFILES: dict[str, dict[str, Any]] = {
    "mp4": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": True,
    },
    "mp4-hq": {
        "video_codec": "libx264",
        "video_preset": "slow",
        "crf": 18,
        "audio_codec": "aac",
        "faststart": True,
    },
    "hevc": {
        "video_codec": "libx265",
        "video_preset": "medium",
        "crf": 28,
        "audio_codec": "aac",
        "faststart": True,
    },
    "hevc-hq": {
        "video_codec": "libx265",
        "video_preset": "slow",
        "crf": 22,
        "audio_codec": "aac",
        "faststart": True,
    },
    "webm": {
        "video_codec": "libvpx-vp9",
        "video_preset": "good",
        "crf": 32,
        "audio_codec": "libopus",
        "faststart": False,
    },
    "mp3": {
        "audio_only": True,
        "audio_codec": "libmp3lame",
        "audio_bitrate": "192k",
    },
    "m4a": {
        "audio_only": True,
        "audio_codec": "aac",
        "audio_bitrate": "192k",
    },
    "wav": {
        "audio_only": True,
        "audio_codec": "pcm_s16le",
    },
    "flac": {
        "audio_only": True,
        "audio_codec": "flac",
    },
    "avi": {
        "video_codec": "mpeg4",
        "video_preset": "medium",
        "crf": 4,
        "audio_codec": "libmp3lame",
        "audio_bitrate": "192k",
        "faststart": False,
    },
    "ts": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": False,
    },
    "ogg": {
        "video_codec": "libtheora",
        "video_preset": "medium",
        "crf": 10,
        "audio_codec": "libvorbis",
        "audio_bitrate": "192k",
        "faststart": False,
    },
    "opus": {
        "audio_only": True,
        "audio_codec": "libopus",
        "audio_bitrate": "192k",
    },
    "aac": {
        "audio_only": True,
        "audio_codec": "aac",
        "audio_bitrate": "192k",
    },
    "ac3": {
        "audio_only": True,
        "audio_codec": "ac3",
        "audio_bitrate": "384k",
    },
    "gif": {
        "video_codec": "gif",
        "audio_codec": "none",
        "fps": "15",
        "faststart": False,
    },
    "mkv": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": False,
    },
    "mov": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": True,
    },
    "m2ts": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": False,
    },
    "mpeg": {
        "video_codec": "mpeg2video",
        "video_preset": "medium",
        "crf": 4,
        "audio_codec": "mp2",
        "audio_bitrate": "192k",
        "faststart": False,
    },
    "flv": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": False,
    },
    "wmv": {
        "video_codec": "wmv2",
        "video_preset": "medium",
        "crf": 4,
        "audio_codec": "wmav2",
        "audio_bitrate": "192k",
        "faststart": False,
    },
    "m4v": {
        "video_codec": "libx264",
        "video_preset": "medium",
        "crf": 23,
        "audio_codec": "aac",
        "faststart": True,
    },
    "3gp": {
        "video_codec": "h263",
        "video_preset": "medium",
        "crf": 4,
        "audio_codec": "aac",
        "audio_bitrate": "96k",
        "faststart": False,
    },
    "ogv": {
        "video_codec": "libtheora",
        "video_preset": "medium",
        "crf": 10,
        "audio_codec": "libvorbis",
        "audio_bitrate": "192k",
        "faststart": False,
    },
    "vob": {
        "video_codec": "mpeg2video",
        "video_preset": "medium",
        "crf": 4,
        "audio_codec": "ac3",
        "audio_bitrate": "384k",
        "faststart": False,
    },
    "asf": {
        "video_codec": "wmv2",
        "video_preset": "medium",
        "crf": 4,
        "audio_codec": "wmav2",
        "audio_bitrate": "192k",
        "faststart": False,
    },
    "mka": {
        "audio_only": True,
        "audio_codec": "aac",
        "audio_bitrate": "192k",
    },
    "oga": {
        "audio_only": True,
        "audio_codec": "libvorbis",
        "audio_bitrate": "192k",
    },
    "ogg-audio": {
        "audio_only": True,
        "audio_codec": "libvorbis",
        "audio_bitrate": "192k",
    },
    "aiff": {
        "audio_only": True,
        "audio_codec": "pcm_s16be",
    },
    "wma": {
        "audio_only": True,
        "audio_codec": "wmav2",
        "audio_bitrate": "192k",
    },
    "amr": {
        "audio_only": True,
        "audio_codec": "libopencore_amrnb",
        "audio_bitrate": "12.2k",
    },
    "mp2": {
        "audio_only": True,
        "audio_codec": "mp2",
        "audio_bitrate": "192k",
    },
    "dts": {
        "audio_only": True,
        "audio_codec": "dts",
        "audio_bitrate": "768k",
    },
    "eac3": {
        "audio_only": True,
        "audio_codec": "eac3",
        "audio_bitrate": "256k",
    },
    "m4b": {
        "audio_only": True,
        "audio_codec": "aac",
        "audio_bitrate": "128k",
    },
    "alac": {
        "audio_only": True,
        "audio_codec": "alac",
    },
    "jpg": {
        "video_codec": "mjpeg",
        "video_preset": "medium",
        "crf": 3,
        "audio_codec": "none",
        "faststart": False,
    },
    "png": {
        "video_codec": "png",
        "video_preset": "medium",
        "crf": 0,
        "audio_codec": "none",
        "faststart": False,
    },
    "bmp": {
        "video_codec": "bmp",
        "video_preset": "medium",
        "crf": 0,
        "audio_codec": "none",
        "faststart": False,
    },
    "tiff": {
        "video_codec": "tiff",
        "video_preset": "medium",
        "crf": 0,
        "audio_codec": "none",
        "faststart": False,
    },
    "webp": {
        "video_codec": "webp",
        "video_preset": "medium",
        "crf": 75,
        "audio_codec": "none",
        "faststart": False,
    },
    "avif": {
        "video_codec": "libaom-av1",
        "video_preset": "medium",
        "crf": 32,
        "audio_codec": "none",
        "faststart": False,
    },
    "heic": {
        "video_codec": "libx265",
        "video_preset": "medium",
        "crf": 26,
        "audio_codec": "none",
        "faststart": False,
    },
    "jxl": {
        "video_codec": "libjxl",
        "video_preset": "medium",
        "crf": 75,
        "audio_codec": "none",
        "faststart": False,
    },
    "ico": {
        "video_codec": "png",
        "video_preset": "medium",
        "crf": 0,
        "audio_codec": "none",
        "faststart": False,
    },
}

EXTENSION_PROFILE = {
    ".mp4": "mp4",
    ".mkv": "mkv",
    ".webm": "webm",
    ".mov": "mov",
    ".mp3": "mp3",
    ".m4a": "m4a",
    ".wav": "wav",
    ".flac": "flac",
    ".avi": "avi",
    ".ts": "ts",
    ".ogg": "ogg-audio",
    ".opus": "opus",
    ".aac": "aac",
    ".ac3": "ac3",
    ".gif": "gif",
    ".m2ts": "m2ts",
    ".mts": "m2ts",
    ".mpg": "mpeg",
    ".mpeg": "mpeg",
    ".flv": "flv",
    ".wmv": "wmv",
    ".m4v": "m4v",
    ".3gp": "3gp",
    ".ogv": "ogv",
    ".vob": "vob",
    ".asf": "asf",
    ".mka": "mka",
    ".oga": "oga",
    ".aiff": "aiff",
    ".aif": "aiff",
    ".wma": "wma",
    ".amr": "amr",
    ".mp2": "mp2",
    ".dts": "dts",
    ".eac3": "eac3",
    ".m4b": "m4b",
    ".alac": "alac",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".bmp": "bmp",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".webp": "webp",
    ".avif": "avif",
    ".heic": "heic",
    ".heif": "heic",
    ".jxl": "jxl",
    ".ico": "ico",
}

HARDWARE_ENCODER_PRIORITY = {
    "h264": ["h264_nvenc", "h264_amf", "h264_qsv", "h264_videotoolbox"],
    "hevc": ["hevc_nvenc", "hevc_amf", "hevc_qsv", "hevc_videotoolbox"],
    "av1": ["av1_nvenc", "av1_amf", "av1_qsv"],
}


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
    format_data = data.get("format", {})
    duration_text = format_data.get("duration")
    duration = float(duration_text) if duration_text else None
    streams = data.get("streams", [])
    video_codec: str | None = None
    audio_codec: str | None = None
    width: int | None = None
    height: int | None = None
    for stream in streams:
        codec_type = stream.get("codec_type")
        if codec_type == "video" and video_codec is None:
            video_codec = stream.get("codec_name")
            width = int(stream.get("width") or 0) or None
            height = int(stream.get("height") or 0) or None
        elif codec_type == "audio" and audio_codec is None:
            audio_codec = stream.get("codec_name")
    size_text = format_data.get("size")
    size_bytes = int(float(size_text)) if size_text else None
    bit_rate_text = format_data.get("bit_rate")
    bit_rate = int(bit_rate_text) if bit_rate_text and bit_rate_text.isdigit() else None
    return MediaInfo(
        duration_s=duration,
        format_name=format_data.get("format_name"),
        streams=streams,
        video_codec=video_codec,
        audio_codec=audio_codec,
        width=width,
        height=height,
        size_bytes=size_bytes,
        bit_rate=bit_rate,
    )


def parse_encoder_list(text: str) -> set[str]:
    """Extract encoder names from `ffmpeg -encoders` output."""
    encoders: set[str] = set()
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[VA]\.\.\.\.\.", parts[0]):
            encoders.add(parts[1].split()[0])
    return encoders


def detect_encoders(ffmpeg_path: str = "ffmpeg") -> set[str]:
    """Return encoder names reported by the installed ffmpeg."""
    result = subprocess.run(
        [ffmpeg_path, "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return parse_encoder_list(result.stdout + "\n" + result.stderr)


def select_hardware_encoder(
    desired: str,
    encoders: set[str],
    prefer: str | None = None,
) -> str | None:
    """Pick a GPU encoder by family, optionally preferring a named encoder."""
    candidates = HARDWARE_ENCODER_PRIORITY.get(desired, [])
    if prefer:
        if prefer in encoders:
            return prefer
        for candidate in candidates:
            if prefer in candidate and candidate in encoders:
                return candidate
        return None
    for candidate in candidates:
        if candidate in encoders:
            return candidate
    return None


def _codec_family(codec: str) -> str:
    normalized = codec.lower()
    h264 = {
        "h264",
        "libx264",
        "h264_nvenc",
        "h264_amf",
        "h264_qsv",
        "h264_videotoolbox",
    }
    hevc = {
        "hevc",
        "h265",
        "libx265",
        "hevc_nvenc",
        "hevc_amf",
        "hevc_qsv",
        "hevc_videotoolbox",
    }
    av1 = {"av1", "libaom-av1", "av1_nvenc", "av1_amf", "av1_qsv"}
    if normalized in h264:
        return "h264"
    if normalized in hevc:
        return "hevc"
    if normalized in av1:
        return "av1"
    if normalized in {"vp9", "libvpx-vp9"}:
        return "vp9"
    if normalized in {"vp8", "libvpx"}:
        return "vp8"
    if normalized in {"aac", "libfdk_aac"}:
        return "aac"
    if normalized in {"mp3", "libmp3lame"}:
        return "mp3"
    return normalized


def _container_accepts_codec(extension: str, codec: str) -> bool:
    if extension in (".mp4", ".m4a", ".mov", ".m4v", ".m4b"):
        return codec in {
            "h264",
            "libx264",
            "hevc",
            "h265",
            "libx265",
            "av1",
            "libaom-av1",
            "libsvtav1",
            "mpeg4",
            "mjpeg",
            "aac",
            "libfdk_aac",
            "mp3",
            "libmp3lame",
            "ac3",
            "eac3",
            "opus",
            "libopus",
            "flac",
            "alac",
            "mp2",
            "pcm_s16le",
            "pcm_s16be",
            "pcm_s24le",
        }
    if extension == ".mkv":
        return True
    if extension == ".avi":
        return codec in {
            "h264",
            "libx264",
            "mpeg4",
            "mjpeg",
            "mp3",
            "libmp3lame",
            "aac",
            "ac3",
        } or codec.startswith("pcm_")
    if extension in (".ts", ".m2ts", ".mts"):
        return codec in {
            "h264",
            "libx264",
            "hevc",
            "libx265",
            "mpeg2video",
            "aac",
            "ac3",
            "eac3",
            "dts",
            "mp3",
            "libmp3lame",
            "opus",
            "libopus",
        }
    if extension == ".webm":
        return codec in {
            "vp8",
            "libvpx",
            "vp9",
            "libvpx-vp9",
            "av1",
            "libaom-av1",
            "libsvtav1",
            "opus",
            "libopus",
            "vorbis",
            "libvorbis",
        }
    if extension == ".ogg":
        return codec in {"theora", "vorbis", "libvorbis", "opus", "libopus", "flac"}
    if extension == ".ogv":
        return codec in {"theora", "vorbis", "libvorbis", "opus", "libopus"}
    if extension == ".mka":
        return True
    if extension == ".oga":
        return codec in {"vorbis", "libvorbis", "opus", "libopus", "flac"}
    if extension == ".mp3":
        return codec in {"mp3", "libmp3lame"}
    if extension == ".flac":
        return codec == "flac"
    if extension == ".wav":
        return codec.startswith("pcm_")
    if extension == ".opus":
        return codec in {"opus", "libopus"}
    if extension == ".aac":
        return codec in {"aac", "libfdk_aac"}
    if extension == ".ac3":
        return codec == "ac3"
    if extension == ".eac3":
        return codec == "eac3"
    if extension == ".aiff" or extension == ".aif":
        return codec in {"pcm_s16be", "pcm_s16le", "pcm_s24be", "pcm_s24le"}
    if extension == ".wma":
        return codec == "wmav2"
    if extension == ".amr":
        return codec in {"amr_nb", "libopencore_amrnb"}
    if extension == ".mp2":
        return codec == "mp2"
    if extension == ".dts":
        return codec == "dts"
    if extension == ".alac":
        return codec == "alac"
    if extension == ".flv":
        return codec in {
            "h264",
            "libx264",
            "aac",
            "mp3",
            "libmp3lame",
        }
    if extension in (".wmv", ".asf"):
        return codec in {"wmv2", "wmav2"}
    if extension in (".mpg", ".mpeg"):
        return codec in {"mpeg2video", "mp2", "ac3"}
    if extension == ".3gp":
        return codec in {"h263", "h264", "libx264", "aac", "amr_nb", "libopencore_amrnb"}
    if extension == ".vob":
        return codec in {"mpeg2video", "mp2", "ac3"}
    if extension == ".gif":
        return codec == "gif"
    if extension in (".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"):
        return codec in {
            "mjpeg",
            "png",
            "bmp",
            "tiff",
            "webp",
        }
    if extension in (".avif",):
        return codec in {"av1", "libaom-av1", "libsvtav1"}
    if extension in (".heic", ".heif"):
        return codec in {"hevc", "libx265"}
    if extension == ".jxl":
        return codec == "libjxl"
    if extension == ".ico":
        return codec == "png"
    return False


def _decide_copy(
    info: MediaInfo,
    dst: Path,
    options: TranscodeOptions,
    video_codec: str,
) -> tuple[bool, bool]:
    """Return (copy_video, copy_audio) when the source can be remuxed."""
    extension = dst.suffix.lower()
    copy_video = False
    copy_audio = False
    if (
        not options.audio_only
        and not options.resolution
        and not options.fps
        and not options.video_bitrate
        and info.video_codec
        and _container_accepts_codec(extension, info.video_codec)
        and _codec_family(info.video_codec) == _codec_family(video_codec)
    ):
        copy_video = True
    if (
        info.audio_codec
        and _container_accepts_codec(extension, info.audio_codec)
        and (options.audio_only or copy_video)
    ):
        requested = options.audio_codec
        if requested in (None, "copy") or _codec_family(requested) == _codec_family(
            info.audio_codec
        ):
            copy_audio = True
    return copy_video, copy_audio


def _video_args(video_codec: str, options: TranscodeOptions) -> list[str]:
    args = ["-c:v", video_codec]
    if "nvenc" in video_codec:
        args += ["-preset", "p4", "-cq", str(options.crf)]
    elif "qsv" in video_codec:
        args += ["-global_quality", str(options.crf)]
    elif "amf" in video_codec:
        args += ["-quality", "balanced", "-qp_i", str(options.crf), "-qp_p", str(options.crf)]
    elif "videotoolbox" in video_codec:
        args += ["-q:v", str(options.crf)]
    elif video_codec in ("libx264", "libx265"):
        args += ["-preset", options.video_preset, "-crf", str(options.crf)]
    elif video_codec == "mpeg4":
        args += ["-q:v", str(options.crf)]
    elif video_codec in ("libvpx", "libvpx-vp9"):
        args += ["-deadline", options.video_preset, "-cpu-used", "5", "-crf", str(options.crf)]
    elif video_codec in ("mpeg2video", "wmv2", "h263", "libtheora", "mjpeg"):
        args += ["-q:v", str(options.crf)]
    elif video_codec in ("png", "bmp", "tiff"):
        args += ["-compression_level", "6"]
    elif video_codec == "webp":
        args += ["-quality", str(max(0, min(100, options.crf))), "-compression_level", "6"]
    elif video_codec in ("libaom-av1", "libsvtav1"):
        args += ["-crf", str(options.crf), "-b:v", "0", "-strict", "experimental"]
    elif video_codec == "libjxl":
        args += ["-quality", str(max(0, min(100, options.crf)))]
    elif video_codec == "gif":
        args += ["-loop", "0"]
    else:
        args += ["-crf", str(options.crf)]
    if options.video_bitrate:
        args += ["-b:v", options.video_bitrate]
    if options.resolution:
        args += ["-vf", f"scale={options.resolution}"]
    if options.fps:
        args += ["-r", str(options.fps)]
    return args


def _audio_args(options: TranscodeOptions) -> list[str]:
    args = ["-c:a", options.audio_codec]
    if options.audio_bitrate:
        args += ["-b:a", options.audio_bitrate]
    if options.audio_channels:
        args += ["-ac", str(options.audio_channels)]
    if options.audio_sample_rate:
        args += ["-ar", str(options.audio_sample_rate)]
    return args


def build_ffmpeg_args(
    src: str | Path,
    dst: str | Path,
    options: TranscodeOptions | None = None,
    ffmpeg_path: str = "ffmpeg",
    info: MediaInfo | None = None,
    encoders: set[str] | None = None,
) -> list[str]:
    """Build an ffmpeg command line without running it."""
    options = options or TranscodeOptions()
    if encoders is None:
        encoders = set()
    src_path = Path(src)
    dst_path = Path(dst)
    args = [
        ffmpeg_path,
        "-y",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        str(src_path),
    ]
    if options.start_time:
        args += ["-ss", options.start_time]
    if options.duration:
        args += ["-t", options.duration]
    if options.threads:
        args += ["-threads", str(options.threads)]
    video_codec = options.video_codec
    if options.hardware:
        desired = _codec_family(video_codec) or "h264"
        selected = select_hardware_encoder(
            desired,
            set(encoders),
            prefer=options.hardware if isinstance(options.hardware, str) else None,
        )
        if selected is not None:
            video_codec = selected
        elif isinstance(options.hardware, str):
            raise TranscodeError(f"hardware encoder not found: {options.hardware}")

    copy_video, copy_audio = (
        _decide_copy(info, dst_path, options, video_codec)
        if options.smart_copy and info is not None
        else (False, False)
    )
    if options.audio_only:
        args += ["-vn"]
        if copy_audio:
            args += ["-c:a", "copy"]
        else:
            args += _audio_args(options)
    else:
        if copy_video:
            args += ["-c:v", "copy"]
        else:
            args += _video_args(video_codec, options)
        if copy_audio:
            args += ["-c:a", "copy"]
        elif options.audio_codec != "none":
            args += _audio_args(options)
    if dst_path.suffix.lower() in {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tiff",
        ".tif",
        ".webp",
        ".avif",
        ".heic",
        ".heif",
        ".jxl",
        ".ico",
    }:
        args += ["-frames:v", "1"]
    if options.faststart and dst_path.suffix.lower() in (".mp4", ".mov", ".m4a"):
        args += ["-movflags", "+faststart"]
    if options.extra_args:
        args.extend(options.extra_args)
    args.append(str(dst_path))
    return args


def _options_from_args(
    dst: str | Path,
    profile: str | None,
    video_codec: str,
    video_preset: str,
    crf: int,
    audio_codec: str,
    extra_args: list[str] | None,
    hardware: bool | str,
    smart_copy: bool,
    audio_bitrate: str | None,
    video_bitrate: str | None,
    resolution: str | None,
    fps: str | None,
    audio_channels: int | None,
    audio_sample_rate: int | None,
    faststart: bool,
    audio_only: bool,
    start_time: str | None,
    duration: str | None,
    threads: int | None,
) -> TranscodeOptions:
    options = TranscodeOptions(
        video_codec=video_codec,
        video_preset=video_preset,
        crf=crf,
        audio_codec=audio_codec,
        extra_args=extra_args,
        hardware=hardware,
        smart_copy=smart_copy,
        audio_bitrate=audio_bitrate,
        video_bitrate=video_bitrate,
        resolution=resolution,
        fps=fps,
        audio_channels=audio_channels,
        audio_sample_rate=audio_sample_rate,
        faststart=faststart,
        audio_only=audio_only,
        start_time=start_time,
        duration=duration,
        threads=threads,
    )
    profile = profile or EXTENSION_PROFILE.get(Path(dst).suffix.lower())
    if not profile:
        return options
    if profile not in TRANSCODE_PROFILES:
        raise TranscodeError(f"unknown transcode profile: {profile}")
    values = TRANSCODE_PROFILES[profile]
    for key, value in values.items():
        if key == "video_codec" and video_codec == "libx264":
            options.video_codec = value
        elif key == "video_preset" and video_preset == "medium":
            options.video_preset = value
        elif key == "crf" and crf == 23:
            options.crf = value
        elif key == "audio_codec" and audio_codec == "aac":
            options.audio_codec = value
        elif key == "faststart" and faststart is True:
            options.faststart = value
        elif key == "audio_only":
            options.audio_only = value
        elif key == "fps" and fps is None:
            options.fps = value
        elif key == "audio_bitrate" and audio_bitrate is None:
            options.audio_bitrate = value
    return options


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
    *,
    profile: str | None = None,
    hardware: bool | str = False,
    smart_copy: bool = True,
    audio_bitrate: str | None = None,
    video_bitrate: str | None = None,
    resolution: str | None = None,
    fps: str | None = None,
    audio_channels: int | None = None,
    audio_sample_rate: int | None = None,
    faststart: bool = True,
    audio_only: bool = False,
    start_time: str | None = None,
    duration: str | None = None,
    threads: int | None = None,
) -> Path:
    """Transcode a media file and emit progress from ffmpeg -progress."""
    if not shutil.which(ffmpeg_path):
        raise TranscodeError("ffmpeg not found on PATH")
    src_path = Path(src)
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    info = probe_media(src_path, ffprobe_path=ffprobe_path)
    source_duration = info.duration_s if info else None
    options = _options_from_args(
        dst_path,
        profile,
        video_codec,
        video_preset,
        crf,
        audio_codec,
        extra_args,
        hardware,
        smart_copy,
        audio_bitrate,
        video_bitrate,
        resolution,
        fps,
        audio_channels,
        audio_sample_rate,
        faststart,
        audio_only,
        start_time,
        duration,
        threads,
    )
    encoders = detect_encoders(ffmpeg_path) if hardware else set()
    args = build_ffmpeg_args(
        src_path,
        dst_path,
        options,
        ffmpeg_path=ffmpeg_path,
        info=info,
        encoders=encoders,
    )

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
    progress_fps: float | None = None
    bitrate: str | None = None
    output_size: int | None = None
    frame: int | None = None
    progress_state: str | None = None
    if process.stdout is not None:
        for line in process.stdout:
            if cancel and cancel.cancelled:
                process.kill()
                raise TranscodeError("transcode cancelled")
            key, _, value = line.strip().partition("=")
            if (key == "out_time_ms" or (key == "out_time_us" and out_time is None)) and value:
                with suppress(ValueError):
                    out_time = int(value) / 1_000_000
            elif key == "speed":
                speed = value
            elif key == "fps" and value:
                with suppress(ValueError):
                    progress_fps = float(value)
            elif key == "bitrate":
                bitrate = value
            elif key == "total_size" and value.isdigit():
                output_size = int(value)
            elif key == "frame" and value.isdigit():
                frame = int(value)
            elif key == "progress":
                progress_state = value
            if progress:
                percent = None
                if source_duration and out_time is not None:
                    percent = min(1.0, out_time / source_duration)
                progress(
                    TranscodeProgress(
                        task_id=task_id,
                        stage="transcode",
                        percent=percent,
                        out_time_s=out_time,
                        speed=speed,
                        fps=progress_fps,
                        bitrate=bitrate,
                        input_size=info.size_bytes if info else None,
                        output_size=output_size,
                        duration_s=source_duration,
                        remaining_s=(
                            max(0.0, source_duration - out_time)
                            if source_duration is not None and out_time is not None
                            else None
                        ),
                        frame=frame,
                        state=progress_state,
                    )
                )

    process.wait()
    thread.join()
    if process.returncode != 0:
        raise TranscodeError("".join(stderr_lines)[-1000:])
    if progress:
        progress(
            TranscodeProgress(
                task_id=task_id,
                stage="finalize",
                percent=1.0,
                out_time_s=source_duration if source_duration is not None else out_time,
                speed=speed,
                fps=progress_fps,
                bitrate=bitrate,
                input_size=info.size_bytes if info else None,
                output_size=dst_path.stat().st_size if dst_path.exists() else output_size,
                duration_s=source_duration,
                remaining_s=0.0 if source_duration is not None else None,
                frame=frame,
                state="end",
            )
        )
    return dst_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Transcode media with named format presets and optional GPU acceleration"
    )
    parser.add_argument("src", nargs="?", help="input media file")
    parser.add_argument("dst", nargs="?", help="output media file")
    parser.add_argument(
        "--profile",
        choices=sorted(TRANSCODE_PROFILES),
        help="named format preset",
    )
    parser.add_argument(
        "--hardware",
        nargs="?",
        const=True,
        default=False,
        help="prefer a GPU encoder (optionally by exact name)",
    )
    parser.add_argument("--no-smart-copy", action="store_true")
    parser.add_argument("--video-codec", default=None)
    parser.add_argument("--video-preset", default=None)
    parser.add_argument("--crf", type=int, default=None)
    parser.add_argument("--audio-codec", default=None)
    parser.add_argument("--audio-bitrate", default=None)
    parser.add_argument("--video-bitrate", default=None)
    parser.add_argument("--resolution", default=None)
    parser.add_argument("--fps", default=None)
    parser.add_argument("--start", default=None, help="start time passed to ffmpeg, e.g. 00:01:30")
    parser.add_argument("--duration", default=None, help="clip duration passed to ffmpeg, e.g. 120")
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--audio-channels", type=int, default=None)
    parser.add_argument("--audio-sample-rate", type=int, default=None)
    parser.add_argument("--list-profiles", action="store_true")
    args = parser.parse_args(argv)
    if args.list_profiles:
        for name, values in TRANSCODE_PROFILES.items():
            print(f"{name}: {json.dumps(values, ensure_ascii=False)}")
        return 0
    if not args.src or not args.dst:
        parser.error("src and dst are required unless --list-profiles is used")
    kwargs: dict[str, Any] = {}
    for key in (
        "profile",
        "video_codec",
        "video_preset",
        "crf",
        "audio_codec",
        "audio_bitrate",
        "video_bitrate",
        "resolution",
        "fps",
        "start_time",
        "duration",
        "threads",
        "audio_channels",
        "audio_sample_rate",
    ):
        value = getattr(args, "start" if key == "start_time" else key)
        if value is not None:
            kwargs[key] = value
    if args.no_smart_copy:
        kwargs["smart_copy"] = False
    transcode_file(
        args.src,
        args.dst,
        hardware=args.hardware,
        **kwargs,
    )
    print(f"transcoded: {args.src} -> {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
