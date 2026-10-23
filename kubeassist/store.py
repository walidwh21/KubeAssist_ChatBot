"""SQLite-backed chat memory: turns, the one pending command, and an audit trail."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import closing
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);
CREATE TABLE IF NOT EXISTS pending (
    session_id TEXT PRIMARY KEY, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL, cluster TEXT NOT NULL, command TEXT NOT NULL,
    risk TEXT NOT NULL, ok INTEGER NOT NULL, ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_session ON executions(session_id, id);
"""


class SessionStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False) if str(path) == ":memory:" else None
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        if self._memory_conn is not None:
            return _Borrowed(self._memory_conn)
        return closing(_open(self.path))

    # ---- conversation -------------------------------------------------
    def add_turn(self, session_id: str, role: str, text: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO turns(session_id, role, text, ts) VALUES (?,?,?,?)",
                (session_id, role, text, time.time()),
            )
            conn.commit()

    def recent_turns(self, session_id: str, limit: int) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, text FROM turns WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [(r[0], r[1]) for r in reversed(rows)]

    # ---- pending command ---------------------------------------------
    def set_pending(self, session_id: str, payload: dict | None) -> None:
        with self._connect() as conn:
            if payload is None:
                conn.execute("DELETE FROM pending WHERE session_id=?", (session_id,))
            else:
                conn.execute(
                    "INSERT OR REPLACE INTO pending(session_id, payload) VALUES (?,?)",
                    (session_id, json.dumps(payload)),
                )
            conn.commit()

    def get_pending(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM pending WHERE session_id=?", (session_id,)).fetchone()
        return json.loads(row[0]) if row else None

    # ---- audit trail --------------------------------------------------
    def record_execution(self, session_id: str, cluster: str, command: str, risk: str, ok: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO executions(session_id, cluster, command, risk, ok, ts) VALUES (?,?,?,?,?,?)",
                (session_id, cluster, command, risk, int(ok), time.time()),
            )
            conn.commit()

    def recent_executions(self, session_id: str, limit: int = 15) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT cluster, command, risk, ok, ts FROM executions "
                "WHERE session_id=? ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [
            {"cluster": r[0], "command": r[1], "risk": r[2], "ok": bool(r[3]), "ts": r[4]}
            for r in rows
        ]


def _open(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path, timeout=5)


class _Borrowed:
    """Context manager that lends out a shared in-memory connection without closing it."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False
