"""test_requirements_parse.py -- verify the fixture requirements.json
matches the schema implied by templates/requirements_checklist.md."""

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "requirements.json"

REQUIRED_KEYS = {
    "meta", "functional", "nonFunctional", "distribution",
    "integration", "failureModes", "compliance", "ops",
    "teamProfile", "category", "showstoppers",
}


def test_requirements_complete():
    data = json.loads(FIXTURE.read_text())
    missing = REQUIRED_KEYS - set(data.keys())
    assert not missing, f"missing keys: {missing}"

    # Category must be one of A-H
    assert data["category"] in set("ABCDEFGH"), f"bad category: {data['category']}"

    # Showstoppers is a list of strings
    assert isinstance(data["showstoppers"], list)
    for item in data["showstoppers"]:
        assert isinstance(item, str)


if __name__ == "__main__":
    test_requirements_complete()
    print("[OK] fixtures/requirements.json is complete and valid")
