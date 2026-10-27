"""SQLite: игры как JSON и статусы генерации (SPEC §4)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    step TEXT NOT NULL DEFAULT '',
    progress REAL NOT NULL DEFAULT 0,
    detail TEXT,
    error TEXT,
    brief TEXT NOT NULL,
    preview TEXT,
    game TEXT,
    report TEXT,
    warnings TEXT,
    provider TEXT,
    ip TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS games_ip_created ON games (ip, created_at);
"""

ACTIVE = ("queued", "outline", "locations", "items", "validate", "fix", "balance", "levels", "playtest")


class Storage:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def create(self, game_id: str, brief: str, ip: str, provider: str) -> None:
        now = time.time()
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO games (id, status, brief, ip, provider, created_at, updated_at) VALUES (?, 'queued', ?, ?, ?, ?, ?)",
                (game_id, brief, ip, provider, now, now),
            )

    def update(self, game_id: str, **fields: Any) -> None:
        for key in ("preview", "game", "report", "warnings", "detail"):
            if key in fields and not isinstance(fields[key], (str, type(None))):
                fields[key] = json.dumps(fields[key], ensure_ascii=False)
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._lock, self._db:
            self._db.execute(f"UPDATE games SET {cols} WHERE id = ?", (*fields.values(), game_id))

    def get(self, game_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
        if row is None:
            return None
        out = dict(row)
        for key in ("preview", "game", "report", "warnings", "detail"):
            if out[key]:
                out[key] = json.loads(out[key])
        return out

    def count_recent(self, ip: str, seconds: float) -> int:
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM games WHERE ip = ? AND created_at > ?", (ip, time.time() - seconds)).fetchone()[0]

    def queued_before(self, game_id: str) -> int:
        with self._lock:
            row = self._db.execute("SELECT created_at FROM games WHERE id = ?", (game_id,)).fetchone()
            if row is None:
                return 0
            return self._db.execute("SELECT COUNT(*) FROM games WHERE status = 'queued' AND created_at < ?", (row[0],)).fetchone()[0]

    def fail_interrupted(self) -> int:
        """После перезапуска сервера фоновые задачи потеряны: незавершённые генерации помечаются ошибкой."""
        marks = ",".join("?" * len(ACTIVE))
        with self._lock, self._db:
            cur = self._db.execute(
                f"UPDATE games SET status = 'failed', error = 'Генерация прервалась: сервер перезапускался. Попробуйте ещё раз.', updated_at = ? WHERE status IN ({marks})",
                (time.time(), *ACTIVE),
            )
        return cur.rowcount
