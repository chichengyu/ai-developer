"""Production daemon runner: PID, restart, heartbeat, and graceful stop.

Wraps a crawler/pipeline command as a monitored background process. On
crashes it restarts with backoff, writes a PID file, updates a heartbeat
file, and stops cleanly on SIGINT/SIGTERM.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any


class DaemonRunner:
    """Monitor one command or callable with restart and heartbeat."""

    def __init__(
        self,
        *,
        command: list[str] | None = None,
        task: Callable[[], Any] | None = None,
        pid_file: str | Path = "daemon.pid",
        log_file: str | Path = "daemon.log",
        heartbeat_file: str | Path = "daemon.heartbeat",
        max_restarts: int = 5,
        restart_delay: float = 3.0,
        task_timeout: float = 0.0,
    ) -> None:
        self.command = command
        self.task = task
        self.pid_file = Path(pid_file)
        self.log_file = Path(log_file)
        self.heartbeat_file = Path(heartbeat_file)
        self.max_restarts = max(0, int(max_restarts))
        self.restart_delay = max(0.0, float(restart_delay))
        self.task_timeout = max(0.0, float(task_timeout))
        self._stop = threading.Event()
        self._process: subprocess.Popen | None = None
        self._stats: dict[str, Any] = {
            "started_at": None,
            "restarts": 0,
            "last_exit_code": None,
        }

    @property
    def pid(self) -> int | None:
        if self.pid_file.exists():
            try:
                return int(self.pid_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                return None
        return None

    def is_running(self) -> bool:
        pid = self.pid
        if pid is None:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _write_pid(self, pid: int) -> None:
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(pid), encoding="utf-8")

    def _heartbeat(self) -> None:
        self.heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
        self.heartbeat_file.write_text(
            json.dumps({"ts": time.time(), "pid": os.getpid()}),
            encoding="utf-8",
        )

    def run_forever(self) -> None:
        """Run command or callable, restarting after crashes."""
        self._stats["started_at"] = time.time()
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)
        restarts = 0
        while not self._stop.is_set():
            if self.command:
                exit_code = self._run_command()
            elif self.task is not None:
                exit_code = self._run_task()
            else:
                raise ValueError("daemon requires command or task")
            self._stats["last_exit_code"] = exit_code
            if self._stop.is_set() or exit_code == 0:
                break
            restarts += 1
            self._stats["restarts"] = restarts
            if restarts > self.max_restarts:
                break
            self._stop.wait(self.restart_delay)
        self._cleanup_pid()

    def _run_command(self) -> int:
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("ab") as log_handle:
            self._process = subprocess.Popen(
                self.command,
                stdout=log_handle,
                stderr=log_handle,
            )
        self._write_pid(self._process.pid)
        self._heartbeat()
        if self.task_timeout:
            try:
                return self._process.wait(timeout=self.task_timeout)
            except subprocess.TimeoutExpired:
                self._process.terminate()
                self._process.wait(timeout=5.0)
                return 124
        return self._process.wait()

    def _run_task(self) -> int:
        assert self.task is not None
        self._write_pid(os.getpid())
        result: list[Any] = []
        error: list[Exception] = []

        def worker() -> None:
            try:
                result.append(self.task())
            except Exception as exc:
                error.append(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._heartbeat()
        thread.join(timeout=self.task_timeout if self.task_timeout else None)
        if thread.is_alive():
            return 124
        if error:
            return 1
        return 0

    def _on_signal(self, signum: int, frame: Any) -> None:
        self._stop.set()
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()

    def stop(self) -> None:
        self._stop.set()
        pid = self.pid
        if pid is not None:
            with suppress(OSError):
                os.kill(pid, signal.SIGTERM)
        self._cleanup_pid()

    def _cleanup_pid(self) -> None:
        with suppress(OSError):
            self.pid_file.unlink(missing_ok=True)

    def status(self) -> dict[str, Any]:
        heartbeat: dict[str, Any] | None = None
        if self.heartbeat_file.exists():
            try:
                heartbeat = json.loads(self.heartbeat_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                heartbeat = None
        return {
            "running": self.is_running(),
            "pid": self.pid,
            "pid_file": str(self.pid_file.resolve()),
            "log_file": str(self.log_file.resolve()),
            "heartbeat": heartbeat,
            "stats": self._stats,
        }


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Daemon runner for crawler commands")
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    parser.add_argument("--pid-file", default="daemon.pid")
    parser.add_argument("--log-file", default="daemon.log")
    parser.add_argument("--heartbeat-file", default="daemon.heartbeat")
    parser.add_argument("--max-restarts", type=int, default=5)
    parser.add_argument("--restart-delay", type=float, default=3.0)
    parser.add_argument("--timeout", type=float, default=0.0)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(argv)

    runner = DaemonRunner(
        command=args.command,
        pid_file=args.pid_file,
        log_file=args.log_file,
        heartbeat_file=args.heartbeat_file,
        max_restarts=args.max_restarts,
        restart_delay=args.restart_delay,
        task_timeout=args.timeout,
    )
    if args.status:
        print(json.dumps(runner.status(), ensure_ascii=False, indent=2))
        return 0
    if args.stop:
        runner.stop()
        print("daemon stop signal sent")
        return 0
    if not args.command:
        parser.error("--command is required unless --status/--stop is used")
    runner.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
