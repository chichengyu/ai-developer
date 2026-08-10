"""Page parsing and HLS/m3u8 parsing for the media pipeline.

The HTML extractor uses the standard-library HTMLParser, so it runs without
BeautifulSoup. Install BeautifulSoup / lxml for production pages that need
CSS-selector-level extraction.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

_MEDIA_TAGS = {"video", "audio", "img", "source", "track", "a", "link"}
_URL_ATTRS = ("src", "data-src", "data-original", "poster", "href")


def normalize_url(url: str, base_url: str | None = None) -> str:
    """Resolve a relative URL against the page/base URL."""
    url = url.strip()
    if url.startswith(("http://", "https://", "data:", "blob:", "ws:", "wss:")):
        return url
    if base_url:
        return urllib.parse.urljoin(base_url, url)
    return url


def _srcset_urls(srcset: str) -> list[str]:
    urls: list[str] = []
    for candidate in srcset.split(","):
        part = candidate.strip().split()
        if part:
            urls.append(part[0])
    return urls


class _MediaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: list[tuple[str, list[str]]] = []
        self.base_href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        if tag == "base":
            href = attr_map.get("href", "").strip()
            if href:
                self.base_href = href
            return
        if tag not in _MEDIA_TAGS:
            return
        urls: list[str] = []
        for attr in _URL_ATTRS:
            value = attr_map.get(attr, "").strip()
            if value and not value.startswith("#"):
                urls.append(value)
        srcset = attr_map.get("srcset", "").strip()
        if srcset:
            urls.extend(_srcset_urls(srcset))
        if urls:
            self.found.append((tag, urls))


@dataclass
class MediaExtraction:
    """Normalized media URLs found on one page."""

    videos: list[str] = field(default_factory=list)
    audios: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    hls: list[str] = field(default_factory=list)
    dash: list[str] = field(default_factory=list)
    smooth: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    def all_urls(self) -> list[str]:
        return (
            self.videos
            + self.audios
            + self.images
            + self.hls
            + self.dash
            + self.smooth
            + self.links
        )


def extract_media_urls(html: str, base_url: str | None = None) -> MediaExtraction:
    """Extract video/audio/image/HLS URLs from an HTML document."""
    parser = _MediaHTMLParser()
    parser.feed(html)
    effective_base = normalize_url(parser.base_href, base_url) if parser.base_href else base_url
    result = MediaExtraction()
    for tag, urls in parser.found:
        for url in urls:
            normalized = normalize_url(url, effective_base)
            if normalized.startswith("blob:") or normalized.startswith("data:"):
                continue
            if ".m3u8" in normalized.lower():
                result.hls.append(normalized)
                continue
            if ".mpd" in normalized.lower() or "application/dash" in normalized.lower():
                result.dash.append(normalized)
                continue
            if ".ism/manifest" in normalized.lower() or (
                "manifest" in normalized.lower() and "format=mp4" in normalized.lower()
            ):
                result.smooth.append(normalized)
                continue
            if tag == "video":
                result.videos.append(normalized)
            elif tag == "audio":
                result.audios.append(normalized)
            elif tag == "img":
                result.images.append(normalized)
            else:
                result.links.append(normalized)
    return _dedupe(result)


def _dedupe(extraction: MediaExtraction) -> MediaExtraction:
    seen: set[str] = set()
    for name in ("videos", "audios", "images", "hls", "dash", "smooth", "links"):
        values: list[str] = []
        for url in getattr(extraction, name):
            if url not in seen:
                seen.add(url)
                values.append(url)
        setattr(extraction, name, values)
    return extraction


@dataclass
class M3U8Variant:
    bandwidth: int
    resolution: str | None
    codecs: str | None
    url: str


@dataclass
class M3U8Key:
    method: str
    uri: str | None
    iv: str | None


@dataclass
class M3U8Rendition:
    media_type: str
    uri: str | None
    group_id: str | None = None
    name: str | None = None
    language: str | None = None


@dataclass
class M3U8Segment:
    duration: float
    uri: str
    key_index: int | None = None
    byterange: str | None = None


@dataclass
class M3U8Part:
    uri: str
    duration: float
    byterange: str | None = None
    independent: bool = False


@dataclass
class M3U8Playlist:
    is_master: bool = False
    variants: list[M3U8Variant] = field(default_factory=list)
    segments: list[M3U8Segment] = field(default_factory=list)
    keys: list[M3U8Key] = field(default_factory=list)
    renditions: list[M3U8Rendition] = field(default_factory=list)
    target_duration: float | None = None
    init_uri: str | None = None
    init_byterange: str | None = None
    media_sequence: int = 0
    endlist: bool = False
    server_control: dict[str, str | None] = field(default_factory=dict)
    part_inf: dict[str, str | None] = field(default_factory=dict)
    skip: dict[str, str | None] = field(default_factory=dict)
    parts: list[M3U8Part] = field(default_factory=list)
    preload_hint: dict[str, str | None] | None = None
    program_date_time: str | None = None
    date_ranges: list[dict[str, str | None]] = field(default_factory=list)
    i_frames: list[M3U8Variant] = field(default_factory=list)


def _attr_value(line: str, key: str) -> str | None:
    match = re.search(rf"{re.escape(key)}=([^,]+)", line)
    if not match:
        return None
    return match.group(1).strip().strip('"')


def _attrs(line: str) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for key, quoted, unquoted in re.findall(
        r"([A-Za-z0-9_-]+)=(?:\"([^\"]*)\"|([^,\s]+))",
        line,
    ):
        result[key] = quoted if quoted != "" else (unquoted or None)
    return result


def parse_m3u8(text: str, base_url: str | None = None) -> M3U8Playlist:
    """Parse a media or master HLS playlist."""
    playlist = M3U8Playlist()
    current_variant: dict[str, str | int | None] = {}
    current_duration: float | None = None
    current_byterange: str | None = None
    byte_range_offsets: dict[str, int] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-TARGETDURATION:"):
            value = line.split(":", 1)[1].strip()
            with suppress(ValueError):
                playlist.target_duration = float(value)
        elif line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            value = line.split(":", 1)[1].strip()
            with suppress(ValueError):
                playlist.media_sequence = int(value)
        elif line.startswith("#EXT-X-ENDLIST"):
            playlist.endlist = True
        elif line.startswith("#EXT-X-SERVER-CONTROL:"):
            playlist.server_control = _attrs(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-PART-INF:"):
            playlist.part_inf = _attrs(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-SKIP:"):
            playlist.skip = _attrs(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-PART:"):
            part_attrs = _attrs(line.split(":", 1)[1])
            part_uri = part_attrs.get("URI")
            if part_uri:
                try:
                    part_duration = float(part_attrs.get("DURATION") or 0)
                except ValueError:
                    part_duration = 0.0
                playlist.parts.append(
                    M3U8Part(
                        uri=normalize_url(part_uri, base_url),
                        duration=part_duration,
                        byterange=part_attrs.get("BYTERANGE"),
                        independent=str(part_attrs.get("INDEPENDENT") or "").lower()
                        in {"yes", "true", "1"},
                    )
                )
        elif line.startswith("#EXT-X-PRELOAD-HINT:"):
            playlist.preload_hint = _attrs(line.split(":", 1)[1])
        elif line.startswith("#EXT-X-PROGRAM-DATE-TIME:"):
            playlist.program_date_time = line.split(":", 1)[1].strip() or None
        elif line.startswith("#EXT-X-DATERANGE:"):
            playlist.date_ranges.append(_attrs(line.split(":", 1)[1]))
        elif line.startswith("#EXT-X-I-FRAME-STREAM-INF:"):
            frame_attrs = _attrs(line.split(":", 1)[1])
            frame_uri = frame_attrs.get("URI")
            if frame_uri:
                playlist.i_frames.append(
                    M3U8Variant(
                        bandwidth=int(frame_attrs.get("BANDWIDTH") or 0),
                        resolution=frame_attrs.get("RESOLUTION"),
                        codecs=frame_attrs.get("CODECS"),
                        url=normalize_url(frame_uri, base_url),
                    )
                )
        elif line.startswith("#EXT-X-MAP:"):
            uri = _attr_value(line, "URI")
            byterange = _attr_value(line, "BYTERANGE")
            if uri:
                playlist.init_uri = normalize_url(uri, base_url)
                playlist.init_byterange = byterange
        elif line.startswith("#EXT-X-MEDIA:"):
            media_type = _attr_value(line, "TYPE") or ""
            uri = _attr_value(line, "URI")
            playlist.renditions.append(
                M3U8Rendition(
                    media_type=media_type,
                    uri=normalize_url(uri, base_url) if uri else None,
                    group_id=_attr_value(line, "GROUP-ID"),
                    name=_attr_value(line, "NAME"),
                    language=_attr_value(line, "LANGUAGE"),
                )
            )
        elif line.startswith("#EXT-X-STREAM-INF:"):
            playlist.is_master = True
            current_variant = {
                "bandwidth": int(_attr_value(line, "BANDWIDTH") or 0),
                "resolution": _attr_value(line, "RESOLUTION"),
                "codecs": _attr_value(line, "CODECS"),
            }
        elif line.startswith("#EXT-X-BYTERANGE:"):
            current_byterange = line.split(":", 1)[1].strip()
        elif line.startswith("#EXT-X-KEY:"):
            method = _attr_value(line, "METHOD") or "NONE"
            uri = _attr_value(line, "URI")
            iv = _attr_value(line, "IV")
            playlist.keys.append(
                M3U8Key(
                    method=method,
                    uri=normalize_url(uri, base_url) if uri else None,
                    iv=iv,
                )
            )
        elif line.startswith("#EXTINF:"):
            value = line.split(":", 1)[1].split(",", 1)[0].strip()
            try:
                current_duration = float(value)
            except ValueError:
                current_duration = None
        elif not line.startswith("#") and line:
            url = normalize_url(line, base_url)
            if playlist.is_master and current_variant:
                playlist.variants.append(
                    M3U8Variant(
                        bandwidth=int(current_variant.get("bandwidth") or 0),
                        resolution=str(current_variant.get("resolution") or None),
                        codecs=str(current_variant.get("codecs") or None),
                        url=url,
                    )
                )
                current_variant = {}
            else:
                key_index = None
                if playlist.keys:
                    key_index = len(playlist.keys) - 1
                byterange = None
                if current_byterange:
                    length_text, _, offset_text = current_byterange.partition("@")
                    try:
                        length = int(length_text, 0)
                        offset = (
                            int(offset_text, 0) if offset_text else byte_range_offsets.get(url, 0)
                        )
                        byte_range_offsets[url] = offset + length
                        byterange = f"{length}@{offset}"
                    except ValueError:
                        byterange = None
                    current_byterange = None
                playlist.segments.append(
                    M3U8Segment(
                        duration=current_duration or 0.0,
                        uri=url,
                        key_index=key_index,
                        byterange=byterange,
                    )
                )
    return playlist


def choose_best_variant(playlist: M3U8Playlist) -> M3U8Variant | None:
    """Pick the highest-bandwidth master playlist variant."""
    if not playlist.variants:
        return None
    return max(playlist.variants, key=lambda item: item.bandwidth)


@dataclass
class MPDSegmentTemplate:
    media: str | None = None
    initialization: str | None = None
    timescale: int = 1
    duration: int | None = None
    start_number: int = 1
    timeline: list[tuple[int, int, int]] = field(default_factory=list)


@dataclass
class MPDRepresentation:
    id: str
    bandwidth: int
    width: int | None
    height: int | None
    codecs: str | None
    mime_type: str | None
    base_url: str | None
    template: MPDSegmentTemplate | None = None
    segment_urls: list[str] = field(default_factory=list)
    segment_base: dict[str, str | None] | None = None


@dataclass
class MPDPlaylist:
    url: str | None = None
    type: str = "static"
    media_presentation_duration: float | None = None
    min_buffer_time: float | None = None
    base_url: str | None = None
    representations: list[MPDRepresentation] = field(default_factory=list)


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first_child_text(parent: Any, name: str) -> str | None:
    for child in parent:
        if _local_tag(child.tag) == name:
            value = (child.text or "").strip()
            return value or None
    return None


def _iso8601_duration(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(
        r"^P(?:(\d+(?:\.\d+)?)D)?(?:T(?:(\d+(?:\.\d+)?)H)?"
        r"(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$",
        value,
    )
    if not match:
        return None
    days, hours, minutes, seconds = (float(item) if item else 0.0 for item in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _int_attr(element: Any, name: str, default: int = 0) -> int:
    value = element.get(name)
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


def _find_segment_template(*containers: Any) -> MPDSegmentTemplate | None:
    for container in containers:
        for child in container:
            if _local_tag(child.tag) != "SegmentTemplate":
                continue
            template = MPDSegmentTemplate(
                media=child.get("media"),
                initialization=child.get("initialization"),
                timescale=_int_attr(child, "timescale", 1),
                duration=_int_attr(child, "duration", 0) or None,
                start_number=_int_attr(child, "startNumber", 1) or 1,
            )
            for timeline in child:
                if _local_tag(timeline.tag) != "SegmentTimeline":
                    continue
                for s in timeline:
                    if _local_tag(s.tag) == "S":
                        template.timeline.append(
                            (
                                _int_attr(s, "t", 0),
                                _int_attr(s, "d", 0),
                                _int_attr(s, "r", 0),
                            )
                        )
            return template
    return None


def _template_number(pattern: str, number: int) -> str:
    def replace(match: re.Match[str]) -> str:
        width = int(match.group(1)) if match.group(1) else 0
        return str(number).zfill(width)

    return re.sub(r"\$Number(?:%(\d+)d)?\$", replace, pattern)


def _template_vars(pattern: str, representation: MPDRepresentation) -> str:
    return (
        pattern.replace("$RepresentationID$", representation.id)
        .replace("$Bandwidth$", str(representation.bandwidth))
    )


def mpd_initialization_url(representation: MPDRepresentation) -> str | None:
    if representation.template is None or not representation.template.initialization:
        return None
    url = _template_vars(representation.template.initialization, representation)
    return normalize_url(url, representation.base_url)


def mpd_initialization_range(
    representation: MPDRepresentation,
) -> tuple[str, str] | None:
    if (
        representation.segment_base
        and representation.base_url
        and representation.segment_base.get("init_range")
    ):
        return representation.base_url, str(representation.segment_base["init_range"])
    return None


def build_mpd_segment_urls(
    representation: MPDRepresentation,
    max_segments: int = 1000,
) -> list[str]:
    if representation.segment_base and representation.base_url:
        return [representation.base_url]
    if representation.segment_urls:
        return list(representation.segment_urls[:max_segments])
    if representation.template is None or not representation.template.media:
        return []
    template = representation.template
    urls: list[str] = []
    number = template.start_number
    if template.timeline:
        for _t, _duration, repeat in template.timeline:
            for _ in range(max(0, repeat) + 1):
                pattern = _template_number(template.media, number)
                urls.append(normalize_url(_template_vars(pattern, representation), representation.base_url))
                number += 1
                if len(urls) >= max_segments:
                    return urls
    elif template.duration:
        for _ in range(max_segments):
            pattern = _template_number(template.media, number)
            urls.append(normalize_url(_template_vars(pattern, representation), representation.base_url))
            number += 1
    return urls


def parse_mpd(text: str, base_url: str | None = None) -> MPDPlaylist:
    """Parse a DASH MPD manifest into representations and segment templates."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid MPD XML: {exc}") from exc
    playlist = MPDPlaylist(
        url=base_url,
        type=str(root.get("type") or "static"),
        media_presentation_duration=_iso8601_duration(
            root.get("mediaPresentationDuration")
        ),
        min_buffer_time=_iso8601_duration(root.get("minBufferTime")),
    )
    root_base = _first_child_text(root, "BaseURL")
    playlist.base_url = normalize_url(root_base, base_url) if root_base else base_url
    for period in root:
        if _local_tag(period.tag) != "Period":
            continue
        period_base = _first_child_text(period, "BaseURL")
        for adaptation in period:
            if _local_tag(adaptation.tag) != "AdaptationSet":
                continue
            adaptation_mime = adaptation.get("mimeType")
            adaptation_base = _first_child_text(adaptation, "BaseURL")
            for representation_node in adaptation:
                if _local_tag(representation_node.tag) != "Representation":
                    continue
                representation_base = (
                    _first_child_text(representation_node, "BaseURL")
                    or adaptation_base
                    or period_base
                    or playlist.base_url
                )
                if representation_base:
                    representation_base = normalize_url(
                        representation_base,
                        playlist.base_url,
                    )
                template = _find_segment_template(
                    representation_node,
                    adaptation,
                    period,
                )
                segment_urls: list[str] = []
                for container in (representation_node, adaptation, period):
                    for child in container:
                        if _local_tag(child.tag) != "SegmentList":
                            continue
                        for segment in child:
                            if _local_tag(segment.tag) != "SegmentURL":
                                continue
                            media = segment.get("media")
                            if media:
                                segment_urls.append(
                                    normalize_url(media, representation_base)
                                )
                segment_base: dict[str, str | None] | None = None
                for container in (representation_node, adaptation, period):
                    for child in container:
                        if _local_tag(child.tag) != "SegmentBase":
                            continue
                        init_range: str | None = None
                        for sub in child:
                            if _local_tag(sub.tag) == "Initialization":
                                init_range = sub.get("range")
                        segment_base = {
                            "index_range": child.get("indexRange"),
                            "init_range": init_range,
                        }
                representation = MPDRepresentation(
                    id=str(representation_node.get("id") or f"rep-{len(playlist.representations)}"),
                    bandwidth=_int_attr(representation_node, "bandwidth"),
                    width=_int_attr(representation_node, "width", 0) or None,
                    height=_int_attr(representation_node, "height", 0) or None,
                    codecs=representation_node.get("codecs"),
                    mime_type=representation_node.get("mimeType") or adaptation_mime,
                    base_url=representation_base,
                    template=template,
                    segment_urls=segment_urls,
                    segment_base=segment_base,
                )
                playlist.representations.append(representation)
    return playlist


def select_mpd_representation(
    playlist: MPDPlaylist,
    *,
    preferred_height: int | None = None,
    max_bandwidth: int | None = None,
) -> MPDRepresentation | None:
    representations = list(playlist.representations)
    if max_bandwidth is not None:
        representations = [
            item for item in representations if item.bandwidth <= max_bandwidth
        ]
    if preferred_height is not None:
        eligible = [
            item
            for item in representations
            if item.height is not None and item.height <= preferred_height
        ]
        if eligible:
            representations = eligible
    if not representations:
        return None
    return max(
        representations,
        key=lambda item: (item.bandwidth, item.height or 0),
    )


@dataclass
class SmoothQualityLevel:
    index: int
    bitrate: int
    width: int | None
    height: int | None
    fourcc: str | None


@dataclass
class SmoothChunk:
    timestamp: int
    duration: int


@dataclass
class SmoothStream:
    media_type: str
    url_template: str | None
    name: str | None
    qualities: list[SmoothQualityLevel] = field(default_factory=list)
    chunks: list[SmoothChunk] = field(default_factory=list)


@dataclass
class SmoothPlaylist:
    url: str | None = None
    duration_seconds: float | None = None
    is_live: bool = False
    streams: list[SmoothStream] = field(default_factory=list)


def parse_smooth_manifest(text: str, base_url: str | None = None) -> SmoothPlaylist:
    """Parse a Microsoft Smooth Streaming manifest."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"invalid Smooth Streaming XML: {exc}") from exc
    playlist = SmoothPlaylist(url=base_url)
    duration = _int_attr(root, "Duration", 0)
    if duration:
        playlist.duration_seconds = duration / 10_000_000
    playlist.is_live = str(root.get("IsLive") or "").lower() in {"true", "1"}
    for stream_node in root:
        if _local_tag(stream_node.tag) != "StreamIndex":
            continue
        stream = SmoothStream(
            media_type=str(stream_node.get("Type") or "video"),
            url_template=stream_node.get("Url"),
            name=stream_node.get("Name"),
        )
        for child in stream_node:
            tag = _local_tag(child.tag)
            if tag == "QualityLevel":
                stream.qualities.append(
                    SmoothQualityLevel(
                        index=_int_attr(child, "Index", 0),
                        bitrate=_int_attr(child, "Bitrate"),
                        width=_int_attr(child, "MaxWidth", 0) or None,
                        height=_int_attr(child, "MaxHeight", 0) or None,
                        fourcc=child.get("FourCC"),
                    )
                )
            elif tag == "c":
                stream.chunks.append(
                    SmoothChunk(
                        timestamp=_int_attr(child, "t", 0),
                        duration=_int_attr(child, "d", 0),
                    )
                )
        playlist.streams.append(stream)
    return playlist


def parse_css_assets(text: str, base_url: str | None = None) -> list[str]:
    """Extract url() and @import resources from CSS text."""
    found: list[str] = []
    patterns = (
        r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)",
        r"@import\s+(['\"])([^'\"]+)\1",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            raw = (match.group(2) if match.lastindex == 2 else match.group(2)).strip()
            if raw.startswith(("data:", "#", "//")):
                continue
            normalized = normalize_url(raw, base_url)
            if normalized.startswith(("http://", "https://")) and normalized not in found:
                found.append(normalized)
    return found


def parse_js_assets(text: str, base_url: str | None = None) -> list[str]:
    """Extract asset-like string URLs from JavaScript text."""
    found: list[str] = []
    patterns = (
        r"import\s*(?:\(\s*)?(['\"])([^'\"]+)\1",
        r"require\s*\(\s*(['\"])([^'\"]+)\1",
        r"new\s+URL\s*\(\s*(['\"])([^'\"]+)\1",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            raw = match.group(2).strip()
            normalized = normalize_url(raw, base_url)
            if normalized.startswith(("http://", "https://")) and normalized not in found:
                found.append(normalized)
    asset_suffix = re.compile(
        r"['\"]([^'\"]+\.(?:css|js|mjs|png|jpe?g|gif|webp|svg|woff2?|ttf|otf|eot|mp4|webm|mp3|m4a|json|xml|pdf|zip))['\"]",
        re.IGNORECASE,
    )
    for match in asset_suffix.finditer(text):
        normalized = normalize_url(match.group(1), base_url)
        if normalized.startswith(("http://", "https://")) and normalized not in found:
            found.append(normalized)
    return found


if __name__ == "__main__":
    print(
        "desktop-app-dev media_parser: import parse_m3u8() / extract_media_urls() for page and HLS parsing."
    )
