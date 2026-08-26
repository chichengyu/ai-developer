#!/usr/bin/env python3
"""Generate or edit images through the Doubao Seedream image API."""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_API_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-5-0-pro-260628"


def mime_for(path):
    suffix = Path(path).suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
        ".gif": "image/gif",
    }.get(suffix, "image/png")


def load_image_arg(value):
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(f"image not found: {path}")
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime_for(path)};base64,{encoded}"


def build_payload(args):
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
        "output_format": args.output_format,
        "response_format": "b64_json",
        "watermark": args.watermark,
        "optimize_prompt_options": {"mode": args.optimize},
    }
    if args.image:
        images = [load_image_arg(item) for item in args.image]
        payload["image"] = images[0] if len(images) == 1 else images
    if args.sequential_max:
        payload["sequential_image_generation"] = "auto"
        payload["sequential_image_generation_options"] = {"max_images": args.sequential_max}
    return payload


def call_api(payload, api_key, api_url):
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def save_item(item, output_path):
    if item.get("b64_json"):
        output_path.write_bytes(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        urllib.request.urlretrieve(item["url"], output_path)
    else:
        raise RuntimeError("api response has neither b64_json nor url")
    return output_path


def main(argv):
    parser = argparse.ArgumentParser(
        description="Generate or edit images with Doubao Seedream. Set ARK_API_KEY to use it."
    )
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--image", action="append", help="Reference image path/URL; repeat for multi-image.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--size", default="2K", choices=["1K", "1.5K", "2K"])
    parser.add_argument("--output-format", default="png", choices=["png", "jpeg"])
    parser.add_argument("--optimize", default="standard", choices=["standard", "fast"])
    parser.add_argument("--watermark", action="store_true")
    parser.add_argument("--sequential-max", type=int, help="Only for Seedream lite group generation.")
    parser.add_argument("--output", required=True)
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    args = parser.parse_args(argv)

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        print("error: ARK_API_KEY is not set", file=sys.stderr)
        return 2

    payload = build_payload(args)
    try:
        result = call_api(payload, api_key, args.api_url)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"api error {exc.code}: {body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"api error: {exc}", file=sys.stderr)
        return 1

    items = result.get("data", [])
    if not items:
        print("api error: no data in response", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    if len(items) > 1 or args.sequential_max:
        if output_path.suffix:
            print("error: multiple images require --output to be a directory", file=sys.stderr)
            return 2
        output_path.mkdir(parents=True, exist_ok=True)
        saved = []
        for index, item in enumerate(items):
            target = output_path / f"result_{index + 1:02d}.{args.output_format}"
            save_item(item, target)
            saved.append(target)
    else:
        if output_path.suffix:
            target = output_path
        else:
            output_path.mkdir(parents=True, exist_ok=True)
            target = output_path / f"result.{args.output_format}"
        target.parent.mkdir(parents=True, exist_ok=True)
        save_item(items[0], target)
        saved = [target]

    for path in saved:
        print(f"wrote: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
