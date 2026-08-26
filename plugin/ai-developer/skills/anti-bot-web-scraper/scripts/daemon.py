"""Production daemon runner: PID, restart, heartbeat, and graceful stop.

Wraps a crawler/pipeline command as a monitored background process. On
crashes it restarts with backoff, writes a PID file, updates a heartbeat
file, and stops cleanly on SIGINT/SIGTERM (Unix) or SIGBREAK (Windows).
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

_IS_WINDOWS = os.name == "nt"

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.windll.kernel32
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.GetLastError.restype = wintypes.DWORD

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001
    _STILL_ACTIVE = 259
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JobObjectExtendedLimitInformation = 9
    _ERROR_ACCESS_DENIED = 5

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]


def _win_process_alive(pid: int) -> bool:
    """Return True if a live process owns ``pid`` (Windows, ctypes-based)."""
    handle = _kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # ERROR_ACCESS_DENIED means the process exists but we lack rights.
        return _kernel32.GetLastError() == _ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        _kernel32.CloseHandle(handle)


def _win_create_kill_job() -> Any:
    """Create a Job Object that kills its processes when the handle closes."""
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _kernel32.SetInformationJobObject(
        job,
        _JobObjectExtendedLimitInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
    ):
        _kernel32.CloseHandle(job)
        return None
    return job


def _win_assign_to_job(job: Any, pid: int) -> bool:
    """Add the process ``pid`` to ``job`` so it dies with the daemon."""
    handle = _kernel32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not handle:
        return False
    try:
        return bool(_kernel32.AssignProcessToJobObject(job, handle))
    finally:
        _kernel32.CloseHandle(handle)


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
        self._win_job: Any = None
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
        if _IS_WINDOWS:
            return _win_process_alive(pid)
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
        if _IS_WINDOWS:
            # SIGTERM has no real delivery on Windows; SIGBREAK (Ctrl+Break) is
            # the native signal a console can actually raise into the process.
            signal.signal(signal.SIGBREAK, self._on_signal)
        else:
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
        popen_kwargs: dict[str, Any] = {}
        if _IS_WINDOWS:
            # Own process group so CTRL_BREAK_EVENT can target the child tree
            # without affecting other console processes.
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        with self.log_file.open("ab") as log_handle:
            popen_kwargs["stdout"] = log_handle
            popen_kwargs["stderr"] = log_handle
            self._process = subprocess.Popen(self.command, **popen_kwargs)
        self._write_pid(self._process.pid)
        self._heartbeat()
        if _IS_WINDOWS:
            # Bind the child to a kill-on-close Job so that if this daemon is
            # force-terminated (e.g. --stop), the child cannot become an orphan.
            self._assign_kill_job(self._process.pid)
        if self.task_timeout:
            try:
                return self._process.wait(timeout=self.task_timeout)
            except subprocess.TimeoutExpired:
                self._signal_process()
                try:
                    self._process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    self._kill_process()
                    with suppress(subprocess.TimeoutExpired):
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

    def _assign_kill_job(self, pid: int) -> None:
        # Close any job from a previous (already-exited) restart cycle first.
        if self._win_job is not None:
            with suppress(Exception):
                _kernel32.CloseHandle(self._win_job)
            self._win_job = None
        job = _win_create_kill_job()
        if job is not None:
            self._win_job = job
            _win_assign_to_job(job, pid)

    def _signal_process(self) -> None:
        """Ask the child to stop gracefully (SIGTERM / CTRL_BREAK_EVENT)."""
        if self._process is None or self._process.poll() is not None:
            return
        if _IS_WINDOWS:
            with suppress(OSError):
                os.kill(self._process.pid, signal.CTRL_BREAK_EVENT)
        else:
            self._process.terminate()

    def _kill_process(self) -> None:
        """Force the child to stop (SIGKILL / TerminateProcess)."""
        if self._process is None or self._process.poll() is not None:
            return
        self._process.kill()

    def _on_signal(self, signum: int, frame: Any) -> None:
        self._stop.set()
        self._signal_process()

    def stop(self) -> None:
        """Stop a running daemon (by pid file) from another process."""
        self._stop.set()
        pid = self.pid
        if pid is not None:
            with suppress(OSError):
                if _IS_WINDOWS:
                    # No reliable cross-process graceful signal exists on
                    # Windows. TerminateProcess the daemon; its child is bound
                    # to a kill-on-close Job, and we clean up the pid file
                    # ourselves below since the daemon's handler won't run.
                    os.kill(pid, signal.SIGTERM)
                else:
                    os.kill(pid, signal.SIGTERM)
        self._cleanup_pid()

    def _cleanup_pid(self) -> None:
        with suppress(OSError):
            self.pid_file.unlink(missing_ok=True)
        # Release any Job handle held in this (possibly separate stop) process.
        if _IS_WINDOWS and self._win_job is not None:
            with suppress(Exception):
                _kernel32.CloseHandle(self._win_job)
            self._win_job = None

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
