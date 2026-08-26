"""test_plan_project.py -- requirements and task generation smoke tests."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import plan_project  # noqa: E402


def test_plan_generates_requirements_and_tasks(tmp_path):
    fixture = ROOT / "tests" / "fixtures" / "requirements.json"
    plan_project.main(
        ["--requirements", str(fixture), "--output-dir", str(tmp_path)]
    )
    requirements = tmp_path / "requirements.md"
    tasks = tmp_path / "tasks.md"
    assert requirements.exists()
    assert tasks.exists()
    assert "Step 1.5 result" in requirements.read_text(encoding="utf-8")
    assert "T-011" in tasks.read_text(encoding="utf-8")
    assert "React Native" in requirements.read_text(encoding="utf-8")


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_plan_generates_requirements_and_tasks(Path(tmp))
    print("[OK] plan_project")
