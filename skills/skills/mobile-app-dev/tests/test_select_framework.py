"""test_select_framework.py -- Step 1.5 decision tree smoke tests."""

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from select_framework import select_framework  # noqa: E402


def test_ios_utility_defaults_to_swiftui():
    result = select_framework(
        {
            "category": "A",
            "platforms": ["ios"],
            "teamProfile": {"languages": ["Swift"]},
            "integration": {"frameworks": []},
        }
    )
    assert result["selected_framework"] == "Swift + SwiftUI"
    assert result["confidence"] == "HIGH"


def test_web_first_both_platforms_selects_react_native():
    result = select_framework(
        {
            "category": "B",
            "platforms": ["ios", "android"],
            "teamProfile": {
                "languages": ["TypeScript"],
                "existingCodebases": ["React", "web"],
            },
            "integration": {"frameworks": []},
        }
    )
    assert result["selected_framework"] == "React Native"
    assert result["confidence"] == "MEDIUM"


def test_hardware_crypto_selects_two_native_codebases():
    result = select_framework(
        {
            "category": "F",
            "platforms": ["ios", "android"],
            "teamProfile": {"languages": ["Swift", "Kotlin"]},
            "integration": {"frameworks": ["Secure Enclave", "StrongBox"]},
        }
    )
    assert result["selected_framework"] == (
        "Swift + SwiftUI (iOS) + Kotlin + Compose (Android)"
    )
    assert result["confidence"] == "HIGH"


def test_watch_healthkit_selects_swiftui():
    result = select_framework(
        {
            "category": "F",
            "platforms": ["watchos"],
            "teamProfile": {"languages": ["Swift"]},
            "integration": {"frameworks": ["HealthKit", "Watch face"]},
        }
    )
    assert result["selected_framework"] == "Swift + SwiftUI"


def test_android_only_defaults_to_compose():
    result = select_framework(
        {
            "category": "A",
            "platforms": ["android"],
            "teamProfile": {"languages": ["Kotlin"]},
            "integration": {"frameworks": []},
        }
    )
    assert result["selected_framework"] == "Kotlin + Compose"


def test_game_category_is_out_of_scope():
    result = select_framework(
        {
            "category": "D",
            "platforms": ["ios", "android"],
            "teamProfile": {"languages": []},
            "integration": {"frameworks": []},
        }
    )
    assert result["out_of_scope"] is True
    assert "Game engine" in result["selected_framework"]


if __name__ == "__main__":
    test_ios_utility_defaults_to_swiftui()
    test_web_first_both_platforms_selects_react_native()
    test_hardware_crypto_selects_two_native_codebases()
    test_watch_healthkit_selects_swiftui()
    test_android_only_defaults_to_compose()
    test_game_category_is_out_of_scope()
    print("[OK] select_framework decision tree")
