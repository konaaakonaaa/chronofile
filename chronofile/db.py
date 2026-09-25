"""
Metadata store: which files exist, and the timeline of hashes for each.

The object store only knows about content by hash; this database knows the
human-meaningful part -- "path X's 7th snapshot points to hash Y at time T".
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL,
    revision    INTEGER NOT NULL,   -- 1-based, per-path sequence number
    hash        TEXT NOT NULL,
    size        INTEGER NOT NULL,
    timestamp   REAL NOT NULL,
    message     TEXT,
    deleted     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_snapshots_path ON snapshots(path);
"""


class Database:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    def latest(self, path: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM snapshots WHERE path = ? ORDER BY revision DESC LIMIT 1",
            (path,),
        )
        return cur.fetchone()

    def next_revision(self, path: str) -> int:
        row = self.latest(path)
        return (row["revision"] + 1) if row else 1

    def add_snapshot(
        self, path: str, digest: str, size: int, message: str = None, deleted: bool = False
    ) -> int:
        revision = self.next_revision(path)
        cur = self.conn.execute(
            "INSERT INTO snapshots (path, revision, hash, size, timestamp, message, deleted) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (path, revision, digest, size, time.time(), message, int(deleted)),
        )
        self.conn.commit()
        return cur.lastrowid

    def history(self, path: str) -> list[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM snapshots WHERE path = ? ORDER BY revision ASC", (path,)
        )
        return cur.fetchall()

    def all_tracked_paths(self) -> list[str]:
        cur = self.conn.execute(
            "SELECT DISTINCT path FROM snapshots WHERE deleted = 0 ORDER BY path"
        )
        return [r["path"] for r in cur.fetchall()]

    def resolve_revision(self, path: str, revision_spec: str) -> Optional[sqlite3.Row]:
        """
        Accepts: a revision number ("3"), a negative relative index ("-1" = latest,
        "-2" = one before that), or a hash prefix.
        """
        hist = self.history(path)
        if not hist:
            return None

        if revision_spec is None:
            return hist[-1]

        # relative index
        try:
            n = int(revision_spec)
            if n < 0:
                idx = len(hist) + n
                return hist[idx] if 0 <= idx < len(hist) else None
            if n == 0:
                return None
            for row in hist:
                if row["revision"] == n:
                    return row
            return None
        except ValueError:
            pass

        # hash prefix
        matches = [r for r in hist if r["hash"].startswith(revision_spec)]
        return matches[-1] if matches else None
