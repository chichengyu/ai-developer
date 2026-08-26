"""Concurrent CAPTCHA task queue with retries and provider cooldown."""

from __future__ import annotations

import itertools
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CaptchaTask:
    task_id: str
    kind: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    future: Future | None = None
    attempts: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None


class CaptchaTaskQueue:
    """Thread pool for CAPTCHA provider calls with retry and status."""

    def __init__(
        self,
        solver: Any,
        *,
        workers: int = 2,
        max_retries: int = 2,
        backoff_base: float = 0.5,
        backoff_max: float = 15.0,
    ) -> None:
        self.solver = solver
        self.workers = max(1, int(workers))
        self.max_retries = max(0, int(max_retries))
        self.backoff_base = max(0.0, float(backoff_base))
        self.backoff_max = max(0.0, float(backoff_max))
        self._queue: queue.PriorityQueue[tuple[int, int, CaptchaTask]] = queue.PriorityQueue()
        self._counter = itertools.count()
        self._threads: list[threading.Thread] = []
        self._stop = threading.Event()
        self._lock = threading.RLock()
        self._tasks: dict[str, CaptchaTask] = {}
        self._stats: dict[str, int] = {
            "submitted": 0,
            "succeeded": 0,
            "failed": 0,
            "retries": 0,
        }
        for _ in range(self.workers):
            thread = threading.Thread(target=self._worker, daemon=True)
            thread.start()
            self._threads.append(thread)

    def submit(
        self,
        kind: str,
        *args: Any,
        priority: int = 0,
        **kwargs: Any,
    ) -> Future:
        future: Future = Future()
        task_id = f"{kind}-{next(self._counter)}"
        task = CaptchaTask(
            task_id=task_id,
            kind=kind,
            args=args,
            kwargs=kwargs,
            priority=priority,
            future=future,
        )
        with self._lock:
            self._tasks[task_id] = task
            self._stats["submitted"] += 1
        self._queue.put((priority, next(self._counter), task))
        return future

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                _, _, task = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue
            self._process(task)
            self._queue.task_done()

    def _process(self, task: CaptchaTask) -> None:
        task.started_at = time.time()
        method = getattr(self.solver, task.kind, None)
        if method is None:
            self._finish(task, error=f"no solver method: {task.kind}")
            return
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            task.attempts = attempt + 1
            try:
                result = method(*task.args, **task.kwargs)
                task.finished_at = time.time()
                if task.future is not None:
                    task.future.set_result(result)
                with self._lock:
                    self._stats["succeeded"] += 1
                    if attempt:
                        self._stats["retries"] += attempt
                return
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(min(self.backoff_max, self.backoff_base * (2**attempt)))
        self._finish(task, error=str(last_error) if last_error else "unknown error")

    def _finish(self, task: CaptchaTask, *, error: str) -> None:
        task.finished_at = time.time()
        task.error = error
        if task.future is not None and not task.future.done():
            task.future.set_exception(RuntimeError(error))
        with self._lock:
            self._stats["failed"] += 1

    def wait_all(self, timeout: float | None = None) -> None:
        deadline = time.monotonic() + timeout if timeout else None
        while True:
            with self._lock:
                pending = [
                    task
                    for task in self._tasks.values()
                    if task.future is not None and not task.future.done()
                ]
            if not pending:
                return
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("CAPTCHA queue wait timed out")
            time.sleep(0.1)

    def status(self) -> dict[str, Any]:
        with self._lock:
            tasks = [
                {
                    "task_id": task.task_id,
                    "kind": task.kind,
                    "priority": task.priority,
                    "attempts": task.attempts,
                    "started_at": task.started_at,
                    "finished_at": task.finished_at,
                    "error": task.error,
                    "done": bool(task.future is not None and task.future.done()),
                }
                for task in self._tasks.values()
            ]
            stats = dict(self._stats)
        return {"stats": stats, "tasks": tasks}

    def shutdown(self) -> None:
        self._stop.set()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=2.0)

    def __enter__(self) -> CaptchaTaskQueue:
        return self

    def __exit__(self, *args: object) -> None:
        self.shutdown()


class ConcurrentCaptchaSolver:
    """Facade that submits common CAPTCHA kinds to a task queue."""

    def __init__(self, queue: CaptchaTaskQueue) -> None:
        self.queue = queue

    def solve_image(self, *args: Any, **kwargs: Any) -> Any:
        return self.queue.submit("solve_image", *args, **kwargs).result()

    def solve_recaptcha_v2(self, *args: Any, **kwargs: Any) -> Any:
        return self.queue.submit("solve_recaptcha_v2", *args, **kwargs).result()

    def solve_hcaptcha(self, *args: Any, **kwargs: Any) -> Any:
        return self.queue.submit("solve_hcaptcha", *args, **kwargs).result()

    def solve_turnstile(self, *args: Any, **kwargs: Any) -> Any:
        return self.queue.submit("solve_turnstile", *args, **kwargs).result()

    def solve_audio(self, *args: Any, **kwargs: Any) -> Any:
        return self.queue.submit("solve_audio", *args, **kwargs).result()

    def get_balance(self) -> float:
        return float(self.queue.solver.get_balance())


if __name__ == "__main__":
    print("captcha_queue: import CaptchaTaskQueue for concurrent CAPTCHA solving.")
