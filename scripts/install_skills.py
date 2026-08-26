#!/usr/bin/env python3
"""Universal desktop-agent skills installer for ai-developer."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


SKILL_SOURCES = (
    "skills/skills",
    "plugin/ai-developer-skill-plugin/skills",
)

KNOWN_AGENTS = {
    "codex": ".codex/skills",
    "claude": ".claude/skills",
    "opencode": ".config/opencode/skills",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_skill_source(root: Path) -> Path:
    for relative in SKILL_SOURCES:
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"skills pack not found under {root}")


def detect_targets(home: Path) -> list[tuple[str, Path]]:
    detected: list[tuple[str, Path]] = []
    for name, relative in KNOWN_AGENTS.items():
        target = home / relative
        marker = home / (".codex" if name == "codex" else ".claude" if name == "claude" else ".config/opencode")
        if marker.exists():
            detected.append((name, target))
    return detected


def install_skills(source: Path, target: Path) -> list[str]:
    target.mkdir(parents=True, exist_ok=True)
    installed: list[str] = []
    for skill in sorted(item for item in source.iterdir() if item.is_dir()):
        if skill.name.startswith("."):
            continue
        shutil.copytree(skill, target / skill.name, dirs_exist_ok=True)
        installed.append(skill.name)
    return installed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install the ai-developer skills into desktop agent skill directories."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Install into every known desktop agent regardless of local detection.",
    )
    parser.add_argument(
        "--detect",
        action="store_true",
        help="Install into locally detected agents (default behavior).",
    )
    parser.add_argument(
        "--agent",
        action="append",
        choices=sorted(KNOWN_AGENTS),
        help="Install into a named agent. May be repeated.",
    )
    parser.add_argument(
        "--dest",
        help="Install into a custom agent skills directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the installation plan without copying files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = repo_root()
    source = find_skill_source(root)
    home = Path.home()

    targets: list[tuple[str, Path]] = []
    if args.agent:
        for name in args.agent:
            targets.append((name, home / KNOWN_AGENTS[name]))
    elif args.all:
        targets = [(name, home / relative) for name, relative in KNOWN_AGENTS.items()]
    else:
        targets = detect_targets(home)

    if args.dest:
        targets.append(("custom", Path(args.dest).expanduser()))

    if not targets:
        print(
            "No desktop agent skill directories detected. "
            "Use --all or --dest <agent-skills-directory> to install explicitly."
        )
        raise SystemExit(1)

    for name, target in targets:
        if args.dry_run:
            print(f"[{name}] would install into {target}")
            continue
        installed = install_skills(source, target)
        print(f"[{name}] installed {len(installed)} skills into {target}")
        for skill in installed:
            print(f"  - {skill}")


if __name__ == "__main__":
    main()
