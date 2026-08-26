#!/usr/bin/env python3
"""Enforce the 10-step approval gates recorded in STATE.md.

Usage:
    python approval_gate.py <project_dir> --step N --action check
    python approval_gate.py <project_dir> --step N --action approve
    python approval_gate.py <project_dir> --step N --action revise
    python approval_gate.py <project_dir> --step N --action show

`check` exits 0 only when STATE.md records `step_<N>_approved: yes`.
`approve` marks the step approved and advances the state.
`revise` marks the step not approved and keeps it as the next pending step.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Optional


def find_state(project: Path) -> Optional[Path]:
    current = project
    while current != current.parent:
        candidate = current / "STATE.md"
        if candidate.exists():
            return candidate
        current = current.parent
    return None


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()


def write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_field(lines: list[str], key: str, value: str) -> bool:
    pattern = re.compile(r"^\- " + re.escape(key) + r":\s*")
    for idx, line in enumerate(lines):
        if pattern.match(line):
            lines[idx] = f"- {key}: {value}"
            return True
    return False


def ensure_step_field(lines: list[str], step: int, value: str) -> None:
    key = f"step_{step}_approved"
    if not set_field(lines, key, value):
        anchor = next((idx for idx, line in enumerate(lines) if line.startswith("- next_pending_step:")), None)
        line = f"- {key}: {value}"
        if anchor is not None:
            lines.insert(anchor, line)
        else:
            lines.append(line)


def state_value(lines: list[str], key: str) -> Optional[str]:
    pattern = re.compile(r"^\- " + re.escape(key) + r":\s*(\S+)\s*$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1)
    return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Enforce the 10-step approval gates.")
    parser.add_argument("project_dir", type=Path)
    parser.add_argument("--step", type=int, required=True, choices=range(0, 10))
    parser.add_argument("--action", choices=("check", "approve", "revise", "show"), required=True)
    args = parser.parse_args(argv)

    state_path = find_state(args.project_dir)
    if args.action == "check" and state_path is None:
        print(f"approval gate: STATE.md not found for {args.project_dir}; step {args.step} is not approved")
        return 1
    if args.action in ("approve", "revise") and state_path is None:
        state_path = args.project_dir / "STATE.md"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"# STATE",
            f"- last_completed_step: {args.step if args.action == 'approve' else 'none'}",
            f"- next_pending_step: {args.step + 1 if args.action == 'approve' else args.step}",
            f"- step_{args.step}_approved: {'yes' if args.action == 'approve' else 'no'}",
        ]
        write_lines(state_path, lines)
        print(f"approval gate: step {args.step} marked {args.action}")
        return 0

    assert state_path is not None
    lines = read_lines(state_path)
    current = state_value(lines, f"step_{args.step}_approved")

    if args.action == "show" or args.action == "check":
        print(f"approval gate: step {args.step} = {current or 'not recorded'}")
        if args.action == "check":
            return 0 if current == "yes" else 1
        return 0

    if args.action == "approve":
        ensure_step_field(lines, args.step, "yes")
        set_field(lines, "last_completed_step", str(args.step))
        set_field(lines, "next_pending_step", str(args.step + 1))
        write_lines(state_path, lines)
        print(f"approval gate: step {args.step} approved; next pending step {args.step + 1}")
        return 0

    ensure_step_field(lines, args.step, "no")
    set_field(lines, "next_pending_step", str(args.step))
    write_lines(state_path, lines)
    print(f"approval gate: step {args.step} marked revise; next pending step remains {args.step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
