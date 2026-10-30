"""Durable simulator job records shared by the web server and the desktop worker.

Job state lives in SQLite next to the run artifacts, so a worker restart (crash,
timeout or app exit) never loses track of a run. Each live job engine holds an
OS-level lock on its own owner file; a record whose owner lock can be taken
belongs to a dead process and may be reclaimed. Results stay in the published
artifact JSON, never in the database.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
ACTIVE = ("queued", "running")
TERMINAL = ("completed", "failed", "cancelled")


class OwnerLock:
    """Exclusive, non-blocking lock released by the OS when its process dies."""

    def __init__(self, path: Path):
        self.path = path
        self.handle: Any = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+b")  # noqa: SIM115 - held for the lock's lifetime
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        self.handle = handle
        return True

    def release(self, *, remove: bool = False) -> None:
        if self.handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
        if remove:
            self.path.unlink(missing_ok=True)


class JobStore:
    """Thread-safe for callers that serialize writes (the Jobs lock does)."""

    def __init__(self, root: Path, owner: str):
        self.root = root
        self.owner = owner
        self.owners = root / ".jobs-owners"
        self.lock = OwnerLock(self.owners / f"{owner}.lock")
        if not self.lock.acquire():
            raise RuntimeError("job engine owner lock is already held")
        self.db = sqlite3.connect(root / "jobs.sqlite3", check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"job store schema {version} is newer than this HEPLab")
        with self.db:
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    config TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    idempotency_key TEXT UNIQUE,
                    owner TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    phase TEXT,
                    progress TEXT,
                    error TEXT,
                    created REAL NOT NULL,
                    updated REAL NOT NULL
                )"""
            )
            self.db.execute("CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status)")
            self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        value = dict(row)
        value["config"] = json.loads(value["config"])
        value["progress"] = json.loads(value["progress"]) if value["progress"] else None
        return value

    def insert(self, identity: str, config: dict, fingerprint: str, key: str | None) -> None:
        now = time.time()
        with self.db:
            self.db.execute(
                "INSERT INTO jobs (id, status, config, fingerprint, idempotency_key, owner,"
                " created, updated) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)",
                (identity, json.dumps(config), fingerprint, key, self.owner, now, now),
            )

    def get(self, identity: str) -> dict | None:
        return self._row(self.db.execute("SELECT * FROM jobs WHERE id = ?", (identity,)).fetchone())

    def by_key(self, key: str) -> dict | None:
        row = self.db.execute("SELECT * FROM jobs WHERE idempotency_key = ?", (key,)).fetchone()
        return self._row(row)

    def update(self, identity: str, **fields: Any) -> None:
        if "progress" in fields and fields["progress"] is not None:
            fields["progress"] = json.dumps(fields["progress"])
        fields["updated"] = time.time()
        columns = ", ".join(f"{name} = ?" for name in fields)
        with self.db:
            self.db.execute(f"UPDATE jobs SET {columns} WHERE id = ?", (*fields.values(), identity))

    def active(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM jobs WHERE status IN (?, ?) ORDER BY created", ACTIVE
        ).fetchall()
        return [value for row in rows if (value := self._row(row)) is not None]

    def recent(self, limit: int = 50) -> list[dict]:
        rows = self.db.execute(
            "SELECT * FROM jobs ORDER BY created DESC LIMIT ?", (limit,)
        ).fetchall()
        return [value for row in rows if (value := self._row(row)) is not None]

    def owner_alive(self, owner: str) -> bool:
        if owner == self.owner:
            return True
        probe = OwnerLock(self.owners / f"{owner}.lock")
        if probe.acquire():
            probe.release(remove=True)
            return False
        return True

    def claim(self, identity: str, previous_owner: str, *, crashed: bool) -> bool:
        """Atomically take over a dead owner's record; a crash mid-run costs one attempt."""
        with self.db:
            cursor = self.db.execute(
                "UPDATE jobs SET owner = ?, status = 'queued', attempts = attempts + ?,"
                " updated = ? WHERE id = ? AND owner = ? AND status IN (?, ?)",
                (self.owner, int(crashed), time.time(), identity, previous_owner, *ACTIVE),
            )
        return cursor.rowcount == 1

    def prune(self, keep: int, *, older_than: float) -> list[str]:
        """Delete terminal rows outside the count/age window and return their IDs."""
        candidates = self.db.execute(
            "SELECT id FROM jobs WHERE status IN (?, ?, ?) AND (created < ? OR id NOT IN"
            " (SELECT id FROM jobs ORDER BY created DESC LIMIT ?))",
            (*TERMINAL, older_than, keep),
        ).fetchall()
        identities = [row["id"] for row in candidates]
        if not identities:
            return []
        with self.db:
            self.db.execute(
                "DELETE FROM jobs WHERE status IN (?, ?, ?) AND (created < ? OR id NOT IN"
                " (SELECT id FROM jobs ORDER BY created DESC LIMIT ?))",
                (*TERMINAL, older_than, keep),
            )
        return identities

    def close(self) -> None:
        self.db.close()
        self.lock.release(remove=True)
