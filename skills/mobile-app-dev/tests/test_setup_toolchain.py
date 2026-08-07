"""test_setup_toolchain.py -- toolchain planning smoke tests."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import setup_toolchain  # noqa: E402


def test_plan_flutter_toolchain():
    plan = setup_toolchain.plan_toolchain("flutter")
    assert plan["framework"] == "flutter"
    assert any(tool["name"] == "flutter" for tool in plan["tools"])
    assert plan["install_commands"]


def test_framework_key_maps_step15_result():
    assert setup_toolchain.framework_key("React Native") == "react-native"
    assert setup_toolchain.framework_key("Kotlin + Compose") == "compose"


def test_check_only_json_does_not_install():
    assert setup_toolchain.main(["--framework", "flutter", "--json"]) == 0


def test_requirements_auto_selects_toolchain():
    fixture = ROOT / "tests" / "fixtures" / "requirements.json"
    assert setup_toolchain.main(["--requirements", str(fixture), "--json"]) == 0


if __name__ == "__main__":
    test_plan_flutter_toolchain()
    test_framework_key_maps_step15_result()
    test_check_only_json_does_not_install()
    test_requirements_auto_selects_toolchain()
    print("[OK] setup_toolchain")
