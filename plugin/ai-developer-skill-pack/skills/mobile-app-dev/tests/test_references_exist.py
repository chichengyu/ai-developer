"""test_references_exist.py -- ensure documented relative paths resolve."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DOCS = (
    [ROOT / "SKILL.md", ROOT / "README.md"]
    + sorted((ROOT / "references").glob("*.md"))
    + sorted((ROOT / "templates").glob("*.md"))
    + sorted((ROOT / "examples").glob("*/README.md"))
)

PREFIXES = (
    "scripts/",
    "references/",
    "templates/",
    "examples/",
    "tests/",
    "agents/",
    "fixtures/",
    "mobile-app-dev/",
)
SKIP_CHARS = frozenset("*?<>\"'")


def _path_candidates(doc):
    text = doc.read_text(encoding="utf-8")
    for match in re.finditer(r"`([^`]+)`", text):
        raw = match.group(1).strip()
        rel = raw.split(" ")[0].rstrip(",.;:)]}")
        rel = rel.split("#", 1)[0]
        resolved = rel
        for prefix in PREFIXES:
            if rel.startswith(prefix):
                if prefix == "mobile-app-dev/":
                    resolved = rel[len(prefix):]
                break
        else:
            continue
        if any(ch in resolved for ch in SKIP_CHARS):
            continue
        yield resolved


def test_relative_paths_exist():
    missing = []
    for doc in DOCS:
        for rel in _path_candidates(doc):
            if not (ROOT / rel).exists():
                missing.append(f"{doc.relative_to(ROOT)} -> {rel}")
    assert not missing, "\n".join(missing)


if __name__ == "__main__":
    test_relative_paths_exist()
    print("[OK] documented relative paths resolve")
