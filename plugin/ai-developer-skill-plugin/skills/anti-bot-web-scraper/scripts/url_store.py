"""Disk-backed URL deduplicator for million-scale crawls."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path


class UrlDeduplicator:
    """SQLite-backed URL seen-set with WAL and batch inserts.

    SQLite handles millions of URLs on disk without holding them in memory.
    `add_many()` uses `INSERT OR IGNORE` batches, and `commit()` flushes
    pending rows so a stopped crawl can be resumed safely.
    """

    def __init__(
        self,
        path: str | Path = "urls.sqlite3",
        *,
        table: str = "seen_urls",
        batch_size: int = 1000,
    ) -> None:
        self.path = None if str(path) == ":memory:" else Path(path)
        self.table = table
        self.batch_size = max(1, int(batch_size))
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
            f"CREATE TABLE IF NOT EXISTS {table} (url TEXT PRIMARY KEY, added_at REAL)"
        )
        self._conn.commit()
        self._pending: set[str] = set()
        self._count: int | None = None

    def contains(self, url: str) -> bool:
        with self._lock:
            if url in self._pending:
                return True
            row = self._conn.execute(
                f"SELECT 1 FROM {self.table} WHERE url = ?",
                (url,),
            ).fetchone()
            return row is not None

    def add(self, url: str) -> bool:
        with self._lock:
            if self.contains(url):
                return False
            self._pending.add(url)
            self._flush_if_needed()
            return True

    def add_many(self, urls: Iterable[str]) -> int:
        added = 0
        with self._lock:
            for url in urls:
                if not url or url in self._pending or self.contains(url):
                    continue
                self._pending.add(url)
                added += 1
                self._flush_if_needed()
        return added

    def _flush_if_needed(self) -> None:
        if len(self._pending) >= self.batch_size:
            self.commit()

    def commit(self) -> None:
        with self._lock:
            if not self._pending:
                self._conn.commit()
                return
            now = __import__("time").time()
            self._conn.executemany(
                f"INSERT OR IGNORE INTO {self.table} (url, added_at) VALUES (?, ?)",
                [(url, now) for url in self._pending],
            )
            self._pending.clear()
            self._conn.commit()
            self._count = None

    def count(self) -> int:
        with self._lock:
            if self._count is None:
                self._count = int(
                    self._conn.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()[0]
                )
            return self._count + len(self._pending)

    def checkpoint(self) -> dict[str, int]:
        self.commit()
        return {"seen_urls": self.count()}

    def close(self) -> None:
        with self._lock:
            self.commit()
            self._conn.close()

    def __enter__(self) -> UrlDeduplicator:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


if __name__ == "__main__":
    with UrlDeduplicator(":memory:") as store:
        store.add("https://example.com/")
        assert not store.add("https://example.com/")
        assert store.add("https://example.com/a")
        print(store.checkpoint())
