#!/usr/bin/env python3
"""Structural doc audit for the skill.

Checks the SKILL.md frontmatter, duplicate-section regression, relative
Markdown references, and the canonical file counts advertised in docs.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def main() -> int:
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines()
    check(skill[0] == "---", "SKILL.md must start with YAML frontmatter")
    check(
        skill[2].startswith('description: "') and skill[2].endswith('"'),
        "SKILL.md description must be a quoted single-line YAML scalar",
    )
    check(
        sum(1 for line in skill if line.startswith("## Tests (fixtures + smoke tests + CI)")) == 1,
        "SKILL.md must contain exactly one Tests heading",
    )

    for md in ROOT.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        for match in re.finditer(r"`([^`]+)`", text):
            ref = match.group(1).strip()
            if not ref.startswith(
                ("scripts/", "templates/", "examples/", "references/", "tests/", ".github/")
            ):
                continue
            if any(ch in ref for ch in "*<>[]{}|...") or "<lang>" in ref:
                continue
            if not (ROOT / ref).exists():
                check(False, f"missing relative reference: {ref} in {md.relative_to(ROOT)}")

    examples = [p for p in (ROOT / "examples").iterdir() if p.is_dir()]
    build_ps1 = list((ROOT / "scripts").glob("build_*.ps1"))
    threading = list((ROOT / "scripts").glob("threading_*"))
    sendinput = list((ROOT / "scripts").glob("sendinput_*"))
    window_enum = list((ROOT / "scripts").glob("window_enum*"))
    check(len(examples) == 8, f"examples count = {len(examples)}, expected 8")
    check(len(build_ps1) == 14, f"build_*.ps1 count = {len(build_ps1)}, expected 14")
    check(len(threading) == 7, f"threading_* count = {len(threading)}, expected 7")
    check(len(sendinput) == 11, f"sendinput_* count = {len(sendinput)}, expected 11")
    check(len(window_enum) == 11, f"window_enum* count = {len(window_enum)}, expected 11")

    if FAILURES:
        print("Doc audit failed:")
        for item in FAILURES:
            print(f"  - {item}")
        return 1
    print("Doc audit OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
