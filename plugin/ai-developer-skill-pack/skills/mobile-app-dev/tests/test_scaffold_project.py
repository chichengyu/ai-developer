"""test_scaffold_project.py -- scaffold generator smoke tests."""

from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from scaffold_project import scaffold  # noqa: E402


def test_flutter_scaffold(tmp_path):
    root = scaffold("flutter", tmp_path / "flutter", "MyApp")
    assert (root / "pubspec.yaml").exists()
    assert (root / "lib" / "main.dart").exists()
    assert (root / "test" / "widget_test.dart").exists()
    pubspec = (root / "pubspec.yaml").read_text(encoding="utf-8")
    assert "flutter_riverpod" in pubspec


def test_compose_scaffold_uses_package_path(tmp_path):
    root = scaffold("compose", tmp_path / "compose", "MyApp")
    activity = root / "app" / "src" / "main" / "java" / "com" / "example" / "myapp" / "MainActivity.kt"
    assert activity.exists()
    assert "package com.example.myapp" in activity.read_text(encoding="utf-8")


def test_all_scaffolds_render_without_placeholders(tmp_path):
    for framework in ["react-native", "swiftui", "maui", "kmp", "capacitor", "tauri"]:
        root = scaffold(framework, tmp_path / framework, "MyApp")
        for path in root.rglob("*"):
            if path.is_file():
                assert "{Name}" not in path.name
                text = path.read_text(encoding="utf-8")
                assert "{Name}" not in text
                assert "{package}" not in text


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        test_flutter_scaffold(Path(tmp))
        test_compose_scaffold_uses_package_path(Path(tmp))
        test_all_scaffolds_render_without_placeholders(Path(tmp))
    print("[OK] scaffold_project")
