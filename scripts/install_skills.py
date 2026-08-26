#!/usr/bin/env python3
"""Universal desktop-agent skills installer for ai-developer."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


SKILL_SOURCES = (
    "skills/skills",
    "plugin/ai-developer-skill-plugin/skills",
)

AGENT_PATHS = {
    "codex": (".codex", "skills"),
    "claude": (".claude", "skills"),
    "cursor": (".cursor", "skills"),
    "gemini": (".gemini", "skills"),
    "opencode": (".config", "opencode/skills"),
}

AGENT_MARKERS = {
    "codex": ".codex",
    "claude": ".claude",
    "cursor": ".cursor",
    "gemini": ".gemini",
    "opencode": ".config/opencode",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def find_skill_source(root: Path) -> Path:
    for relative in SKILL_SOURCES:
        candidate = root / relative
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"skills pack not found under {root}")


def agent_target(home: Path, name: str) -> Path:
    relative_root, relative_tail = AGENT_PATHS[name]
    if name == "opencode" and os.environ.get("XDG_CONFIG_HOME"):
        return Path(os.environ["XDG_CONFIG_HOME"]) / "opencode" / "skills"
    return home / relative_root / relative_tail


def detect_targets(home: Path) -> list[tuple[str, Path]]:
    detected: list[tuple[str, Path]] = []
    for name in AGENT_PATHS:
        target = agent_target(home, name)
        marker = home / AGENT_MARKERS[name]
        if marker.exists() or target.exists():
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
        "--agent",
        action="append",
        choices=sorted(AGENT_PATHS),
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
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print supported desktop agents and their skill directories.",
    )
    parser.add_argument(
        "--source",
        help="Override the skills source directory.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = repo_root()
    home = Path.home()

    if args.list:
        for name in AGENT_PATHS:
            print(f"{name}: {agent_target(home, name)}")
        return

    if args.source:
        source = Path(args.source).expanduser()
        if not source.is_absolute():
            source = root / source
        source = source.resolve()
    else:
        source = find_skill_source(root)
    if not source.is_dir():
        raise SystemExit(f"skills source not found: {source}")

    targets: list[tuple[str, Path]] = []
    if args.agent:
        for name in args.agent:
            targets.append((name, agent_target(home, name)))
    elif args.all:
        targets = [(name, agent_target(home, name)) for name in AGENT_PATHS]
    elif args.dest:
        targets = []
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

    failures = 0
    for name, target in targets:
        if args.dry_run:
            print(f"[{name}] would install into {target}")
            continue
        try:
            installed = install_skills(source, target)
        except OSError as error:
            failures += 1
            print(f"[{name}] failed: {error}", file=sys.stderr)
            continue
        print(f"[{name}] installed {len(installed)} skills into {target}")
        for skill in installed:
            print(f"  - {skill}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
