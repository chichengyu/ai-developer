"""Recurring task scheduling on top of the SQLite task queue.

Supported schedule shapes:

    {"type": "interval", "seconds": 3600}
    {"type": "daily", "time": "09:30"}
    {"type": "cron", "minute": "*/15", "hour": "*"}
    {"type": "once", "at": "2026-08-08T09:30:00+08:00"}

TaskScheduler stores one row per schedule in the same SQLite database as
the queue and enqueues due tasks from a background loop in the sidecar.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from task_queue import ScheduleRecord, TaskQueue


def _parse_cron_field(value: Any, low: int, high: int) -> set[int]:
    text = str(value or "*").strip()
    if not text:
        text = "*"
    result: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            step = max(1, int(step_text))
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start_text, _, end_text = part.partition("-")
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(part)
        result.update(range(start, end + 1, step))
    return {value for value in result if low <= value <= high}


def next_run_after(
    schedule: dict[str, Any],
    now: datetime | None = None,
    start_after_seconds: float = 0.0,
) -> datetime:
    """Return the next UTC run time for a schedule definition."""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    schedule_type = str(schedule.get("type", "interval")).lower()
    start = current + timedelta(seconds=max(0.0, float(start_after_seconds)))
    if schedule_type == "once":
        at = schedule.get("at")
        if not at:
            raise ValueError("once schedule requires 'at'")
        parsed = datetime.fromisoformat(str(at))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    if schedule_type == "interval":
        return start + timedelta(seconds=max(0.0, float(schedule.get("seconds", 60))))
    if schedule_type == "daily":
        time_text = str(schedule.get("time", "09:00"))
        hour_text, _, minute_text = time_text.partition(":")
        candidate = start.replace(
            hour=int(hour_text),
            minute=int(minute_text),
            second=0,
            microsecond=0,
        )
        if candidate <= start:
            candidate += timedelta(days=1)
        return candidate
    if schedule_type == "cron":
        minutes = _parse_cron_field(schedule.get("minute", "*"), 0, 59)
        hours = _parse_cron_field(schedule.get("hour", "*"), 0, 23)
        candidate = start.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(7 * 24 * 60):
            if candidate.hour in hours and candidate.minute in minutes:
                return candidate
            candidate += timedelta(minutes=1)
        raise ValueError("cron schedule has no matching time in the next 7 days")
    raise ValueError(f"unsupported schedule type: {schedule_type}")


class TaskScheduler:
    """Persist schedules and enqueue due tasks through TaskQueue."""

    def __init__(self, queue: TaskQueue) -> None:
        self.queue = queue

    def add(
        self,
        kind: str,
        payload: dict[str, Any],
        schedule: dict[str, Any],
        dedupe_key: str | None = None,
        priority: int = 0,
        max_attempts: int | None = None,
        start_after_seconds: float = 0.0,
    ) -> ScheduleRecord:
        next_run = next_run_after(
            schedule,
            start_after_seconds=start_after_seconds,
        ).isoformat()
        return self.queue.add_schedule(
            kind,
            payload,
            schedule,
            dedupe_key=dedupe_key,
            priority=priority,
            max_attempts=max_attempts,
            next_run_at=next_run,
        )

    def enqueue_due(self, now: datetime | None = None) -> int:
        """Enqueue every due schedule and advance its next run time."""
        now = now or datetime.now(timezone.utc)
        due = self.queue.due_schedules(now.isoformat())
        for record in due:
            self.queue.enqueue(
                record.kind,
                record.payload,
                dedupe_key=record.dedupe_key,
                priority=record.priority,
                max_attempts=record.max_attempts,
            )
            next_run = next_run_after(record.schedule, now=now)
            self.queue.mark_schedule_run(record.id, next_run.isoformat())
        return len(due)

    def list(self) -> list[ScheduleRecord]:
        return self.queue.list_schedules()

    def remove(self, schedule_id: int) -> bool:
        return self.queue.remove_schedule(schedule_id)

    def pause(self, schedule_id: int) -> bool:
        return self.queue.set_schedule_enabled(schedule_id, False)

    def resume(self, schedule_id: int) -> bool:
        return self.queue.set_schedule_enabled(schedule_id, True)


if __name__ == "__main__":
    print(
        "desktop-app-dev task_scheduler: import TaskScheduler / next_run_after() for recurring schedules."
    )
