"""test_no_bom.py -- fail if a text file starts with a BOM or embeds U+FEFF."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_SUFFIXES = {
    ".md", ".py", ".ps1", ".kt", ".dart", ".tsx", ".swift", ".xml",
    ".yaml", ".yml", ".kts", ".toml", ".json", ".js",
}
TEXT_NAMES = {".gitignore"}

BOMS = {
    "utf-8": b"\xef\xbb\xbf",
    "utf-16-le": b"\xff\xfe",
    "utf-16-be": b"\xfe\xff",
    "utf-32-le": b"\xff\xfe\x00\x00",
    "utf-32-be": b"\x00\x00\xfe\xff",
}


def _iter_text_files():
    for path in ROOT.rglob("*"):
        if ".git" in path.parts:
            continue
        if path.is_file() and (path.suffix.lower() in TEXT_SUFFIXES or path.name in TEXT_NAMES):
            yield path


def test_no_bom_at_start():
    bad = []
    for path in _iter_text_files():
        data = path.read_bytes()
        for encoding, signature in BOMS.items():
            if data.startswith(signature):
                bad.append(f"{path.relative_to(ROOT)} starts with {encoding} BOM")
                break
    assert not bad, "\n".join(bad)


def test_no_embedded_bom():
    bad = []
    for path in _iter_text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "\ufeff" in text:
            bad.append(str(path.relative_to(ROOT)))
    assert not bad, "files contain U+FEFF: " + ", ".join(bad)


if __name__ == "__main__":
    test_no_bom_at_start()
    test_no_embedded_bom()
    print("[OK] no BOM or U+FEFF in text files")
