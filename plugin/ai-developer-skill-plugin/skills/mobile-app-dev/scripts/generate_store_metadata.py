"""generate_store_metadata.py -- draft App Store / Play Store metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _comma_list(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value or "TBD")


def render_app_store(req: dict) -> str:
    meta = req.get("meta", {}) or {}
    functional = req.get("functional", {}) or {}
    compliance = req.get("compliance", {}) or {}
    name = meta.get("appName", "My App")
    return f"""# {name} - App Store metadata

- Subtitle: {name}
- Category: {req.get('category', 'Productivity')}
- Description: {functional.get('description', 'TBD')}
- Privacy nutrition labels drafted: {compliance.get('privacyLabels', 'no')}
- Required screenshots: 6.7in, 6.5in, 5.5in, iPad Pro 12.9in
- Notes: Replace with final marketing copy and localized strings.
"""


def render_play_store(req: dict) -> str:
    meta = req.get("meta", {}) or {}
    functional = req.get("functional", {}) or {}
    compliance = req.get("compliance", {}) or {}
    name = meta.get("appName", "My App")
    return f"""# {name} - Play Store metadata

- App name: {name}
- Short description: {functional.get('description', 'TBD')[:80]}
- Full description: {functional.get('description', 'TBD')}
- Data safety form drafted: {compliance.get('dataSafetyForm', 'no')}
- Content rating questionnaire: pending
- Required screenshots: phone 8-16:9, tablet 10in+
- Notes: Replace with final marketing copy and localized strings.
"""


def render_screenshots(req: dict) -> str:
    meta = req.get("meta", {}) or {}
    screens = req.get("functional", {}).get("screens", []) or []
    name = meta.get("appName", "My App")
    lines = [
        f"# {name} - screenshot plan",
        "",
        "Capture one image per primary screen on a mid-tier device:",
    ]
    lines.extend(f"- {screen}" for screen in screens)
    lines.extend(
        [
            "",
            "Include at least one screenshot showing offline or empty state.",
            "Keep text under 40% of the frame; do not add fake device bezels.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_privacy_labels(req: dict) -> str:
    integration = req.get("integration", {}) or {}
    compliance = req.get("compliance", {}) or {}
    frameworks = _comma_list(integration.get("frameworks"))
    return f"""# Privacy labels checklist

- Data collection documented: {compliance.get('privacyLabels', 'no')}
- Data safety form documented: {compliance.get('dataSafetyForm', 'no')}
- SDKs / frameworks to declare: {frameworks}
- App Tracking Transparency prompt needed: verify
- Account deletion flow needed: verify
- Export compliance / encryption: verify
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft store metadata from requirements.")
    parser.add_argument("--requirements", required=True, help="requirements.json path")
    parser.add_argument("--output-dir", default="store", help="output directory")
    args = parser.parse_args(argv)

    req = json.loads(Path(args.requirements).read_text(encoding="utf-8"))
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "app_store.md": render_app_store(req),
        "play_store.md": render_play_store(req),
        "screenshots.md": render_screenshots(req),
        "privacy_labels.md": render_privacy_labels(req),
    }
    for filename, content in files.items():
        (output / filename).write_bytes(content.encode("utf-8"))
        print(f"Wrote {output / filename}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
