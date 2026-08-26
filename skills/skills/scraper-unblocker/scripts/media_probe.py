#!/usr/bin/env python3
"""Deep media probe: extract metadata and media assets from a page.

Parses HTML for titles, Open Graph/JSON-LD metadata, inline state JSON,
video/audio/image sources, and manifest links. Stdlib-only; it never bypasses
access controls.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from scraper_probe import (
    DEFAULT_USER_AGENT,
    detect_blocks,
    fetch,
    load_cookie_header,
    parse_headers,
)

INLINE_STATE_KEYS = [
    "__INITIAL_STATE__",
    "__NUXT__",
    "__NEXT_DATA__",
    "__APP_DATA__",
    "__PRELOADED_STATE__",
    "_SSR_DATA",
]

MEDIA_EXTENSIONS = {
    "video": (".mp4", ".webm", ".mov", ".mkv", ".flv", ".avi", ".ts"),
    "image": (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".bmp"),
    "audio": (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac"),
    "manifest": (".m3u8", ".mpd"),
}


def classify_url(url: str, hint: str = "") -> str:
    path = urlparse(url).path.lower()
    query = urlparse(url).query.lower()
    hint = hint.lower()
    if "mime_type=video" in query or "/video/" in path or "/vod/" in path:
        return "video"
    if "mime_type=image" in query or "/image/" in path:
        return "image"
    if "mime_type=audio" in query:
        return "audio"
    if path.endswith(MEDIA_EXTENSIONS["manifest"]) or "mpegurl" in hint or "dash" in hint:
        return "manifest"
    if path.endswith(MEDIA_EXTENSIONS["video"]) or hint.startswith("video/"):
        return "video"
    if path.endswith(MEDIA_EXTENSIONS["image"]) or hint.startswith("image/"):
        return "image"
    if path.endswith(MEDIA_EXTENSIONS["audio"]) or hint.startswith("audio/"):
        return "audio"
    return "unknown"


def extract_inline_json(script_text: str) -> Dict[str, Any]:
    found: Dict[str, Any] = {}
    for key in INLINE_STATE_KEYS:
        pattern = re.compile(r"window\.[\"']?" + re.escape(key) + r"[\"']?\s*=\s*")
        match = pattern.search(script_text)
        if not match:
            continue
        start = script_text.find("{", match.end())
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        end = None
        for index in range(start, len(script_text)):
            char = script_text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end:
            try:
                found[key] = json.loads(script_text[start:end])
            except Exception:
                found[key] = None
    return found


def clean_drama_name(raw: str) -> str:
    if not raw:
        return ""
    cleaned = re.sub(r"\s*[-_|]\s*(红果短剧|hongguoduanju).*$", "", raw, flags=re.I)
    cleaned = re.sub(r"\s*(在线观看|全集|完整版|高清|免费)\s*$", "", cleaned)
    return cleaned.strip()


def extract_media_from_json(
    data: Any, base_url: str, max_items: int = 2000
) -> List[Dict[str, Any]]:
    media: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def walk(node: Any, path: str = "") -> None:
        if len(media) >= max_items:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                key_text = str(key).lower()
                if (
                    isinstance(value, str)
                    and value.startswith(("http://", "https://", "//"))
                    and any(
                        token in key_text
                        for token in ("video", "play", "stream", "media", "src", "url", "m3u8", "mp4")
                    )
                ):
                    url = urljoin(base_url, value) if value.startswith("//") else value
                    kind = classify_url(url)
                    if kind != "unknown" and url not in seen:
                        seen.add(url)
                        media.append(
                            {
                                "kind": kind,
                                "url": url,
                                "source": f"inline_json{path}.{key}",
                                "text": "",
                            }
                        )
                walk(value, f"{path}.{key}" if path else str(key))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{path}[{index}]")
        elif isinstance(node, str):
            text = node.strip()
            if not text.startswith(("http://", "https://", "//")):
                return
            url = urljoin(base_url, text) if text.startswith("//") else text
            kind = classify_url(url)
            if kind != "unknown" and url not in seen:
                seen.add(url)
                media.append(
                    {
                        "kind": kind,
                        "url": url,
                        "source": f"inline_json{path}",
                        "text": "",
                    }
                )

    walk(data)
    return media


def dedupe_media(media: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for item in media:
        key = item["url"].split("#")[0]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


class MediaPageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.h1 = ""
        self.meta: Dict[str, str] = {}
        self.json_ld: List[Any] = []
        self.media: List[Dict[str, Any]] = []
        self.links: List[str] = []
        self.script_urls: List[str] = []
        self.inline_state: Dict[str, Any] = {}
        self._title_parts: List[str] = []
        self._h1_parts: List[str] = []
        self._in_title = False
        self._in_h1 = False
        self._collect_script = False
        self._script_type = ""
        self._script_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        attr_map = {key.lower(): value for key, value in attrs if value is not None}
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "meta":
            key = attr_map.get("property") or attr_map.get("name") or attr_map.get(
                "itemprop"
            ) or attr_map.get("http-equiv")
            if key:
                value = attr_map.get("content", "")
                self.meta[key.lower()] = value
                if key.lower() in (
                    "og:video",
                    "og:video:url",
                    "og:video:secure_url",
                    "og:image",
                    "og:image:url",
                    "og:image:secure_url",
                    "twitter:image",
                    "twitter:player:stream",
                ):
                    self.media.append(
                        {
                            "kind": classify_url(value, attr_map.get("type", "")),
                            "url": urljoin(self.base_url, value),
                            "source": key.lower(),
                            "text": self.meta.get("og:title", ""),
                        }
                    )
        elif tag == "video":
            src = attr_map.get("src")
            if src:
                self.media.append(
                    {
                        "kind": "video",
                        "url": urljoin(self.base_url, src),
                        "source": "video[src]",
                        "text": "",
                    }
                )
            poster = attr_map.get("poster")
            if poster:
                self.media.append(
                    {
                        "kind": "image",
                        "url": urljoin(self.base_url, poster),
                        "source": "video[poster]",
                        "text": "",
                    }
                )
        elif tag == "source":
            src = attr_map.get("src")
            if src:
                kind = classify_url(src, attr_map.get("type", ""))
                self.media.append(
                    {
                        "kind": kind,
                        "url": urljoin(self.base_url, src),
                        "source": "source[src]",
                        "text": "",
                    }
                )
        elif tag == "img":
            src = (
                attr_map.get("src")
                or attr_map.get("data-src")
                or attr_map.get("data-original")
                or attr_map.get("data-lazy-src")
            )
            if src:
                self.media.append(
                    {
                        "kind": "image",
                        "url": urljoin(self.base_url, src),
                        "source": "img",
                        "text": attr_map.get("alt", ""),
                    }
                )
        elif tag == "link":
            href = attr_map.get("href")
            if href:
                abs_href = urljoin(self.base_url, href)
                kind = classify_url(abs_href, attr_map.get("type", ""))
                if kind in ("video", "image", "audio", "manifest"):
                    self.media.append(
                        {
                            "kind": kind,
                            "url": abs_href,
                            "source": "link[rel={}]".format(attr_map.get("rel", "")),
                            "text": "",
                        }
                    )
        elif tag == "script":
            script_src = attr_map.get("src")
            if script_src:
                self.script_urls.append(urljoin(self.base_url, script_src))
            self._collect_script = True
            self._script_type = attr_map.get("type", "").lower()
            self._script_parts = []
        elif tag == "a":
            href = attr_map.get("href")
            if href and not href.startswith(("javascript:", "mailto:", "tel:")):
                abs_href = urljoin(self.base_url, href)
                parsed = urlparse(abs_href)
                if parsed.scheme in ("http", "https") and parsed.netloc == urlparse(
                    self.base_url
                ).netloc:
                    self.links.append(abs_href)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.title = "".join(self._title_parts).strip()
            self._in_title = False
            self._title_parts = []
        elif tag == "h1":
            self.h1 = "".join(self._h1_parts).strip()
            self._in_h1 = False
            self._h1_parts = []
        elif tag == "script" and self._collect_script:
            text = "".join(self._script_parts)
            if "ld+json" in self._script_type:
                try:
                    self.json_ld.append(json.loads(text))
                except Exception:
                    pass
            self.inline_state.update(extract_inline_json(text))
            self._collect_script = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_h1:
            self._h1_parts.append(data)
        elif self._collect_script:
            self._script_parts.append(data)


def analyze_page(
    url: str,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout: float = 15.0,
    proxy: Optional[str] = None,
    max_bytes: int = 1_000_000,
    extra_headers: Optional[Dict[str, str]] = None,
    cookie: Optional[str] = None,
) -> Dict[str, Any]:
    response = fetch(
        url,
        user_agent,
        timeout,
        proxy,
        max_bytes,
        extra_headers=extra_headers,
        cookie=cookie,
    )
    page: Dict[str, Any] = {
        "url": url,
        "final_url": response["final_url"],
        "status": response["status"],
        "content_type": response["headers"].get("content-type", ""),
        "error": response["error"],
        "title": "",
        "h1": "",
        "meta": {},
        "json_ld": [],
        "media": [],
        "links": [],
        "script_urls": [],
        "inline_state_keys": [],
        "inline_state": {},
        "drama_name_candidates": [],
        "best_drama_name": "",
        "block_signals": [],
    }
    if response["error"] or response["status"] is None:
        return page

    parser = MediaPageParser(response["final_url"])
    parser.feed(response["body_text"])
    page["title"] = parser.title
    page["h1"] = parser.h1
    page["meta"] = parser.meta
    page["json_ld"] = parser.json_ld
    page["inline_state"] = parser.inline_state
    page["media"] = dedupe_media(
        parser.media
        + extract_media_from_json(parser.json_ld, response["final_url"])
        + extract_media_from_json(parser.inline_state, response["final_url"])
    )
    page["links"] = list(dict.fromkeys(parser.links))
    page["script_urls"] = list(dict.fromkeys(parser.script_urls))
    page["inline_state_keys"] = list(parser.inline_state.keys())
    page["drama_name_candidates"] = [
        candidate
        for candidate in (parser.h1, parser.meta.get("og:title", ""), parser.title)
        if candidate
    ]
    page["best_drama_name"] = clean_drama_name(
        parser.h1 or parser.meta.get("og:title", "") or parser.title
    )
    page["block_signals"] = detect_blocks(response)
    return page


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Deep media probe for a web page.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--proxy", default=None)
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="Extra request header; repeatable.",
    )
    parser.add_argument(
        "--cookie",
        default=None,
        help="Cookie header for an authorized session you already hold.",
    )
    parser.add_argument(
        "--cookies-file",
        default=None,
        help="JSON session file from session_capture.py or browser storage state.",
    )
    parser.add_argument("--max-bytes", type=int, default=1_000_000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    page = analyze_page(
        args.url,
        args.user_agent,
        args.timeout,
        args.proxy,
        args.max_bytes,
        parse_headers(args.header),
        args.cookie or load_cookie_header(args.cookies_file),
    )
    if args.json:
        print(json.dumps(page, ensure_ascii=False, indent=2))
    else:
        print("URL:", page["url"])
        print("Status:", page["status"], "Content-Type:", page["content_type"])
        print("Title:", page["title"])
        print("H1:", page["h1"])
        print("Best drama name:", page["best_drama_name"])
        print("Inline state keys:", ", ".join(page["inline_state_keys"]) or "none")
        print("Script bundles:", len(page["script_urls"]))
        for script_url in page["script_urls"][:5]:
            print("  ", script_url)
        print("Media found:", len(page["media"]))
        for item in page["media"][:20]:
            print(f"  [{item['kind']}] {item['source']} -> {item['url']}")
        if page["block_signals"]:
            print("Block signals:", ", ".join(s["type"] for s in page["block_signals"]))
        if page["error"]:
            print("Error:", page["error"])
    if page["block_signals"] or page["error"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
