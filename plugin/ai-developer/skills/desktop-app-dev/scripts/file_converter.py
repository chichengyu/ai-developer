"""Generic file conversion engine for the media pipeline.

Dispatches to ffmpeg for media/image formats, to the Python standard
library for text/data/subtitle/archive formats, and reports a clear
unavailable error when an optional external tool would be required.
"""

from __future__ import annotations

import argparse
import configparser
import csv
import html
import io
import json
import re
import shutil
import tarfile
import time
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from media_downloader import CancelToken
from media_formats import lookup_format


class ConversionError(RuntimeError):
    """Raised when a file cannot be converted."""


class ConversionUnavailable(ConversionError):
    """Raised when the target format needs an optional external tool."""


@dataclass
class ConvertProgress:
    task_id: int | str | None
    stage: str
    percent: float | None
    input_size: int
    output_size: int
    current: str | None = None
    done: int = 0
    total: int = 1
    elapsed_s: float = 0.0


@dataclass
class ConvertResult:
    path: Path
    engine: str
    input_size: int
    output_size: int
    elapsed_s: float = 0.0


@dataclass
class BatchConvertProgress:
    task_id: int | str | None
    stage: str
    percent: float | None
    done: int
    total: int
    input_bytes_done: int
    total_input_bytes: int
    output_bytes: int
    current: str | None = None
    elapsed_s: float = 0.0


ProgressFn = Callable[[ConvertProgress], None] | None
BatchProgressFn = Callable[[BatchConvertProgress], None] | None


def _read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8"


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _markdown_to_html(text: str) -> str:
    lines = text.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            escaped = " ".join(paragraph)
            escaped = html.escape(escaped)
            escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
            escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
            output.append(f"<p>{escaped}</p>")
            paragraph.clear()

    for line in lines:
        if line.strip().startswith("```"):
            flush_paragraph()
            if in_code:
                output.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines.clear()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
        elif stripped.startswith("### "):
            flush_paragraph()
            output.append(f"<h3>{html.escape(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            flush_paragraph()
            output.append(f"<h2>{html.escape(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            flush_paragraph()
            output.append(f"<h1>{html.escape(stripped[2:])}</h1>")
        elif re.match(r"^\s*[-*]\s+", stripped):
            flush_paragraph()
            output.append(f"<li>{html.escape(re.sub(r'^[-*]\\s+', '', stripped))}</li>")
        elif re.match(r"^\s*\d+\.\s+", stripped):
            flush_paragraph()
            output.append(f"<li>{html.escape(re.sub(r'^\\d+\\.\\s+', '', stripped))}</li>")
        else:
            paragraph.append(stripped)
    flush_paragraph()
    if in_code:
        output.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    return "<html><body>" + "".join(output) + "</body></html>"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _html_to_text(text: str) -> str:
    parser = _TextExtractor()
    parser.feed(text)
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def _json_to_csv(value: Any) -> str:
    rows = value if isinstance(value, list) else [value]
    if not rows:
        return ""
    keys: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            for key in row:
                if key not in keys:
                    keys.append(key)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=keys)
    writer.writeheader()
    for row in rows:
        if isinstance(row, dict):
            writer.writerow({key: row.get(key, "") for key in keys})
        else:
            writer.writerow({keys[0]: row} if keys else {})
    return buffer.getvalue()


def _csv_to_json(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _json_to_jsonl(value: Any) -> str:
    rows = value if isinstance(value, list) else [value]
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def _jsonl_to_json(text: str) -> list[Any]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _xml_to_json(text: str) -> dict[str, Any]:
    import xml.etree.ElementTree as ET

    root = ET.fromstring(text)

    def convert(node: Any) -> Any:
        if len(node) == 0:
            return node.text or ""
        children: list[Any] = []
        for child in node:
            children.append(convert(child))
        return children if len(children) > 1 else children[0]

    return {root.tag: convert(root)}


def _ini_to_json(text: str) -> dict[str, dict[str, str]]:
    parser = configparser.ConfigParser()
    parser.read_string(text)
    return {section: dict(parser.items(section)) for section in parser.sections()}


def _convert_text_file(src: Path, dst: Path, src_ext: str, dst_ext: str) -> str:
    text, _ = _read_text(src)
    if src_ext == dst_ext:
        _write_text(dst, text)
        return "copy"
    if src_ext == "md" and dst_ext == "html":
        _write_text(dst, _markdown_to_html(text))
    elif src_ext == "html" and dst_ext in ("txt", "md"):
        _write_text(dst, _html_to_text(text))
    elif src_ext in ("txt", "log") and dst_ext == "html":
        _write_text(dst, "<html><body><pre>" + html.escape(text) + "</pre></body></html>")
    elif src_ext == "txt" and dst_ext == "json":
        _write_text(dst, json.dumps({"text": text}, ensure_ascii=False, indent=2))
    elif src_ext == "csv" and dst_ext in ("json", "jsonl"):
        rows = _csv_to_json(text)
        _write_text(
            dst,
            json.dumps(rows, ensure_ascii=False, indent=2)
            if dst_ext == "json"
            else _json_to_jsonl(rows),
        )
    elif src_ext in ("json", "jsonl") and dst_ext == "csv":
        value = _jsonl_to_json(text) if src_ext == "jsonl" else json.loads(text)
        _write_text(dst, _json_to_csv(value))
    elif src_ext == "json" and dst_ext == "jsonl":
        _write_text(dst, _json_to_jsonl(json.loads(text)))
    elif src_ext == "jsonl" and dst_ext == "json":
        _write_text(dst, json.dumps(_jsonl_to_json(text), ensure_ascii=False, indent=2))
    elif src_ext == "xml" and dst_ext == "json":
        _write_text(dst, json.dumps(_xml_to_json(text), ensure_ascii=False, indent=2))
    elif src_ext == "ini" and dst_ext == "json":
        _write_text(dst, json.dumps(_ini_to_json(text), ensure_ascii=False, indent=2))
    elif src_ext in ("txt", "log", "md") and dst_ext == "md":
        _write_text(dst, text)
    else:
        raise ConversionUnavailable(f"no built-in conversion from .{src_ext} to .{dst_ext}")
    return "stdlib"


def _format_time_srt(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis = 0
    if secs >= 60:
        minutes += 1
        secs = 0
    if minutes >= 60:
        hours += 1
        minutes = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_time_ass(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        secs += 1
        centis = 0
    if secs >= 60:
        minutes += 1
        secs = 0
    if minutes >= 60:
        hours += 1
        minutes = 0
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _parse_time(text: str) -> float:
    text = text.strip().replace(",", ".")
    parts = text.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        hours, minutes, seconds = "0", parts[0], parts[1]
    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)


def _srt_blocks(text: str) -> list[tuple[float, float, str]]:
    blocks: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        match = re.match(r"(\d+:\d+:\d+,\d+)\s*-->\s*(\d+:\d+:\d+,\d+)", lines[1])
        if not match:
            continue
        start = _parse_time(match.group(1))
        end = _parse_time(match.group(2))
        blocks.append((start, end, "\n".join(lines[2:])))
    return blocks


def _vtt_cues(text: str) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].startswith("WEBVTT") or lines[0].startswith("NOTE"):
            continue
        match = re.match(r"(\d+:\d+:\d+\.\d+)\s*-->\s*(\d+:\d+:\d+\.\d+)", lines[0])
        if not match:
            continue
        start = _parse_time(match.group(1))
        end = _parse_time(match.group(2))
        cues.append((start, end, "\n".join(lines[1:])))
    return cues


def _ass_dialogues(text: str) -> list[tuple[float, float, str]]:
    dialogues: list[tuple[float, float, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("Dialogue:"):
            continue
        fields = stripped[len("Dialogue:") :].strip().split(",", 9)
        if len(fields) < 10:
            continue
        start = _parse_time(fields[1])
        end = _parse_time(fields[2])
        dialogues.append((start, end, fields[9]))
    return dialogues


def _srt_to_vtt(blocks: list[tuple[float, float, str]]) -> str:
    lines = ["WEBVTT", ""]
    for start, end, text in blocks:
        lines.append(
            f"{_format_time_srt(start).replace(',', '.')} --> "
            f"{_format_time_srt(end).replace(',', '.')}"
        )
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _vtt_to_srt(cues: list[tuple[float, float, str]]) -> str:
    lines: list[str] = []
    for index, (start, end, text) in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(f"{_format_time_srt(start)} --> {_format_time_srt(end)}")
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _to_ass(blocks: list[tuple[float, float, str]]) -> str:
    lines = [_ASS_HEADER]
    for start, end, text in blocks:
        text = text.replace("\n", "\\N")
        lines.append(
            f"Dialogue: 0,{_format_time_ass(start)},{_format_time_ass(end)},"
            f"Default,,0,0,0,,{text}"
        )
    return "\n".join(lines)


def _convert_subtitle_file(src: Path, dst: Path, src_ext: str, dst_ext: str) -> str:
    text, _ = _read_text(src)
    if src_ext == dst_ext:
        _write_text(dst, text)
        return "copy"
    if src_ext == "srt" and dst_ext == "vtt":
        _write_text(dst, _srt_to_vtt(_srt_blocks(text)))
    elif src_ext == "vtt" and dst_ext == "srt":
        _write_text(dst, _vtt_to_srt(_vtt_cues(text)))
    elif src_ext in ("ass", "ssa") and dst_ext == "srt":
        _write_text(dst, _vtt_to_srt(_ass_dialogues(text)))
    elif src_ext in ("ass", "ssa") and dst_ext == "vtt":
        _write_text(dst, _srt_to_vtt(_ass_dialogues(text)))
    elif src_ext == "srt" and dst_ext in ("ass", "ssa"):
        _write_text(dst, _to_ass(_srt_blocks(text)))
    elif src_ext == "vtt" and dst_ext in ("ass", "ssa"):
        _write_text(dst, _to_ass(_vtt_cues(text)))
    else:
        raise ConversionUnavailable(
            f"no built-in subtitle conversion from .{src_ext} to .{dst_ext}"
        )
    return "stdlib"


def _create_archive(src: Path, dst: Path, dst_ext: str) -> str:
    if dst_ext == "zip":
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(src, arcname=src.name)
        return "stdlib"
    if dst_ext in ("tar", "gz", "bz2", "xz"):
        mode = {"tar": "w", "gz": "w:gz", "bz2": "w:bz2", "xz": "w:xz"}[dst_ext]
        with tarfile.open(dst, mode) as archive:
            archive.add(src, arcname=src.name)
        return "stdlib"
    raise ConversionUnavailable(f"archive target .{dst_ext} needs an external tool")


def _zip_member_is_safe(member_name: str) -> bool:
    normalized = member_name.replace("\\", "/")
    if normalized.startswith("/") or (len(normalized) >= 2 and normalized[1] == ":"):
        return False
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    return bool(parts) and all(part != ".." for part in parts)


def extract_archive(archive: str | Path, output_dir: str | Path) -> list[Path]:
    """Extract a zip/tar archive safely and return the written paths."""
    archive = Path(archive)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as zf:
            for zip_member in zf.infolist():
                if not _zip_member_is_safe(zip_member.filename):
                    raise ConversionError(f"unsafe zip member: {zip_member.filename}")
            zf.extractall(output)
            written = [output / zip_member.filename for zip_member in zf.infolist()]
    else:
        with tarfile.open(archive) as tf:
            for tar_member in tf.getmembers():
                if tar_member.name.startswith("/") or ".." in Path(tar_member.name).parts:
                    raise ConversionError(f"unsafe tar member: {tar_member.name}")
            tf.extractall(output)
            written = [
                output / tar_member.name for tar_member in tf.getmembers() if tar_member.isfile()
            ]
    return written


def _emit(
    progress: ProgressFn,
    task_id: int | str | None,
    stage: str,
    percent: float | None,
    input_size: int,
    output_size: int,
    start: float,
    current: str | None = None,
) -> None:
    if progress:
        progress(
            ConvertProgress(
                task_id=task_id,
                stage=stage,
                percent=percent,
                input_size=input_size,
                output_size=output_size,
                current=current,
                elapsed_s=time.monotonic() - start,
            )
        )


def convert_file(
    src: str | Path,
    dst: str | Path,
    *,
    profile: str | None = None,
    progress: ProgressFn = None,
    cancel: CancelToken | None = None,
    task_id: int | str | None = None,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
    extra_args: list[str] | None = None,
) -> ConvertResult:
    """Convert one file, dispatching to the engine declared by the target."""
    src_path = Path(src)
    dst_path = Path(dst)
    if not src_path.is_file():
        raise ConversionError(f"source file not found: {src_path}")
    if cancel and cancel.cancelled:
        raise ConversionError("conversion cancelled")
    src_ext = src_path.suffix.lower().lstrip(".")
    dst_ext = dst_path.suffix.lower().lstrip(".")
    src_spec = lookup_format(src_ext)
    dst_spec = lookup_format(dst_ext)
    if dst_spec is None:
        raise ConversionUnavailable(f"unknown target format: .{dst_ext}")
    if src_spec is not None and dst_spec is not None:
        cross_ok = (
            (src_spec.category == "video" and dst_spec.category in ("audio", "image"))
            or src_spec.category == dst_spec.category
            or dst_spec.category == "archive"
        )
        if not cross_ok:
            raise ConversionError(
                f"cannot convert .{src_ext} ({src_spec.category}) "
                f"to .{dst_ext} ({dst_spec.category})"
            )
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    input_size = src_path.stat().st_size

    if dst_spec.engine == "ffmpeg" or (
        src_spec is not None and src_spec.category == "video" and dst_spec.category == "image"
    ):
        from ffmpeg_transcoder import transcode_file

        transcode_events: list[Any] = []

        def on_transcode(event: Any) -> None:
            transcode_events.append(event)
            output_size = event.output_size or 0
            _emit(
                progress,
                task_id,
                event.stage,
                event.percent,
                input_size,
                output_size,
                start,
                current=str(src_path),
            )

        transcode_file(
            src_path,
            dst_path,
            profile=dst_spec.profile or profile,
            progress=on_transcode,
            cancel=cancel,
            task_id=task_id,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
            extra_args=extra_args,
        )
        output_size = dst_path.stat().st_size if dst_path.exists() else 0
        _emit(progress, task_id, "done", 1.0, input_size, output_size, start)
        return ConvertResult(dst_path, "ffmpeg", input_size, output_size, time.monotonic() - start)

    if dst_spec.engine == "stdlib":
        if dst_spec.category in ("document", "data"):
            _emit(progress, task_id, "convert", 0.0, input_size, 0, start)
            engine = _convert_text_file(src_path, dst_path, src_ext, dst_ext)
        elif dst_spec.category == "subtitle":
            _emit(progress, task_id, "convert", 0.0, input_size, 0, start)
            engine = _convert_subtitle_file(src_path, dst_path, src_ext, dst_ext)
        elif dst_spec.category == "archive":
            _emit(progress, task_id, "archive", 0.0, input_size, 0, start)
            engine = _create_archive(src_path, dst_path, dst_ext)
        else:
            raise ConversionUnavailable(f"no stdlib converter for .{dst_ext}")
        output_size = dst_path.stat().st_size if dst_path.exists() else 0
        _emit(progress, task_id, "done", 1.0, input_size, output_size, start)
        return ConvertResult(dst_path, engine, input_size, output_size, time.monotonic() - start)

    if dst_spec.engine == "copy":
        _emit(progress, task_id, "copy", 0.0, input_size, 0, start)
        shutil.copy2(src_path, dst_path)
        output_size = dst_path.stat().st_size
        _emit(progress, task_id, "done", 1.0, input_size, output_size, start)
        return ConvertResult(dst_path, "copy", input_size, output_size, time.monotonic() - start)

    raise ConversionUnavailable(
        f".{dst_ext} requires an optional tool: {dst_spec.note or 'external converter'}"
    )


def convert_many(
    inputs: Iterable[str | Path],
    output_dir: str | Path,
    target_ext: str,
    *,
    progress: BatchProgressFn = None,
    cancel: CancelToken | None = None,
    task_id: int | str | None = None,
    ffmpeg_path: str = "ffmpeg",
    ffprobe_path: str = "ffprobe",
) -> dict[str, Any]:
    """Convert a folder of files and emit aggregate byte-based progress."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    target_spec = lookup_format(target_ext)
    if target_spec is None:
        raise ConversionUnavailable(f"unknown target format: {target_ext}")
    items = [Path(item) for item in inputs]
    missing = [item for item in items if not item.is_file()]
    if missing:
        raise ConversionError(f"missing source files: {missing[0]}")
    total_input_bytes = sum(item.stat().st_size for item in items)
    start = time.monotonic()
    done_bytes = 0
    output_bytes = 0
    results: list[ConvertResult] = []

    def emit(stage: str, percent: float | None, done: int, current: str | None = None) -> None:
        if progress:
            progress(
                BatchConvertProgress(
                    task_id=task_id,
                    stage=stage,
                    percent=percent,
                    done=done,
                    total=len(items),
                    input_bytes_done=done_bytes,
                    total_input_bytes=total_input_bytes,
                    output_bytes=output_bytes,
                    current=current,
                    elapsed_s=time.monotonic() - start,
                )
            )

    emit("preflight", 0.0, 0)
    for index, src_path in enumerate(items):
        if cancel and cancel.cancelled:
            raise ConversionError("batch conversion cancelled")
        dst_path = output / f"{src_path.stem}.{target_spec.extension}"
        size = src_path.stat().st_size

        def child_progress(
            event: ConvertProgress,
            done_bytes_base: int = done_bytes,
            size: int = size,
            index: int = index,
        ) -> None:
            nonlocal done_bytes, output_bytes
            fraction = event.percent if event.percent is not None else 0.0
            done_bytes = int(done_bytes_base + fraction * size)
            output_bytes = max(output_bytes, event.output_size)
            emit(
                event.stage, (done_bytes / total_input_bytes) if total_input_bytes else None, index
            )

        done_bytes_base = done_bytes
        result = convert_file(
            src_path,
            dst_path,
            progress=child_progress,
            cancel=cancel,
            task_id=task_id,
            ffmpeg_path=ffmpeg_path,
            ffprobe_path=ffprobe_path,
        )
        results.append(result)
        done_bytes = done_bytes_base + size
        output_bytes += result.output_size
        emit("done", (done_bytes / total_input_bytes) if total_input_bytes else 1.0, index + 1)
    elapsed = time.monotonic() - start
    return {
        "results": [asdict(result) for result in results],
        "total_input_bytes": total_input_bytes,
        "total_output_bytes": output_bytes,
        "elapsed_s": elapsed,
        "average_speed": output_bytes / elapsed if elapsed > 0 else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert files with the unified engine")
    parser.add_argument("--convert", nargs=2, metavar=("SRC", "DST"))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--batch", nargs="+", metavar="SRC")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--target", default=None)
    parser.add_argument("--extract", nargs=2, metavar=("ARCHIVE", "DIR"))
    args = parser.parse_args(argv)
    if args.extract:
        written = extract_archive(args.extract[0], args.extract[1])
        print(f"extracted {len(written)} files")
        return 0
    if args.convert:
        result = convert_file(
            args.convert[0],
            args.convert[1],
            profile=args.profile,
        )
        print(
            f"converted: {result.path} ({result.engine}, "
            f"{result.input_size} -> {result.output_size} bytes, {result.elapsed_s:.2f}s)"
        )
        return 0
    if args.batch:
        if not args.output_dir or not args.target:
            parser.error("--batch requires --output-dir and --target")
        summary = convert_many(args.batch, args.output_dir, args.target)
        print(f"batch converted {len(summary['results'])} files")
        return 0
    parser.error("pass --convert, --batch, or --extract")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
