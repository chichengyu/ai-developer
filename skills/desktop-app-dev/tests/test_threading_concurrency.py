"""Runtime tests for the shared bounded worker pool."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from threading_pool import (  # noqa: E402
    BatchItem,
    BatchProgress,
    Cancelled,
    RetryPolicy,
    WorkerPool,
    check_cancel,
)


def _slow_job(payload, progress, cancel_event):
    for step in range(5):
        check_cancel(cancel_event)
        time.sleep(0.005)
        progress((step + 1) / 5)
    return payload * 2


def test_run_all_is_bounded_and_aggregates_progress() -> None:
    seen: list[BatchProgress] = []
    lock = threading.Lock()

    def on_progress(p: BatchProgress) -> None:
        with lock:
            seen.append(p)

    pool = WorkerPool(
        _slow_job,
        max_workers=2,
        progress_throttle=0,
        on_progress=on_progress,
    )
    items = pool.run_all(range(6))

    assert [item.result for item in items] == [0, 2, 4, 6, 8, 10]
    assert all(item.error is None for item in items)
    assert all(item.status == "succeeded" for item in items)
    with lock:
        assert seen
        completed = [p.completed for p in seen]
        assert completed == sorted(completed)
        assert completed[-1] == 6
        assert seen[-1].percent == 1.0


def test_cancel_stops_pending_and_running_tasks() -> None:
    started = threading.Event()
    cancelled_calls: list[bool] = []
    lock = threading.Lock()

    def blocking_job(payload, progress, cancel_event):
        started.set()
        while not cancel_event.is_set():
            time.sleep(0.002)
        raise Cancelled()

    pool = WorkerPool(
        blocking_job,
        max_workers=1,
        on_cancel=lambda: cancelled_calls.append(True),
    )
    pool.submit_many([1, 2, 3])
    pool.start()
    assert started.wait(1)
    pool.cancel()
    assert pool.wait(timeout=2)
    with lock:
        assert cancelled_calls
    assert all(item.status == "cancelled" for item in pool.items())


def test_retry_policy_retries_transient_failures() -> None:
    attempts = {0: 0, 1: 0, 2: 0}

    def flaky_job(payload, progress, cancel_event):
        attempts[payload] += 1
        if attempts[payload] < 3:
            raise TimeoutError("transient")
        return payload

    pool = WorkerPool(
        flaky_job,
        max_workers=2,
        retry=RetryPolicy(max_attempts=3, delay_seconds=0.01),
        progress_throttle=0,
    )
    items = pool.run_all([0, 1, 2])

    assert attempts == {0: 3, 1: 3, 2: 3}
    assert all(item.status == "succeeded" for item in items)
    assert all(item.attempts == 3 for item in items)


def test_item_progress_and_error_callback_are_delivered() -> None:
    item_progress: list[tuple[int, object]] = []
    errors: list[BatchItem[int]] = []
    lock = threading.Lock()

    def mixed_job(payload, progress, cancel_event):
        progress(0.5)
        if payload == 1:
            raise ValueError("boom")
        return payload

    pool = WorkerPool(
        mixed_job,
        max_workers=2,
        progress_throttle=0,
        on_item_progress=lambda index, value: item_progress.append((index, value)),
        on_error=lambda item: errors.append(item),
    )
    items = pool.run_all([0, 1, 2])

    with lock:
        assert (0, 0.5) in item_progress
        assert (1, 0.5) in item_progress
        assert len(errors) == 1
        assert errors[0].payload == 1
    assert items[1].status == "failed"
    assert isinstance(items[1].error, ValueError)


def test_fail_fast_cancels_remaining_tasks() -> None:
    gate = threading.Event()

    def failer(payload, progress, cancel_event):
        if payload == 0:
            raise RuntimeError("fatal")
        gate.wait(0.5)
        check_cancel(cancel_event)
        return payload

    pool = WorkerPool(
        failer,
        max_workers=2,
        fail_fast=True,
        progress_throttle=0,
    )
    pool.submit_many([0, 1, 2, 3])
    pool.start()
    assert pool.wait(timeout=2)
    gate.set()
    statuses = {item.payload: item.status for item in pool.items()}
    assert statuses[0] == "failed"
    assert any(item.status == "cancelled" for item in pool.items())


if __name__ == "__main__":
    tests = [
        test_run_all_is_bounded_and_aggregates_progress,
        test_cancel_stops_pending_and_running_tasks,
        test_retry_policy_retries_transient_failures,
        test_item_progress_and_error_callback_are_delivered,
        test_fail_fast_cancels_remaining_tasks,
    ]
    for test in tests:
        test()
        print(f"  [OK] {test.__name__}")
    print(f"threading concurrency: {len(tests)}/{len(tests)} OK")
