"""
Repo ties the object store and the metadata db together, and knows how to
walk a directory tree, respecting ignore rules.
"""

from __future__ import annotations

import fnmatch
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .db import Database
from .storage import ObjectStore

STORE_DIRNAME = ".chronofile"
DEFAULT_IGNORE = [
    ".chronofile", ".git", "__pycache__", "*.pyc", "node_modules",
    ".venv", "venv", ".DS_Store", "*.tmp",
]


class NotAChronofileRepo(Exception):
    pass


@dataclass
class FileStatus:
    path: str
    kind: str  # "new" | "modified" | "deleted" | "unchanged"
    current_hash: Optional[str] = None
    previous_hash: Optional[str] = None


class Repo:
    def __init__(self, workdir: Path):
        self.workdir = Path(workdir).resolve()
        self.store_dir = self.workdir / STORE_DIRNAME
        self.config_path = self.store_dir / "config.json"

    # -- lifecycle ---------------------------------------------------

    @classmethod
    def init(cls, workdir: Path, poll_interval: float = 2.0) -> "Repo":
        repo = cls(workdir)
        repo.store_dir.mkdir(exist_ok=True)
        (repo.store_dir / "objects").mkdir(exist_ok=True)
        config = {"poll_interval": poll_interval, "ignore": DEFAULT_IGNORE}
        repo.config_path.write_text(json.dumps(config, indent=2))
        # touch the db so `init` fully sets things up
        repo._db().close()
        return repo

    @classmethod
    def find(cls, start: Path) -> "Repo":
        cur = Path(start).resolve()
        for candidate in [cur, *cur.parents]:
            if (candidate / STORE_DIRNAME).is_dir():
                return cls(candidate)
        raise NotAChronofileRepo(
            "Not a chronofile repo (or any parent). Run `chronofile init` first."
        )

    def _db(self) -> Database:
        return Database(self.store_dir / "db.sqlite3")

    def _store(self) -> ObjectStore:
        return ObjectStore(self.store_dir / "objects")

    def config(self) -> dict:
        return json.loads(self.config_path.read_text())

    # -- scanning ------------------------------------------------------

    def _is_ignored(self, rel_path: str, ignore_patterns: list[str]) -> bool:
        parts = Path(rel_path).parts
        for pattern in ignore_patterns:
            if any(fnmatch.fnmatch(part, pattern) for part in parts):
                return True
            if fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def walk_files(self) -> list[str]:
        ignore_patterns = self.config()["ignore"]
        results = []
        for p in self.workdir.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(self.workdir))
                if not self._is_ignored(rel, ignore_patterns):
                    results.append(rel)
        return sorted(results)

    # -- core operations -------------------------------------------------

    def status(self) -> list[FileStatus]:
        db = self._db()
        try:
            tracked = set(db.all_tracked_paths())
            on_disk = set(self.walk_files())
            results = []

            for rel in sorted(on_disk | tracked):
                full = self.workdir / rel
                latest = db.latest(rel)
                if rel in on_disk and rel not in tracked:
                    results.append(FileStatus(rel, "new"))
                elif rel in on_disk and rel in tracked:
                    data = full.read_bytes()
                    current_hash = ObjectStore.hash_bytes(data)
                    if latest and latest["deleted"]:
                        results.append(FileStatus(rel, "new", current_hash))
                    elif latest and current_hash != latest["hash"]:
                        results.append(FileStatus(rel, "modified", current_hash, latest["hash"]))
                    else:
                        results.append(FileStatus(rel, "unchanged", current_hash, latest["hash"] if latest else None))
                elif rel not in on_disk and rel in tracked:
                    if not (latest and latest["deleted"]):
                        results.append(FileStatus(rel, "deleted", previous_hash=latest["hash"] if latest else None))
            return results
        finally:
            db.close()

    def snapshot(self, message: str = None, only_changed: bool = True) -> list[FileStatus]:
        """Take a snapshot of the current state. Returns what changed."""
        db = self._db()
        store = self._store()
        try:
            changes = [s for s in self.status() if s.kind != "unchanged"]
            for change in changes:
                full = self.workdir / change.path
                if change.kind == "deleted":
                    db.add_snapshot(change.path, change.previous_hash or "", 0,
                                     message=message, deleted=True)
                else:
                    data = full.read_bytes()
                    digest = store.write(data)
                    db.add_snapshot(change.path, digest, len(data), message=message)
            return changes
        finally:
            db.close()

    def history(self, path: str):
        db = self._db()
        try:
            return db.history(str(path))
        finally:
            db.close()

    def read_revision(self, path: str, revision_spec: str = None) -> bytes:
        db = self._db()
        store = self._store()
        try:
            row = db.resolve_revision(str(path), revision_spec)
            if row is None:
                raise KeyError(f"No such revision '{revision_spec}' for {path}")
            if row["deleted"]:
                raise KeyError(f"{path} was deleted at that revision")
            return store.read(row["hash"])
        finally:
            db.close()

    def restore(self, path: str, revision_spec: str = None, backup_current: bool = True):
        content = self.read_revision(path, revision_spec)
        full = self.workdir / path
        if backup_current and full.exists():
            self.snapshot(message="auto-backup before restore")
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)
