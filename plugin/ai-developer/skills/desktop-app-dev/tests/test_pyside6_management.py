"""Structural + optional runtime tests for the PySide6 management example."""

from __future__ import annotations

import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "pyside6-management"


def test_ui_has_one_table_per_page() -> None:
    root = ET.parse(EXAMPLE / "assets" / "app.ui").getroot()

    def widgets(element: ET.Element) -> list[ET.Element]:
        result = []
        for child in element.iter():
            if child.tag == "widget":
                result.append(child)
        return result

    pages = [
        widget
        for widget in widgets(root)
        if widget.attrib.get("name") in {"pageTasks", "pageDeps", "pageLogs"}
    ]
    assert len(pages) == 3
    for page in pages:
        tables = [
            widget for widget in widgets(page) if widget.attrib.get("class") == "QTableWidget"
        ]
        assert len(tables) == 1, f"{page.attrib.get('name')} must have one table"
        progress_bars = [
            widget for widget in widgets(page) if widget.attrib.get("class") == "QProgressBar"
        ]
        assert len(progress_bars) == 1, f"{page.attrib.get('name')} must have one progress bar"
        assert len(tables) == len(progress_bars)


def test_app_uses_lazy_loading_and_clean_shutdown() -> None:
    assert (EXAMPLE / "assets" / "dependencies.json").is_file()
    text = (EXAMPLE / "app.py").read_text(encoding="utf-8")
    assert "https://" not in text, "app.py must not hard-code dependency URLs"
    ui_text = (EXAMPLE / "assets" / "app.ui").read_text(encoding="utf-8")
    manifest_text = (EXAMPLE / "assets" / "dependencies.json").read_text(encoding="utf-8")
    for term in (
        "QUiLoader",
        "StartupSplash",
        "QPropertyAnimation",
        "set_progress",
        "FramelessWindowHint",
        "app.processEvents",
        "JobRegistry",
        "DependencyCenter",
        "dependencies.json",
        "depHelp",
        "_show_dep_detail",
        "QProgressBar",
        "_linkify",
        "QDesktopServices",
        "openUrl",
        "anchorClicked",
        "_open_dependency_homepage",
        "setRange(0, 100)",
        'runner.on("progress")',
        "ensure_python_dependency",
        "_set_busy",
        "QThreadPool.globalInstance().waitForDone",
        "self._jobs.shutdown_all",
    ):
        assert term in text, f"app.py missing {term}"
    assert "QTextBrowser" in ui_text
    assert "openExternalLinks" in ui_text
    assert "depHelp" in ui_text
    assert '"help"' in manifest_text
    assert '"homepage"' in manifest_text
    assert "manual_install" in manifest_text


def test_threading_templates_support_shutdown() -> None:
    single = (ROOT / "scripts" / "threading_pyside6.py").read_text(encoding="utf-8")
    pool = (ROOT / "scripts" / "threading_pool_pyside6.py").read_text(encoding="utf-8")
    assert "class JobRegistry" in single
    assert "def shutdown_all" in single
    assert "finished = Signal()" in single
    assert "def shutdown" in pool


def test_build_script_has_faststart_install_deps() -> None:
    text = (ROOT / "scripts" / "build_python.ps1").read_text(encoding="utf-8")
    for term in (
        "$FastStart",
        "$InstallDeps",
        "$Paths",
        "OneDir",
        "--disable-windowed-traceback",
        'Join-Path $entryDir "requirements.txt"',
    ):
        assert term in text, f"build_python.ps1 missing {term}"


def test_lazy_dependency_check_and_ensure() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from lazy_python_dependency import check_python_dependency, ensure_python_dependency

    target = Path(tempfile.gettempdir()) / "pyside6-deps-test"
    status = check_python_dependency("openpyxl", target)
    if status["installed"]:
        result = ensure_python_dependency("openpyxl", target)
        assert result["installed"] is True
    else:
        assert status["installed"] is False


def test_runtime_offscreen_launch_and_exit() -> None:
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("  [SKIP] PySide6 not installed")
        return

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(EXAMPLE))

    import app as app_module

    app = QApplication.instance() or QApplication(sys.argv)
    window = app_module.MainWindow()
    window.show()
    QTimer.singleShot(120, app.quit)
    app.exec()
    window.shutdown()
    assert window._jobs.running_count == 0


def main() -> int:
    tests = [
        test_ui_has_one_table_per_page,
        test_app_uses_lazy_loading_and_clean_shutdown,
        test_threading_templates_support_shutdown,
        test_build_script_has_faststart_install_deps,
        test_lazy_dependency_check_and_ensure,
        test_runtime_offscreen_launch_and_exit,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"  [OK] {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  [FAIL] {test.__name__}: {exc}")
    print(f"PySide6 management: {len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
