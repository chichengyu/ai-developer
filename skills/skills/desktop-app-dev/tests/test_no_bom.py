#!/usr/bin/env python3
"""Regression guard: no UTF-8 BOM or U+FEFF bytes in skill text files."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "node_modules",
    "target",
    "__pycache__",
}


def main() -> int:
    bad: list[tuple[str, str]] = []
    checked = 0
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        raw = path.read_bytes()
        if b"\x00" in raw:
            continue
        checked += 1
        if raw.startswith(b"\xef\xbb\xbf"):
            bad.append((str(rel), "starts with UTF-8 BOM"))
        elif b"\xef\xbb\xbf" in raw:
            bad.append((str(rel), "contains U+FEFF"))

    if bad:
        print(f"BOM/U+FEFF audit failed ({checked} files checked):")
        for name, kind in bad:
            print(f"  {kind}: {name}")
        return 1
    print(f"BOM/U+FEFF audit OK ({checked} files checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
