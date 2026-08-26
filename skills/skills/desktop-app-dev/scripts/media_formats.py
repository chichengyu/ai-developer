"""Unified format registry for the media pipeline.

The catalog covers the common audio, video, image, subtitle, document,
data, and archive targets used by desktop media tools. Every entry
declares which engine can produce it: ffmpeg, the Python standard
library, a byte-for-byte copy, or an optional external tool.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FormatSpec:
    extension: str
    category: str
    label: str
    engine: str = "ffmpeg"
    profile: str | None = None
    mime: str | None = None
    note: str = ""


CATEGORY_LABELS = {
    "video": "Video",
    "audio": "Audio",
    "image": "Image",
    "subtitle": "Subtitle",
    "document": "Document",
    "data": "Data",
    "archive": "Archive",
}


def _f(
    extension: str,
    category: str,
    label: str,
    *,
    engine: str = "ffmpeg",
    profile: str | None = None,
    mime: str | None = None,
    note: str = "",
) -> FormatSpec:
    return FormatSpec(
        extension=extension,
        category=category,
        label=label,
        engine=engine,
        profile=profile,
        mime=mime,
        note=note,
    )


FORMAT_CATALOG: list[FormatSpec] = [
    # Video
    _f("mp4", "video", "MPEG-4 Part 14", profile="mp4", mime="video/mp4"),
    _f("mkv", "video", "Matroska", profile="mkv", mime="video/x-matroska"),
    _f("webm", "video", "WebM", profile="webm", mime="video/webm"),
    _f("mov", "video", "QuickTime", profile="mov", mime="video/quicktime"),
    _f("avi", "video", "AVI", profile="avi", mime="video/x-msvideo"),
    _f("ts", "video", "MPEG-TS", profile="ts", mime="video/mp2t"),
    _f("m2ts", "video", "Blu-ray MPEG-TS", profile="m2ts", mime="video/mp2t"),
    _f("mts", "video", "AVCHD MPEG-TS", profile="m2ts", mime="video/mp2t"),
    _f("mpg", "video", "MPEG Program Stream", profile="mpeg", mime="video/mpeg"),
    _f("mpeg", "video", "MPEG Program Stream", profile="mpeg", mime="video/mpeg"),
    _f("flv", "video", "Flash Video", profile="flv", mime="video/x-flv"),
    _f("wmv", "video", "Windows Media Video", profile="wmv", mime="video/x-ms-wmv"),
    _f("m4v", "video", "iTunes Video", profile="m4v", mime="video/x-m4v"),
    _f("3gp", "video", "3GPP", profile="3gp", mime="video/3gpp"),
    _f("ogv", "video", "Ogg Video", profile="ogv", mime="video/ogg"),
    _f("vob", "video", "DVD VOB", profile="vob", mime="video/dvd"),
    _f("asf", "video", "Advanced Systems Format", profile="asf", mime="video/x-ms-asf"),
    _f(
        "rmvb",
        "video",
        "RealMedia Variable Bitrate",
        engine="optional",
        mime="application/vnd.rn-realmedia-vbr",
        note="requires an ffmpeg build with RealMedia muxing support",
    ),
    _f(
        "mxf",
        "video",
        "Material Exchange Format",
        engine="optional",
        mime="application/mxf",
        note="depends on ffmpeg mxf muxer availability",
    ),
    # Audio
    _f("mp3", "audio", "MPEG Layer 3", profile="mp3", mime="audio/mpeg"),
    _f("m4a", "audio", "MPEG-4 Audio", profile="m4a", mime="audio/mp4"),
    _f("m4b", "audio", "Audiobook MPEG-4", profile="m4b", mime="audio/mp4"),
    _f("aac", "audio", "AAC", profile="aac", mime="audio/aac"),
    _f("ac3", "audio", "Dolby Digital", profile="ac3", mime="audio/ac3"),
    _f("eac3", "audio", "Dolby Digital Plus", profile="eac3", mime="audio/eac3"),
    _f("wav", "audio", "Waveform Audio", profile="wav", mime="audio/wav"),
    _f("flac", "audio", "FLAC", profile="flac", mime="audio/flac"),
    _f("ogg", "audio", "Ogg Audio", profile="ogg-audio", mime="audio/ogg"),
    _f("oga", "audio", "Ogg Audio", profile="oga", mime="audio/ogg"),
    _f("opus", "audio", "Opus", profile="opus", mime="audio/opus"),
    _f("aiff", "audio", "AIFF", profile="aiff", mime="audio/aiff"),
    _f("aif", "audio", "AIFF", profile="aiff", mime="audio/aiff"),
    _f("wma", "audio", "Windows Media Audio", profile="wma", mime="audio/x-ms-wma"),
    _f("mka", "audio", "Matroska Audio", profile="mka", mime="audio/x-matroska"),
    _f("amr", "audio", "Adaptive Multi-Rate", profile="amr", mime="audio/amr"),
    _f("mp2", "audio", "MPEG Layer 2", profile="mp2", mime="audio/mpeg"),
    _f("dts", "audio", "DTS", profile="dts", mime="audio/vnd.dts"),
    _f(
        "alac",
        "audio",
        "Apple Lossless",
        engine="optional",
        mime="audio/mp4",
        note="ALAC is a codec; prefer an m4a container for output",
    ),
    _f(
        "ape",
        "audio",
        "Monkey's Audio",
        engine="optional",
        mime="audio/x-ape",
        note="requires ffmpeg ape decoder/encoder availability",
    ),
    _f(
        "spx",
        "audio",
        "Speex",
        engine="optional",
        mime="audio/x-speex",
        note="requires ffmpeg speex encoder availability",
    ),
    _f(
        "caf",
        "audio",
        "Core Audio Format",
        engine="optional",
        mime="audio/x-caf",
        note="requires ffmpeg caf muxer availability",
    ),
    # Image
    _f("jpg", "image", "JPEG", profile="jpg", mime="image/jpeg"),
    _f("jpeg", "image", "JPEG", profile="jpg", mime="image/jpeg"),
    _f("png", "image", "PNG", profile="png", mime="image/png"),
    _f("webp", "image", "WebP", profile="webp", mime="image/webp"),
    _f("gif", "image", "GIF", profile="gif", mime="image/gif"),
    _f("bmp", "image", "BMP", profile="bmp", mime="image/bmp"),
    _f("tiff", "image", "TIFF", profile="tiff", mime="image/tiff"),
    _f("tif", "image", "TIFF", profile="tiff", mime="image/tiff"),
    _f("avif", "image", "AVIF", profile="avif", mime="image/avif"),
    _f(
        "heic",
        "image",
        "HEIC",
        engine="optional",
        profile="heic",
        mime="image/heic",
        note="requires ffmpeg built with libx265 + HEIF support",
    ),
    _f(
        "heif",
        "image",
        "HEIF",
        engine="optional",
        profile="heic",
        mime="image/heif",
        note="requires ffmpeg built with libx265 + HEIF support",
    ),
    _f(
        "jxl",
        "image",
        "JPEG XL",
        engine="optional",
        profile="jxl",
        mime="image/jxl",
        note="requires ffmpeg built with libjxl",
    ),
    _f(
        "ico",
        "image",
        "Windows Icon",
        engine="optional",
        profile="ico",
        mime="image/x-icon",
        note="requires ffmpeg ico muxer availability",
    ),
    _f(
        "tga",
        "image",
        "Targa",
        engine="optional",
        mime="image/x-tga",
        note="requires ffmpeg targa encoder availability",
    ),
    _f("svg", "image", "SVG", engine="copy", mime="image/svg+xml"),
    # Subtitle
    _f("srt", "subtitle", "SubRip", engine="stdlib"),
    _f("vtt", "subtitle", "WebVTT", engine="stdlib"),
    _f("ass", "subtitle", "ASS", engine="stdlib"),
    _f("ssa", "subtitle", "SSA", engine="stdlib"),
    _f("sub", "subtitle", "MicroDVD / SubViewer", engine="copy"),
    _f("ttml", "subtitle", "TTML", engine="copy"),
    _f("mpl2", "subtitle", "MPL2", engine="copy"),
    # Document / text
    _f("txt", "document", "Plain text", engine="stdlib", mime="text/plain"),
    _f("md", "document", "Markdown", engine="stdlib", mime="text/markdown"),
    _f("html", "document", "HTML", engine="stdlib", mime="text/html"),
    _f("log", "document", "Log file", engine="copy", mime="text/plain"),
    _f("rtf", "document", "Rich Text", engine="optional", mime="application/rtf"),
    _f(
        "pdf",
        "document",
        "PDF",
        engine="optional",
        mime="application/pdf",
        note="uses pandoc / LibreOffice / Ghostscript when installed",
    ),
    _f(
        "epub",
        "document",
        "EPUB",
        engine="optional",
        mime="application/epub+zip",
        note="uses pandoc / Calibre when installed",
    ),
    _f(
        "mobi",
        "document",
        "Mobipocket",
        engine="optional",
        mime="application/x-mobipocket-ebook",
        note="uses Calibre when installed",
    ),
    _f(
        "docx",
        "document",
        "Word document",
        engine="optional",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        note="uses LibreOffice / pandoc when installed",
    ),
    _f(
        "xlsx",
        "document",
        "Excel workbook",
        engine="optional",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        note="uses LibreOffice when installed",
    ),
    _f(
        "pptx",
        "document",
        "PowerPoint",
        engine="optional",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        note="uses LibreOffice when installed",
    ),
    _f(
        "odt",
        "document",
        "OpenDocument Text",
        engine="optional",
        mime="application/vnd.oasis.opendocument.text",
        note="uses LibreOffice / pandoc when installed",
    ),
    # Data
    _f("json", "data", "JSON", engine="stdlib", mime="application/json"),
    _f("jsonl", "data", "JSON Lines", engine="stdlib", mime="application/x-ndjson"),
    _f("csv", "data", "CSV", engine="stdlib", mime="text/csv"),
    _f("xml", "data", "XML", engine="stdlib", mime="application/xml"),
    _f("ini", "data", "INI", engine="stdlib", mime="text/plain"),
    _f(
        "yaml",
        "data",
        "YAML",
        engine="optional",
        mime="application/yaml",
        note="requires PyYAML when converting",
    ),
    _f(
        "yml",
        "data",
        "YAML",
        engine="optional",
        mime="application/yaml",
        note="requires PyYAML when converting",
    ),
    _f(
        "toml",
        "data",
        "TOML",
        engine="optional",
        mime="application/toml",
        note="requires tomli-w when converting",
    ),
    # Archive
    _f("zip", "archive", "ZIP", engine="stdlib", mime="application/zip"),
    _f("tar", "archive", "TAR", engine="stdlib", mime="application/x-tar"),
    _f("gz", "archive", "Gzip TAR", engine="stdlib", mime="application/gzip"),
    _f("bz2", "archive", "Bzip2 TAR", engine="stdlib", mime="application/x-bzip2"),
    _f("xz", "archive", "XZ TAR", engine="stdlib", mime="application/x-xz"),
    _f(
        "7z",
        "archive",
        "7-Zip",
        engine="optional",
        mime="application/x-7z-compressed",
        note="requires 7z executable when converting",
    ),
    _f(
        "rar",
        "archive",
        "RAR",
        engine="optional",
        mime="application/vnd.rar",
        note="requires 7z / unrar executable when converting",
    ),
]


def _index_by_extension() -> dict[str, FormatSpec]:
    index: dict[str, FormatSpec] = {}
    for spec in FORMAT_CATALOG:
        index.setdefault(spec.extension, spec)
    return index


_BY_EXTENSION = _index_by_extension()


def lookup_format(extension: str) -> FormatSpec | None:
    """Return the catalog entry for an extension, with or without a dot."""
    return _BY_EXTENSION.get(extension.lower().lstrip("."))


def formats_by_category(category: str | None = None) -> list[FormatSpec]:
    """Return catalog entries, optionally filtered by category."""
    if category:
        return [spec for spec in FORMAT_CATALOG if spec.category == category]
    return list(FORMAT_CATALOG)


def categories() -> list[str]:
    """Return category names in catalog order."""
    seen: list[str] = []
    for spec in FORMAT_CATALOG:
        if spec.category not in seen:
            seen.append(spec.category)
    return seen


def engine_targets(engine: str) -> list[FormatSpec]:
    """Return formats that a given engine can produce."""
    return [spec for spec in FORMAT_CATALOG if spec.engine == engine]


def catalog_payload() -> dict[str, Any]:
    """Return a JSON-serializable catalog for the sidecar."""
    return {
        "count": len(FORMAT_CATALOG),
        "categories": [
            {"id": category, "label": CATEGORY_LABELS.get(category, category)}
            for category in categories()
        ],
        "formats": [asdict(spec) for spec in FORMAT_CATALOG],
    }


def infer_category(path: str | Path) -> str | None:
    """Infer a file category from its extension."""
    spec = lookup_format(Path(path).suffix)
    return spec.category if spec else None


def list_formats(category: str | None = None, json_output: bool = False) -> str:
    """Render the catalog for the CLI."""
    if json_output:
        return json.dumps(catalog_payload(), ensure_ascii=False, indent=2)
    lines: list[str] = []
    for current in categories():
        if category and current != category:
            continue
        lines.append(f"{CATEGORY_LABELS.get(current, current)}")
        for spec in formats_by_category(current):
            profile = f", profile={spec.profile}" if spec.profile else ""
            note = f" -- {spec.note}" if spec.note else ""
            lines.append(f"  .{spec.extension:<8} {spec.engine:<8}{profile}{note}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the unified media format catalog")
    parser.add_argument("--list", nargs="?", const="", default=None, metavar="CATEGORY")
    parser.add_argument("--lookup", metavar="EXT")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.lookup:
        spec = lookup_format(args.lookup)
        if spec is None:
            print(f"unknown format: {args.lookup}")
            return 1
        print(json.dumps(asdict(spec), ensure_ascii=False, indent=2))
        return 0
    print(list_formats(args.list or None, json_output=args.json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
