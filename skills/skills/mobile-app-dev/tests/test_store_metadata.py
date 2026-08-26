"""test_store_metadata.py -- store metadata generator smoke tests."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import generate_store_metadata  # noqa: E402


def test_store_metadata_generates_all_files(tmp_path):
    fixture = ROOT / "tests" / "fixtures" / "requirements.json"
    generate_store_metadata.main(
        ["--requirements", str(fixture), "--output-dir", str(tmp_path)]
    )
    for filename in ("app_store.md", "play_store.md", "screenshots.md", "privacy_labels.md"):
        assert (tmp_path / filename).exists()
    assert "Privacy labels" in (tmp_path / "privacy_labels.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_store_metadata_generates_all_files(Path(tmp))
    print("[OK] generate_store_metadata")
