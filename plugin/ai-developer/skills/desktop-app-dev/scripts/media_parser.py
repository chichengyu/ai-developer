"""Page parsing and HLS/m3u8 parsing for the media pipeline.

The HTML extractor uses the standard-library HTMLParser, so it runs without
BeautifulSoup. Install BeautifulSoup / lxml for production pages that need
CSS-selector-level extraction.
"""

from __future__ import annotations

import re
import urllib.parse
from contextlib import suppress
from dataclasses import dataclass, field
from html.parser import HTMLParser

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
    links: list[str] = field(default_factory=list)

    def all_urls(self) -> list[str]:
        return self.videos + self.audios + self.images + self.hls + self.links


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
    for name in ("videos", "audios", "images", "hls", "links"):
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
class M3U8Segment:
    duration: float
    uri: str
    key_index: int | None = None
    byterange: str | None = None


@dataclass
class M3U8Playlist:
    is_master: bool = False
    variants: list[M3U8Variant] = field(default_factory=list)
    segments: list[M3U8Segment] = field(default_factory=list)
    keys: list[M3U8Key] = field(default_factory=list)
    target_duration: float | None = None
    init_uri: str | None = None
    init_byterange: str | None = None
    endlist: bool = False


def _attr_value(line: str, key: str) -> str | None:
    match = re.search(rf"{re.escape(key)}=([^,]+)", line)
    if not match:
        return None
    return match.group(1).strip().strip('"')


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
        elif line.startswith("#EXT-X-ENDLIST"):
            playlist.endlist = True
        elif line.startswith("#EXT-X-MAP:"):
            uri = _attr_value(line, "URI")
            byterange = _attr_value(line, "BYTERANGE")
            if uri:
                playlist.init_uri = normalize_url(uri, base_url)
                playlist.init_byterange = byterange
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


if __name__ == "__main__":
    print(
        "desktop-app-dev media_parser: import parse_m3u8() / extract_media_urls() for page and HLS parsing."
    )
