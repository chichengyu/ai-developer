"""SQLite resource state store for large-scale media crawls."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class ResourceStore:
    """Persist per-resource status, path, size, hash, and retry state."""

    def __init__(
        self,
        path: str | Path,
        *,
        table: str = "resources",
    ) -> None:
        self.path = None if str(path) == ":memory:" else Path(path)
        self.table = table
        self._lock = threading.RLock()
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            ":memory:" if self.path is None else str(self.path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
              url TEXT PRIMARY KEY,
              kind TEXT,
              path TEXT,
              size INTEGER,
              sha256 TEXT,
              status TEXT,
              retries INTEGER DEFAULT 0,
              last_error TEXT,
              updated_at REAL
            )
            """
        )
        self._conn.commit()

    def get(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT * FROM {self.table} WHERE url = ?",
                (url,),
            ).fetchone()
        if row is None:
            return None
        columns = [item[1] for item in self._conn.execute(f"PRAGMA table_info({self.table})")]
        return dict(zip(columns, row, strict=False))

    def status(self, url: str) -> str | None:
        item = self.get(url)
        return item["status"] if item else None

    def upsert(
        self,
        url: str,
        *,
        kind: str | None = None,
        path: str | None = None,
        size: int | None = None,
        sha256: str | None = None,
        status: str = "pending",
        retries: int = 0,
        last_error: str | None = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                f"""
                INSERT INTO {self.table} (
                  url, kind, path, size, sha256, status, retries, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                  kind=excluded.kind,
                  path=excluded.path,
                  size=excluded.size,
                  sha256=excluded.sha256,
                  status=excluded.status,
                  retries=excluded.retries,
                  last_error=excluded.last_error,
                  updated_at=excluded.updated_at
                """,
                (
                    url,
                    kind,
                    path,
                    size,
                    sha256,
                    status,
                    retries,
                    last_error,
                    time.time(),
                ),
            )
            self._conn.commit()

    def mark_success(
        self,
        url: str,
        *,
        path: str,
        size: int,
        sha256: str | None,
        kind: str | None = None,
    ) -> None:
        self.upsert(
            url,
            kind=kind,
            path=path,
            size=size,
            sha256=sha256,
            status="success",
        )

    def mark_failed(self, url: str, error: str, *, kind: str | None = None) -> None:
        item = self.get(url) or {}
        retries = int(item.get("retries") or 0) + 1
        self.upsert(
            url,
            kind=kind or item.get("kind"),
            path=item.get("path"),
            size=item.get("size"),
            sha256=item.get("sha256"),
            status="failed",
            retries=retries,
            last_error=str(error)[:1000],
        )

    def failed(self, limit: int = 1000) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM {self.table} WHERE status = 'failed' ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        columns = [item[1] for item in self._conn.execute(f"PRAGMA table_info({self.table})")]
        return [dict(zip(columns, row, strict=False)) for row in rows]

    def count(self, status: str | None = None) -> int:
        with self._lock:
            if status is None:
                row = self._conn.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()
            else:
                row = self._conn.execute(
                    f"SELECT COUNT(*) FROM {self.table} WHERE status = ?",
                    (status,),
                ).fetchone()
        return int(row[0])

    def checkpoint(self) -> dict[str, int]:
        with self._lock:
            self._conn.commit()
        return {"resources": self.count(), "failed": self.count("failed")}

    def cleanup(
        self,
        older_than_seconds: float,
        *,
        statuses: tuple[str, ...] = ("failed", "success"),
        delete_files: bool = False,
    ) -> dict[str, Any]:
        """Remove old resource rows, optionally deleting their local files."""
        cutoff = time.time() - max(0.0, float(older_than_seconds))
        removed = 0
        deleted_files = 0
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT url, path FROM {self.table}
                WHERE status IN ({",".join("?" for _ in statuses)})
                  AND updated_at < ?
                """,
                (*statuses, cutoff),
            ).fetchall()
            if rows:
                urls = [row[0] for row in rows]
                placeholders = ",".join("?" for _ in urls)
                self._conn.execute(
                    f"DELETE FROM {self.table} WHERE url IN ({placeholders})",
                    urls,
                )
                self._conn.commit()
            removed = len(rows)
            if delete_files:
                for _, path_value in rows:
                    if not path_value:
                        continue
                    path = Path(str(path_value))
                    if path.is_file():
                        try:
                            path.unlink()
                            deleted_files += 1
                        except OSError:
                            pass
        return {"removed": removed, "deleted_files": deleted_files}

    def close(self) -> None:
        with self._lock:
            self._conn.commit()
            self._conn.close()

    def __enter__(self) -> ResourceStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


if __name__ == "__main__":
    with ResourceStore(":memory:") as store:
        store.mark_failed("https://example.com/a.mp4", "timeout", kind="video")
        print(store.checkpoint())
