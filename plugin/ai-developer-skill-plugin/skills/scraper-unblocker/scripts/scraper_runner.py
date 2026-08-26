#!/usr/bin/env python3
"""Concurrent, robots-aware crawler template with retries and JSONL output.

Stdlib-only. Safe by default: challenge and CAPTCHA pages are logged as BLOCKED
and never followed, and no access control is bypassed.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

from scraper_probe import load_cookie_header

DEFAULT_USER_AGENT = "scraper-unblocker-runner/1.0 (contact: replace-me@example.com)"

BLOCK_PATTERNS = {
    "challenge": [
        "just a moment",
        "checking your browser",
        "cf-chl",
        "cf-challenge",
        "attention required",
        "verify you are human",
        "captcha",
        "turnstile",
        "hcaptcha",
        "recaptcha",
        "perimeterx",
        "px-captcha",
        "kasada",
        "arkose",
        "intelligent tracking prevention",
    ],
    "waf": [
        "access denied",
        "request blocked",
        "sorry, you have been blocked",
        "incapsula",
        "akamai",
        "distil",
        "datadome",
        "sucuri",
        "imperva",
        "akamaighost",
        "shape security",
        "request rejected",
        "web application firewall",
    ],
    "js_required": [
        "please enable javascript",
        "javascript is required",
        "enable javascript and cookies",
        "javascript is disabled",
    ],
    "cookie_wall": [
        "accept cookies",
        "cookie settings",
        "your privacy",
        "consent",
    ],
}


class CrawlState:
    def __init__(self, args: argparse.Namespace) -> None:
        self.user_agent = args.user_agent
        self.timeout = args.timeout
        self.proxy = args.proxy
        self.extra_headers = args.extra_headers
        self.cookie = args.cookie
        self.max_retries = args.max_retries
        self.delay = args.delay
        self.max_depth = args.max_depth
        self.max_body_bytes = args.max_body_bytes
        self.save_body = args.save_body
        self.same_host_only = not args.no_same_host
        self.no_robots = args.no_robots
        self.seen: set[str] = set()
        self.robots_cache: Dict[str, str] = {}
        self.cache_lock = threading.Lock()
        self.rate_lock = threading.Lock()
        self.last_request = 0.0

    def throttle(self) -> None:
        with self.rate_lock:
            now = time.monotonic()
            wait_for = self.delay - (now - self.last_request)
            if wait_for > 0:
                time.sleep(wait_for)
            self.last_request = time.monotonic()


def build_opener(proxy: Optional[str]) -> urllib.request.OpenerDirector:
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    return urllib.request.build_opener()


def decode_body(body: bytes, content_type: str = "") -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charset = match.group(1) if match else "utf-8"
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_once(url: str, state: CrawlState) -> Dict[str, Any]:
    opener = build_opener(state.proxy)
    headers = {
        "User-Agent": state.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if state.cookie:
        headers["Cookie"] = state.cookie
    if state.extra_headers:
        headers.update(state.extra_headers)
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    result = {
        "requested_url": url,
        "status": None,
        "final_url": url,
        "headers": {},
        "body_bytes": 0,
        "body_text": "",
        "error": None,
    }
    try:
        with opener.open(request, timeout=state.timeout) as response:
            result["status"] = response.status
            result["final_url"] = response.geturl()
            result["headers"] = {k.lower(): v for k, v in response.headers.items()}
            body = response.read(state.max_body_bytes + 1)
            result["body_bytes"] = len(body)
            result["body_text"] = decode_body(
                body, result["headers"].get("content-type", "")
            )
    except urllib.error.HTTPError as exc:
        result["status"] = exc.code
        result["final_url"] = exc.geturl() or url
        result["headers"] = {k.lower(): v for k, v in exc.headers.items()}
        body = exc.read(state.max_body_bytes + 1)
        result["body_bytes"] = len(body)
        result["body_text"] = decode_body(body, result["headers"].get("content-type", ""))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def parse_robots(text: str) -> Dict[str, Any]:
    rules: Dict[str, List[Tuple[bool, str]]] = {}
    crawl_delays: Dict[str, float] = {}
    current: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current = value.lower()
            rules.setdefault(current, [])
        elif key in ("disallow", "allow") and current is not None:
            rules[current].append((key == "allow", value))
        elif key == "crawl-delay" and current is not None:
            try:
                crawl_delays[current] = float(value)
            except ValueError:
                pass
    return {"rules": rules, "crawl_delays": crawl_delays}


def robots_path_allowed(path: str, pattern: str) -> bool:
    if not pattern:
        return True
    regex = re.escape(pattern).replace(r"\*", ".*")
    if pattern.endswith("$"):
        regex = regex[:-2] + "$"
    return re.match(regex, path) is not None


def robots_allowed(
    url: str, user_agent: str, robots_text: str
) -> Tuple[bool, str, Optional[float]]:
    parsed = parse_robots(robots_text)
    url_parts = urllib.parse.urlparse(url)
    target = (url_parts.path or "/") + (("?" + url_parts.query) if url_parts.query else "")
    for agent in (user_agent.lower(), "*"):
        if agent not in parsed["rules"]:
            continue
        for is_allow, pattern in parsed["rules"][agent]:
            if robots_path_allowed(target, pattern):
                return is_allow, ("Allow " if is_allow else "Disallow ") + pattern, parsed[
                    "crawl_delays"
                ].get(agent)
    return True, "no matching robots rule", None


def robots_allowed_cached(state: CrawlState, url: str) -> Tuple[bool, str]:
    if state.no_robots:
        return True, "robots check disabled"
    parts = urlparse(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    with state.cache_lock:
        text = state.robots_cache.get(origin)
    if text is None:
        state.throttle()
        robots_resp = fetch_once(origin + "/robots.txt", state)
        text = robots_resp["body_text"] if robots_resp["status"] == 200 else ""
        with state.cache_lock:
            state.robots_cache[origin] = text
    allowed, rule, _ = robots_allowed(url, state.user_agent, text)
    return allowed, rule


def retry_after_seconds(response: Dict[str, Any], fallback: float) -> float:
    value = response["headers"].get("retry-after", "")
    if value.isdigit():
        return float(value)
    return fallback


def detect_block(
    status: Optional[int], headers: Dict[str, str], body_text: str
) -> Optional[str]:
    if status in (401, 403):
        return f"http_{status}"
    body = body_text.lower()
    server = headers.get("server", "").lower()
    if "cloudflare" in server or any(key.startswith("cf-") for key in headers):
        return "cloudflare"
    for kind, patterns in BLOCK_PATTERNS.items():
        for pattern in patterns:
            if pattern in body:
                return kind
    return None


def fetch_with_retries(url: str, state: CrawlState) -> Dict[str, Any]:
    last: Dict[str, Any] = {}
    for attempt in range(state.max_retries):
        response = fetch_once(url, state)
        last = response
        if response["error"]:
            time.sleep(min(8.0, 2**attempt + random.random()))
            continue
        if response["status"] in (429, 503) and not detect_block(
            response["status"], response["headers"], response["body_text"]
        ):
            time.sleep(retry_after_seconds(response, min(8.0, 2**attempt)))
            continue
        return response
    return last


def normalize_url(url: str) -> str:
    parts = urlparse(url)
    if parts.scheme.lower() not in ("http", "https"):
        return url
    return urlunparse(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            parts.params,
            parts.query,
            "",
        )
    )


class LinkParser(HTMLParser):
    def __init__(self, base_url: str, same_host_only: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.same_host_only = same_host_only
        self.links: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attr_map = {key.lower(): value for key, value in attrs if value is not None}
        if tag == "base" and attr_map.get("href"):
            self.base_url = urljoin(self.base_url, attr_map["href"])
        elif tag == "a" and attr_map.get("href"):
            href = attr_map["href"].strip()
            if not href or href.startswith(("javascript:", "mailto:", "tel:", "#")):
                return
            target = urljoin(self.base_url, href)
            if self.same_host_only and urlparse(target).netloc.lower() != urlparse(
                self.base_url
            ).netloc.lower():
                return
            self.links.append(normalize_url(target))


def extract_links(html: str, base_url: str, same_host_only: bool) -> List[str]:
    parser = LinkParser(base_url, same_host_only)
    try:
        parser.feed(html)
    except Exception:
        return []
    return parser.links


def process_url(state: CrawlState, url: str, depth: int) -> Dict[str, Any]:
    state.throttle()
    result: Dict[str, Any] = {
        "url": url,
        "depth": depth,
        "final_url": None,
        "status": None,
        "content_type": None,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "block": None,
        "error": None,
        "links": [],
        "body": None,
    }

    allowed, rule = robots_allowed_cached(state, url)
    if not allowed:
        result["error"] = f"blocked by robots.txt: {rule}"
        return result

    response = fetch_with_retries(url, state)
    result["final_url"] = response["final_url"]
    result["status"] = response["status"]
    result["content_type"] = response["headers"].get("content-type")
    if response["error"]:
        result["error"] = response["error"]
        return result
    if response["status"] in (429, 503):
        result["error"] = f"unavailable after retries: HTTP {response['status']}"
        return result

    block = detect_block(response["status"], response["headers"], response["body_text"])
    if block:
        result["block"] = block
        result["error"] = f"BLOCKED: {block}"
        return result

    result["links"] = extract_links(
        response["body_text"], response["final_url"], state.same_host_only
    )
    if state.save_body:
        result["body"] = response["body_text"][: state.max_body_bytes]
    return result


def crawl(args: argparse.Namespace) -> None:
    state = CrawlState(args)
    start = normalize_url(args.start_url)
    if urlparse(start).scheme not in ("http", "https"):
        raise SystemExit("--start-url must be an http(s) URL")
    state.seen.add(start)
    fetched = 0

    with open(args.output, "w", encoding="utf-8") as out:
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = {pool.submit(process_url, state, start, 0): (start, 0)}
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    url, depth = futures.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {
                            "url": url,
                            "depth": depth,
                            "final_url": None,
                            "status": None,
                            "content_type": None,
                            "fetched_at": datetime.now(timezone.utc).isoformat(),
                            "block": None,
                            "error": f"{type(exc).__name__}: {exc}",
                            "links": [],
                            "body": None,
                        }
                    out.write(json.dumps(result, ensure_ascii=False) + "\n")
                    out.flush()
                    fetched += 1
                    if fetched >= args.max_pages:
                        continue
                    if result.get("block") or result.get("error"):
                        continue
                    if depth + 1 >= state.max_depth:
                        continue
                    for link in result["links"]:
                        if link in state.seen:
                            continue
                        if len(futures) + fetched >= args.max_pages:
                            continue
                        state.seen.add(link)
                        futures[pool.submit(process_url, state, link, depth + 1)] = (
                            link,
                            depth + 1,
                        )

    print(f"Fetched {fetched} pages; results written to {args.output}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Robots-aware concurrent crawler with retries and JSONL output."
    )
    parser.add_argument("--start-url", required=True, help="Seed URL to crawl.")
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--delay", type=float, default=0.5, help="Global minimum delay between requests.")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
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
    parser.add_argument("--max-retries", type=int, default=3, help="Retry attempts for transient failures.")
    parser.add_argument("--output", default="crawl.jsonl")
    parser.add_argument("--save-body", action="store_true", help="Store truncated HTML in output.")
    parser.add_argument("--max-body-bytes", type=int, default=100_000)
    parser.add_argument("--no-robots", action="store_true", help="Disable robots.txt checks.")
    parser.add_argument("--no-same-host", action="store_true", help="Allow off-site links.")
    args = parser.parse_args(argv)

    if args.concurrency < 1 or args.max_pages < 1 or args.delay < 0:
        parser.error("concurrency must be >= 1, max-pages >= 1, delay >= 0")

    extra_headers: Dict[str, str] = {}
    for item in args.header:
        if ":" in item:
            key, _, value = item.partition(":")
            extra_headers[key.strip()] = value.strip()
    args.extra_headers = extra_headers
    args.cookie = args.cookie or load_cookie_header(args.cookies_file)

    crawl(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
