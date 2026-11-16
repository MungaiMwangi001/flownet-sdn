"""Tiny SQLite store for traffic policies and the event log."""
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src TEXT NOT NULL, dst TEXT NOT NULL,
                    action TEXT NOT NULL DEFAULT 'deny',
                    bidirectional INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL
                );
                """
            )

    def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    # events
    def add_event(self, kind: str, message: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO events (ts, kind, message) VALUES (?, ?, ?)", (_now(), kind, message))

    def events(self, limit: int = 100) -> list[dict]:
        return self._rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))

    # policies
    def add_policy(self, src: str, dst: str, bidirectional: bool) -> dict:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO policies (src, dst, bidirectional, created_at) VALUES (?, ?, ?, ?)",
                (src, dst, int(bidirectional), _now()),
            )
            pid = cur.lastrowid
        return self.get_policy(pid)

    def policies(self) -> list[dict]:
        return [self._fmt(p) for p in self._rows("SELECT * FROM policies ORDER BY id")]

    def get_policy(self, pid: int) -> dict | None:
        rows = self._rows("SELECT * FROM policies WHERE id = ?", (pid,))
        return self._fmt(rows[0]) if rows else None

    def delete_policy(self, pid: int) -> bool:
        with self._lock, self._conn:
            return self._conn.execute("DELETE FROM policies WHERE id = ?", (pid,)).rowcount > 0

    @staticmethod
    def _fmt(row: dict) -> dict:
        row["bidirectional"] = bool(row["bidirectional"])
        return row
