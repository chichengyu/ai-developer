"""SQLite-backed persistent task queue for desktop workers.

This is the durable queue behind the desktop UI: crawl, download,
transcode, and publish tasks all live in one SQLite table. Workers claim
one task at a time with an atomic UPDATE, write progress/resume checkpoints
back to the same row, and the UI paginates over the table with
`list_tasks()`.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskRecord:
    id: int
    kind: str
    payload: dict[str, Any]
    status: str
    priority: int
    attempts: int
    max_attempts: int
    progress: float
    stage: str | None
    resume_token: dict[str, Any] | None
    error: str | None
    result_path: str | None
    run_after: str | None
    created_at: str
    updated_at: str
    dedupe_key: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TaskRecord:
        payload = json.loads(row["payload"]) if row["payload"] else {}
        resume = json.loads(row["resume_token"]) if row["resume_token"] else None
        return cls(
            id=int(row["id"]),
            kind=row["kind"],
            payload=payload if isinstance(payload, dict) else {},
            status=row["status"],
            priority=int(row["priority"]),
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            progress=float(row["progress"]),
            stage=row["stage"],
            resume_token=resume if isinstance(resume, dict) else None,
            error=row["error"],
            result_path=row["result_path"],
            run_after=row["run_after"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            dedupe_key=row["dedupe_key"],
        )


class TaskQueue:
    """Thread-safe SQLite queue with atomic claims and crash recovery."""

    def __init__(self, db_path: str | Path, max_attempts: int = 3) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_max_attempts = max_attempts
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA busy_timeout = 5000")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    dedupe_key TEXT UNIQUE,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    priority INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    progress REAL NOT NULL DEFAULT 0,
                    stage TEXT,
                    resume_token TEXT,
                    error TEXT,
                    result_path TEXT,
                    run_after TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(tasks)")}
            if "run_after" not in columns:
                self._conn.execute("ALTER TABLE tasks ADD COLUMN run_after TEXT")
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
                ON tasks(status, priority, id)
                """
            )
            self._conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def _now_offset(cls, seconds: float) -> str:
        return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()

    def enqueue(
        self,
        kind: str,
        payload: dict[str, Any],
        dedupe_key: str | None = None,
        priority: int = 0,
        max_attempts: int | None = None,
        resume_token: dict[str, Any] | None = None,
    ) -> TaskRecord:
        now = self._now()
        attempts = max_attempts or self.default_max_attempts
        with self._lock:
            if dedupe_key is not None:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO tasks (
                        kind, dedupe_key, payload, status, priority,
                        attempts, max_attempts, progress, resume_token,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, 'queued', ?, 0, ?, 0, ?, ?, ?)
                    """,
                    (
                        kind,
                        dedupe_key,
                        json.dumps(payload, ensure_ascii=False),
                        priority,
                        attempts,
                        json.dumps(resume_token, ensure_ascii=False) if resume_token else None,
                        now,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE dedupe_key = ?",
                    (dedupe_key,),
                ).fetchone()
            else:
                cursor = self._conn.execute(
                    """
                    INSERT INTO tasks (
                        kind, payload, status, priority, attempts,
                        max_attempts, progress, resume_token,
                        created_at, updated_at
                    ) VALUES (?, ?, 'queued', ?, 0, ?, 0, ?, ?, ?)
                    """,
                    (
                        kind,
                        json.dumps(payload, ensure_ascii=False),
                        priority,
                        attempts,
                        json.dumps(resume_token, ensure_ascii=False) if resume_token else None,
                        now,
                        now,
                    ),
                )
                row = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)
                ).fetchone()
            self._conn.commit()
            return TaskRecord.from_row(row)

    def claim_next(self) -> TaskRecord | None:
        """Atomically move one queued task to running."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE status = 'queued'
                      AND (run_after IS NULL OR run_after <= ?)
                    ORDER BY priority DESC, id ASC
                    LIMIT 1
                    """,
                    (self._now(),),
                ).fetchone()
                if row is None:
                    self._conn.execute("ROLLBACK")
                    return None
                now = self._now()
                self._conn.execute(
                    """
                    UPDATE tasks
                    SET status = 'running', attempts = attempts + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, int(row["id"])),
                )
                updated = self._conn.execute(
                    "SELECT * FROM tasks WHERE id = ?", (int(row["id"]),)
                ).fetchone()
                self._conn.execute("COMMIT")
                return TaskRecord.from_row(updated)
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def claim_batch(self, limit: int = 4) -> list[TaskRecord]:
        records: list[TaskRecord] = []
        for _ in range(limit):
            record = self.claim_next()
            if record is None:
                break
            records.append(record)
        return records

    def update_progress(
        self,
        task_id: int,
        progress: float,
        stage: str | None = None,
        resume_token: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE tasks
                SET progress = ?, stage = COALESCE(?, stage),
                    resume_token = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    min(max(progress, 0.0), 1.0),
                    stage,
                    json.dumps(resume_token, ensure_ascii=False) if resume_token else None,
                    self._now(),
                    task_id,
                ),
            )
            self._conn.commit()

    def succeed(self, task_id: int, result_path: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE tasks
                SET status = 'succeeded', progress = 1.0,
                    result_path = COALESCE(?, result_path),
                    error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (result_path, self._now(), task_id),
            )
            self._conn.commit()

    def fail(
        self,
        task_id: int,
        error: str,
        retry: bool = True,
        delay_seconds: float = 0.0,
    ) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT attempts, max_attempts FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            can_retry = row is not None and int(row["attempts"]) < int(row["max_attempts"])
            status = "queued" if retry and can_retry else "failed"
            run_after = self._now_offset(delay_seconds) if status == "queued" else None
            self._conn.execute(
                """
                UPDATE tasks
                SET status = ?, error = ?, run_after = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error[:2000], run_after, self._now(), task_id),
            )
            self._conn.commit()

    def pause(self, task_id: int) -> None:
        self._set_status(task_id, TaskStatus.PAUSED.value)

    def resume(self, task_id: int) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE tasks
                SET status = ?, run_after = NULL, updated_at = ?
                WHERE id = ?
                """,
                (TaskStatus.QUEUED.value, self._now(), task_id),
            )
            self._conn.commit()

    def cancel(self, task_id: int) -> None:
        self._set_status(task_id, TaskStatus.CANCELLED.value)

    def _set_status(self, task_id: int, status: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                (status, self._now(), task_id),
            )
            self._conn.commit()

    def get(self, task_id: int) -> TaskRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return TaskRecord.from_row(row) if row else None

    def list_tasks(
        self,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[TaskRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search:
            clauses.append("(kind LIKE ? OR payload LIKE ? OR error LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT * FROM tasks
                {where}
                ORDER BY priority DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
            return [TaskRecord.from_row(row) for row in rows]

    def count(self, status: str | None = None, search: str | None = None) -> int:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if search:
            clauses.append("(kind LIKE ? OR payload LIKE ? OR error LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            row = self._conn.execute(f"SELECT COUNT(*) AS n FROM tasks {where}", params).fetchone()
            return int(row["n"])

    def reset_stale_running(self) -> int:
        """Crash recovery: put orphaned running tasks back in the queue."""
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE tasks
                SET status = 'queued', run_after = NULL, updated_at = ?
                WHERE status = 'running'
                """,
                (self._now(),),
            )
            self._conn.commit()
            return cursor.rowcount

    def stats(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM tasks GROUP BY status"
            ).fetchall()
            return {row["status"]: int(row["n"]) for row in rows}

    def prune(self, days: int = 30) -> int:
        with self._lock:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            cursor = self._conn.execute(
                """
                DELETE FROM tasks
                WHERE status IN ('succeeded', 'failed', 'cancelled')
                  AND updated_at < ?
                """,
                (cutoff,),
            )
            self._conn.commit()
            return cursor.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def self_test(self) -> dict[str, Any]:
        """Run a local persistence round-trip without network access."""
        key = "self-test-media"
        self.enqueue(
            "download",
            {"url": "https://example.com/video.mp4"},
            dedupe_key=key,
            max_attempts=2,
        )
        before_duplicate = self.count()
        duplicate = self.enqueue(
            "download",
            {"url": "https://example.com/video.mp4"},
            dedupe_key=key,
        )
        dedupe_ok = self.count() == before_duplicate
        record = self.claim_next()
        if record is None:
            raise RuntimeError("self-test could not claim a task")
        self.update_progress(record.id, 0.5, stage="chunks", resume_token={"done": 1})
        self.succeed(record.id, result_path="C:/out/video.mp4")
        self.pause(duplicate.id)
        self.resume(duplicate.id)
        self.cancel(duplicate.id)
        stale = self.enqueue("crawl", {"url": "https://example.com"})
        self._conn.execute("UPDATE tasks SET status='running' WHERE id=?", (stale.id,))
        self._conn.commit()
        self.reset_stale_running()
        record_after = self.get(record.id)
        duplicate_after = self.get(duplicate.id)
        stale_after = self.get(stale.id)
        if record_after is None or duplicate_after is None or stale_after is None:
            raise RuntimeError("self-test could not read back tasks")
        return {
            "dedupe": dedupe_ok,
            "claimed": record.status == "running",
            "progress": record_after.progress == 1.0,
            "cancelled": duplicate_after.status == "cancelled",
            "stale_reset": stale_after.status == "queued",
        }
