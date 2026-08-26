#!/usr/bin/env python3
"""Verify the canonical VK table against every Windows language template.

Run:
    python scripts/check_vk_tables.py

`scripts/vk_table.json` is the canonical key set for the skill's keyboard
templates. The Python reference must match exactly; the other Windows
templates must at least expose every canonical special key.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "vk_table.json"
PYTHON_PATH = ROOT / "sendinput_python.py"

WINDOWS_TEMPLATES = [
    "sendinput_python.py",
    "sendinput_win32.c",
    "sendinput_dotnet.cs",
    "SendInput.java",
    "sendinput_rust.rs",
    "sendinput_go.go",
    "sendinput_dart.dart",
    "sendinput_node.ts",
    "sendinput_swift.swift",
    "sendinput_kotlin.kt",
]

SWIFT_ALIAS = {
    "back": "backspace",
    "esc": "escape",
    "pageup": "pageUp",
    "pagedown": "pageDown",
    "lshift": "lShift",
    "rshift": "rShift",
    "lctrl": "lCtrl",
    "rctrl": "rCtrl",
    "lalt": "lAlt",
    "ralt": "rAlt",
    "lwin": "lWin",
    "rwin": "rWin",
}


def generated_keys() -> set[str]:
    return (
        {chr(c) for c in range(ord("a"), ord("z") + 1)}
        | {str(d) for d in range(10)}
        | {f"f{i}" for i in range(1, 25)}
        | {f"num{i}" for i in range(10)}
    )


def has_key(text: str, lang: str, key: str) -> bool:
    if lang == "csharp":
        return re.search(rf"['\"]{re.escape(key.upper())}['\"]", text, re.IGNORECASE) is not None
    if lang == "node":
        return re.search(rf"\b{re.escape(key)}\b\s*:", text) is not None
    if lang == "swift":
        name = SWIFT_ALIAS.get(key, key)
        return re.search(rf"\b{re.escape(name)}\b", text) is not None
    return re.search(rf"['\"]{re.escape(key)}['\"]", text) is not None


def load_python_vk() -> dict[str, int]:
    spec = importlib.util.spec_from_file_location("sendinput_python", PYTHON_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {PYTHON_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.VK)


def main() -> int:
    canonical = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    python_vk = load_python_vk()
    failures = 0
    for key in sorted(set(canonical) | set(python_vk)):
        if key not in canonical:
            print(f"  [FAIL] {key}: missing from vk_table.json")
            failures += 1
        elif key not in python_vk:
            print(f"  [FAIL] {key}: missing from sendinput_python.py")
            failures += 1
        elif canonical[key] != python_vk[key]:
            print(f"  [FAIL] {key}: json={canonical[key]} python={python_vk[key]}")
            failures += 1

    special = [k for k in canonical if k not in generated_keys()]
    for name in WINDOWS_TEMPLATES:
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        lang = {
            "sendinput_dotnet.cs": "csharp",
            "sendinput_node.ts": "node",
            "sendinput_swift.swift": "swift",
        }.get(name, "quoted")
        missing = [k for k in special if not has_key(text, lang, k)]
        if missing:
            print(f"  [FAIL] {name}: missing special keys: {', '.join(missing)}")
            failures += len(missing)

    if canonical.get("f1") != 0x70 or canonical.get("f24") != 0x87:
        print("  [FAIL] vk_table.json F-key range must be VK_F1 (0x70) to VK_F24 (0x87)")
        failures += 1
    f_key_patterns = {
        "sendinput_python.py": r"0x70\s*\+\s*i\s*-\s*1",
        "sendinput_dotnet.cs": r"0x70\s*\+\s*i\s*-\s*1",
        "SendInput.java": r"0x70\s*\+\s*i\s*-\s*1",
        "sendinput_rust.rs": r"0x70\s*\+\s*i\s*-\s*1",
        "sendinput_go.go": r"0x70\s*\+\s*i\s*-\s*1",
        "sendinput_dart.dart": r"0x70\s*\+\s*i\s*-\s*1",
        "sendinput_node.ts": r"0x70\s*\+\s*i\s*-\s*1",
        "sendinput_swift.swift": r"0x70\s*\+\s*n\s*-\s*1",
        "sendinput_kotlin.kt": r"0x70\s*\+\s*it\s*-\s*1",
        "sendinput_win32.c": r"VK_F1\s*\+\s*n\s*-\s*1",
    }
    for name, pattern in f_key_patterns.items():
        if not re.search(pattern, (ROOT / name).read_text(encoding="utf-8")):
            print(f"  [FAIL] {name}: F-key mapping must start at VK_F1 (0x70)")
            failures += 1

    if failures:
        print(f"\n{failures} VK mismatch(es).")
        return 1
    print(f"VK table OK ({len(canonical)} keys, {len(WINDOWS_TEMPLATES)} templates).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
