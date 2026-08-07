"""test_plist_parse.py -- verify the fixture Info.plist is well-formed."""

import xml.etree.ElementTree as ET
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "Info.plist.xml"


def test_plist_parses():
    tree = ET.parse(FIXTURE)
    root = tree.getroot()
    assert root.tag == "plist", f"expected plist root, got {root.tag}"
    assert root.get("version") == "1.0"

    # Find the dict
    dict_elem = root.find("dict")
    assert dict_elem is not None, "plist must have a dict child"

    # Verify a few known keys exist
    keys = {key.text for key in dict_elem.findall("key")}
    assert "CFBundleIdentifier" in keys
    assert "CFBundleVersion" in keys
    assert "LSRequiresIPhoneOS" in keys


if __name__ == "__main__":
    test_plist_parses()
    print("[OK] fixtures/Info.plist.xml is well-formed")