"""PySide6 management shell demo.

This example shows the canonical patterns for a PySide6 desktop app:

1. One table per page: left navigation switches QStackedWidget pages, so
   no right-side page stacks two tables.
2. Loading state: every action button is disabled with a visible suffix and
   every table shows an indeterminate progress bar while a job runs.
3. UI integration: app.ui is loaded at runtime with QUiLoader.
4. Fast start + clean exit: optional modules are imported lazily, and all
   JobRunners/pools/child processes are cancelled and waited on close.
5. Lazy dependencies: check/install happen only when a feature uses them,
   not on startup.

Run:
    python examples/pyside6-management/app.py

Build:
    powershell -ExecutionPolicy Bypass -File scripts/build_python.ps1 ^
      -Entry examples/pyside6-management/app.py -Name PySide6Management ^
      -HiddenImports "PySide6.QtUiTools,dependency_center,builtin_dependency_manager,lazy_python_dependency,threading_pyside6" ^
      -Paths "scripts" ^
      -AddData "examples/pyside6-management/assets;assets" ^
      -Install -InstallDeps -FastStart
"""

from __future__ import annotations

import atexit
import contextlib
import html
import importlib.metadata
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

from dependency_center import DependencyCenter  # noqa: E402
from lazy_python_dependency import (  # noqa: E402
    default_target_dir,
    ensure_python_dependency,
)
from PySide6.QtCore import (  # noqa: E402
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QBrush, QColor, QDesktopServices  # noqa: E402
from PySide6.QtUiTools import QUiLoader  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from threading_pyside6 import JobRegistry, JobRunner, poll_cancel  # noqa: E402

if getattr(sys, "frozen", False):
    BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
else:
    BASE_DIR = Path(__file__).resolve().parent


def _write_crash_log(exc_type: type[BaseException], exc: BaseException, tb: Any) -> None:
    """Keep a readable crash log for windowed EXEs (no console available)."""
    with contextlib.suppress(Exception):
        path = Path(tempfile.gettempdir()) / "PySide6Management_crash.log"
        path.write_text(
            "".join(traceback.format_exception(exc_type, exc, tb)),
            encoding="utf-8",
        )
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _write_crash_log


class StartupSplash(QWidget):
    """Frameless startup window with a fade-in animation and progress bar."""

    def __init__(self) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(560, 240)
        self.setWindowTitle("PySide6Management")

        title = QLabel("PySide6Management")
        title.setObjectName("splashTitle")
        self.subtitle = QLabel("正在加载界面...")
        self.subtitle.setObjectName("splashSubtitle")
        self.status = QLabel("0%")
        self.status.setObjectName("splashStatus")
        self.bar = QProgressBar()
        self.bar.setObjectName("splashBar")
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.subtitle)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

        self.setStyleSheet(
            """
            StartupSplash { background: #1e1f24; border: 1px solid #3d414a; }
            QLabel#splashTitle { color: #eceff4; font-size: 22px; font-weight: bold; }
            QLabel#splashSubtitle { color: #a8adb8; font-size: 13px; }
            QLabel#splashStatus { color: #7c8cf8; font-size: 12px; }
            QProgressBar#splashBar {
                background: #141519; border: 1px solid #3d414a;
                border-radius: 5px; height: 10px;
                color: #eceff4; text-align: center;
            }
            QProgressBar#splashBar::chunk { background: #7c8cf8; border-radius: 4px; }
            """
        )

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        self._fade = QPropertyAnimation(effect, b"opacity", self)
        self._fade.setDuration(350)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.start()

    def set_progress(self, value: int, message: str = "") -> None:
        value = max(0, min(100, int(value)))
        self.bar.setValue(value)
        self.status.setText(f"{value}%")
        if message:
            self.subtitle.setText(message)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._jobs = JobRegistry(self)
        self._children: set[subprocess.Popen[Any]] = set()
        self._busy_counts: dict[Any, int] = {}
        self._button_texts: dict[QPushButton, str] = {}
        self._logs: list[tuple[str, str, str, str]] = []
        self._task_rows: list[list[str]] = []
        self._page = 0
        self._page_size = 20
        self._dep_manifest = BASE_DIR / "assets" / "dependencies.json"
        self._dep_target = default_target_dir("PySide6Management")
        self._dep_items: list[dict[str, Any]] = []

        loader = QUiLoader()
        ui = loader.load(str(BASE_DIR / "assets" / "app.ui"))
        if ui is None:
            raise RuntimeError(f"failed to load {BASE_DIR / 'assets' / 'app.ui'}")
        self._ui = ui
        self.setCentralWidget(ui.centralWidget())
        self.setMenuBar(ui.menuBar())
        self.setStatusBar(ui.statusBar())

        self._apply_theme()
        self._wire()
        self.statusBar().showMessage("就绪")
        self._log("系统", "界面已加载，依赖与任务数据按需加载")

    def _apply_theme(self) -> None:
        qss_path = BASE_DIR / "assets" / "theme.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    def _wire(self) -> None:
        self._ui.navList.currentRowChanged.connect(self._ui.contentStack.setCurrentIndex)
        self._ui.refreshTasksButton.clicked.connect(self.refresh_tasks)
        self._ui.addTaskButton.clicked.connect(self.add_task)
        self._ui.exportTasksButton.clicked.connect(self.export_tasks)
        self._ui.prevPageButton.clicked.connect(self.prev_page)
        self._ui.nextPageButton.clicked.connect(self.next_page)
        self._ui.pageSizeCombo.currentIndexChanged.connect(self._on_page_size_changed)
        self._ui.refreshDepsButton.clicked.connect(self.refresh_deps)
        self._ui.installDepsButton.clicked.connect(self.install_deps)
        self._ui.depTable.itemSelectionChanged.connect(self._show_dep_detail)
        self._ui.depHelp.anchorClicked.connect(self._open_dependency_homepage)
        self._ui.refreshLogsButton.clicked.connect(self.refresh_logs)
        self._ui.clearLogsButton.clicked.connect(self.clear_logs)

        for table in (self._ui.taskTable, self._ui.depTable, self._ui.logTable):
            table.horizontalHeader().setStretchLastSection(True)
            table.verticalHeader().setVisible(False)
            table.setColumnWidth(0, 120)

    def _set_busy(self, controls: list[Any], busy: bool) -> None:
        for control in controls:
            count = max(0, self._busy_counts.get(control, 0) + (1 if busy else -1))
            self._busy_counts[control] = count
            if busy and count == 1:
                if isinstance(control, QPushButton):
                    self._button_texts.setdefault(control, control.text())
                    control.setText(f"{self._button_texts[control]} ...")
                    control.setEnabled(False)
                elif isinstance(control, QTableWidget):
                    control.setEnabled(False)
                elif isinstance(control, QProgressBar):
                    control.setRange(0, 100)
                    control.setValue(0)
                    control.setVisible(True)
            elif not busy and count == 0:
                if isinstance(control, QPushButton):
                    original = self._button_texts.get(control, control.text())
                    control.setText(original.replace(" ...", ""))
                    control.setEnabled(True)
                elif isinstance(control, QTableWidget):
                    control.setEnabled(True)
                elif isinstance(control, QProgressBar):
                    control.setRange(0, 100)
                    control.setVisible(False)

    def _run_job(
        self,
        controls: list[Any],
        job: Any,
        on_done: Any,
        on_error: Any | None = None,
    ) -> None:
        self._set_busy(controls, True)
        runner = JobRunner(job, parent=self, auto_delete=False)
        self._jobs.register(runner)
        progress_bars = [control for control in controls if isinstance(control, QProgressBar)]

        def update_progress(value: Any) -> None:
            try:
                percent = max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                return
            for bar in progress_bars:
                bar.setValue(int(round(percent * 100)))

        def finish() -> None:
            self._set_busy(controls, False)

        runner.on("progress").connect(update_progress)
        runner.on("done").connect(lambda result: (finish(), on_done(result)))
        runner.on("cancelled").connect(finish)
        runner.on("failed").connect(
            lambda exc: (finish(), self._show_error(exc))
            if on_error is None
            else (finish(), on_error(exc))
        )
        runner.start()

    def _show_error(self, exc: BaseException) -> None:
        self.statusBar().showMessage(f"错误: {exc}")
        self._log("错误", str(exc), "ERROR")
        QMessageBox.warning(self, "操作失败", str(exc))

    def _log(self, source: str, message: str, level: str = "INFO") -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._logs.append((now, level, source, message))
        if self._logs and len(self._logs) > 200:
            self._logs = self._logs[-200:]

    def _fill_table(self, table: QTableWidget, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        table.setColumnCount(max(1, table.columnCount()))
        for row_index, row in enumerate(rows):
            for col_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if col_index == 0:
                    item.setForeground(QBrush(QColor("#a8adb8")))
                table.setItem(row_index, col_index, item)
        table.resizeColumnsToContents()

    @staticmethod
    def _linkify(text: str) -> str:
        escaped = html.escape(text)
        parts = []
        rest = escaped
        while "http" in rest:
            start = rest.find("http")
            parts.append(rest[:start])
            end = start
            while end < len(rest) and not rest[end].isspace():
                end += 1
            url = rest[start:end]
            parts.append(f'<a href="{url}">{url}</a>')
            rest = rest[end:]
        parts.append(rest)
        return "".join(parts)

    def _task_controls(self) -> list[Any]:
        return [
            self._ui.refreshTasksButton,
            self._ui.addTaskButton,
            self._ui.exportTasksButton,
            self._ui.prevPageButton,
            self._ui.nextPageButton,
            self._ui.taskTable,
            self._ui.tasksLoading,
        ]

    def _sample_tasks(self) -> list[list[str]]:
        return [
            [str(i), f"任务-{i:03d}", "排队中" if i % 3 == 0 else "运行中", f"{i % 100}%", "刚刚"]
            for i in range(1, 38)
        ]

    def refresh_tasks(self) -> None:
        def job(token: JobRunner.CancelToken, progress: Any) -> list[list[str]]:
            for i in range(10):
                poll_cancel(token)
                time.sleep(0.03)
                progress((i + 1) / 10)
            return self._sample_tasks()

        def done(tasks: list[list[str]]) -> None:
            self._task_rows = tasks
            self._page = 0
            self._apply_pagination()
            self._ui.taskHint.setText(f"共 {len(tasks)} 条，点击刷新重新加载")
            self._log("任务", f"加载 {len(tasks)} 条任务")

        self._run_job(self._task_controls(), job, done)

    def add_task(self) -> None:
        base_count = len(self._task_rows)

        def job(token: JobRunner.CancelToken, progress: Any) -> list[list[str]]:
            for i in range(6):
                poll_cancel(token)
                time.sleep(0.03)
                progress((i + 1) / 6)
            next_id = base_count + 1
            return [str(next_id), f"任务-{next_id:03d}", "新建", "0%", "刚刚"]

        def done(row: list[str]) -> None:
            self._task_rows.append(row)
            self._apply_pagination()
            self._ui.taskHint.setText(f"新增 {row[1]}，共 {len(self._task_rows)} 条")
            self._log("任务", f"新增 {row[1]}")

        self._run_job(self._task_controls(), job, done)

    def export_tasks(self) -> None:
        rows = list(self._task_rows)

        def job(token: JobRunner.CancelToken, progress: Any) -> str:
            def dep_progress(stage: str, percent: float | None, message: str) -> None:
                if percent is not None:
                    progress(percent * 0.6)

            ensure_python_dependency(
                "openpyxl",
                target_dir=self._dep_target,
                progress=dep_progress,
                cancel=lambda: token.cancelled,
            )
            from openpyxl import Workbook  # lazy import: only on export

            poll_cancel(token)
            wb = Workbook()
            ws = wb.active
            ws.title = "任务"
            ws.append(["编号", "名称", "状态", "进度", "更新时间"])
            for row in rows:
                poll_cancel(token)
                ws.append(row)
                progress(0.6 + 0.4 * min(1.0, len(rows) / 100.0))
            path = Path(tempfile.gettempdir()) / "pyside6_tasks.xlsx"
            wb.save(str(path))
            return str(path)

        def done(path: str) -> None:
            self._ui.taskHint.setText(f"已导出: {path}")
            self._log("任务", f"导出 {len(rows)} 条到 {path}")

        self._run_job(self._task_controls(), job, done)

    def _apply_pagination(self) -> None:
        total = len(self._task_rows)
        pages = max(1, (total + self._page_size - 1) // self._page_size)
        self._page = min(max(0, self._page), pages - 1)
        start = self._page * self._page_size
        end = min(total, start + self._page_size)
        self._fill_table(self._ui.taskTable, self._task_rows[start:end])
        self._ui.pageLabel.setText(f"第 {self._page + 1} / {pages} 页")
        self._ui.prevPageButton.setEnabled(self._page > 0)
        self._ui.nextPageButton.setEnabled(self._page < pages - 1)

    def prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._apply_pagination()

    def next_page(self) -> None:
        pages = max(1, (len(self._task_rows) + self._page_size - 1) // self._page_size)
        if self._page < pages - 1:
            self._page += 1
            self._apply_pagination()

    def _on_page_size_changed(self, index: int) -> None:
        self._page_size = (20, 50, 100)[index]
        self._page = 0
        self._apply_pagination()

    def _dep_controls(self) -> list[Any]:
        return [
            self._ui.refreshDepsButton,
            self._ui.installDepsButton,
            self._ui.depTable,
            self._ui.depsLoading,
        ]

    def refresh_deps(self) -> None:
        def job(token: JobRunner.CancelToken, progress: Any) -> dict[str, Any]:
            center = DependencyCenter(self._dep_manifest)
            items = center.check_status()["items"]
            for index in range(len(items)):
                poll_cancel(token)
                progress((index + 1) / max(1, len(items)))
            return {"items": items, "help": center.help_text()}

        def done(result: dict[str, Any]) -> None:
            statuses = result["items"]
            self._dep_items = statuses
            rows = [
                [
                    item["name"],
                    self._version(item),
                    self._status_text(item),
                    "; ".join(item.get("paths") or []),
                ]
                for item in statuses
            ]
            self._fill_table(self._ui.depTable, rows)
            self._ui.depHelp.setHtml(self._linkify(result["help"]))
            ready = sum(1 for item in statuses if item["installed"])
            self._ui.depsHint.setText(f"已就绪 {ready}/{len(statuses)}，使用对应功能时自动检查")
            self._log("依赖", f"检查完成 {ready}/{len(statuses)}")

        self._run_job(self._dep_controls(), job, done)

    @staticmethod
    def _version(item: dict[str, Any]) -> str:
        try:
            return importlib.metadata.version(item["name"])
        except Exception:
            return ""

    @staticmethod
    def _status_text(item: dict[str, Any]) -> str:
        return "就绪" if item["installed"] else "未安装"

    def install_deps(self) -> None:
        def job(token: JobRunner.CancelToken, progress: Any) -> dict[str, Any]:
            def dep_progress(stage: str, percent: float | None, message: str) -> None:
                if percent is not None:
                    progress(percent)

            center = DependencyCenter(self._dep_manifest, progress=dep_progress)
            return {"items": center.install_all()["items"], "help": center.help_text()}

        def done(result: dict[str, Any]) -> None:
            statuses = result["items"]
            self._dep_items = statuses
            rows = [
                [
                    item["name"],
                    self._version(item),
                    self._status_text(item),
                    "; ".join(item.get("paths") or []),
                ]
                for item in statuses
            ]
            self._fill_table(self._ui.depTable, rows)
            self._ui.depHelp.setHtml(self._linkify(result["help"]))
            self._ui.depsHint.setText("依赖已安装到应用目录，无需用户手动安装")
            self._log("依赖", "可选依赖安装完成")

        self._run_job(self._dep_controls(), job, done)

    def _show_dep_detail(self) -> None:
        if not self._dep_items:
            return
        selection = self._ui.depTable.selectionModel()
        if selection is None:
            return
        selected = selection.selectedRows()
        if not selected:
            return
        item = self._dep_items[selected[0].row()]
        description = item.get("description") or ""
        manual = item.get("manual_install") or ""
        lines = [item["name"]]
        homepage = item.get("homepage") or ""
        if description:
            lines.append(description)
        if homepage:
            lines.append(f"官网：{homepage}")
        if manual:
            lines.append(f"手动安装：{manual}")
        self._ui.depHelp.setHtml(self._linkify("\n\n".join(lines)))

    def _open_dependency_homepage(self, url: QUrl) -> None:
        QDesktopServices.openUrl(url)

    def _log_controls(self) -> list[Any]:
        return [
            self._ui.refreshLogsButton,
            self._ui.clearLogsButton,
            self._ui.logTable,
            self._ui.logsLoading,
        ]

    def refresh_logs(self) -> None:
        snapshot = list(self._logs)

        def job(token: JobRunner.CancelToken, progress: Any) -> list[tuple[str, str, str, str]]:
            for i in range(4):
                poll_cancel(token)
                time.sleep(0.02)
                progress((i + 1) / 4)
            return snapshot

        def done(logs: list[tuple[str, str, str, str]]) -> None:
            rows = [list(item) for item in logs]
            self._fill_table(self._ui.logTable, rows)
            self._ui.logsHint.setText(f"共 {len(logs)} 条日志")
            self._log("日志", "日志列表已刷新")

        self._run_job(self._log_controls(), job, done)

    def clear_logs(self) -> None:
        def job(token: JobRunner.CancelToken, progress: Any) -> bool:
            poll_cancel(token)
            progress(1.0)
            return True

        def done(_: bool) -> None:
            self._logs.clear()
            self._ui.logTable.setRowCount(0)
            self._ui.logsHint.setText("日志已清空")
            self._log("日志", "日志已清空")

        self._run_job(self._log_controls(), job, done)

    def shutdown(self) -> None:
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True
        self._jobs.shutdown_all(3000)
        for proc in list(self._children):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self._children.clear()
        QThreadPool.globalInstance().waitForDone(3000)
        self.statusBar().showMessage("正在退出...")

    def closeEvent(self, event: Any) -> None:
        self.shutdown()
        super().closeEvent(event)


def _start_after_splash(app: QApplication, splash: StartupSplash) -> None:
    smoke_test = "--smoke-test" in sys.argv
    if smoke_test:
        splash.set_progress(100, "完成")
        app.processEvents()
    else:
        for value in range(0, 101, 5):
            message = "正在加载依赖清单..." if value < 50 else "正在初始化界面..."
            splash.set_progress(value, message)
            app.processEvents()
            time.sleep(0.015)

    window = MainWindow()
    window.resize(1080, 720)
    splash.hide()
    window.show()
    if smoke_test:
        QTimer.singleShot(300, app.quit)
    app.aboutToQuit.connect(window.shutdown)

    def atexit_shutdown() -> None:
        with contextlib.suppress(Exception):
            window.shutdown()

    atexit.register(atexit_shutdown)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("PySide6Management")
    app.setQuitOnLastWindowClosed(True)
    splash = StartupSplash()
    splash.show()
    QTimer.singleShot(0, lambda: _start_after_splash(app, splash))
    return app.exec()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:
        _write_crash_log(type(exc), exc, exc.__traceback__)
        raise
