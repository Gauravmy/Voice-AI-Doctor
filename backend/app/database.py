"""SQLite access layer.

Design notes
------------
* A short-lived connection is opened per operation (`connect()`); SQLite handles
  this cheaply and it avoids sharing a connection across asyncio tasks/threads.
* `isolation_level=None` puts sqlite3 in autocommit mode so transactions are
  explicit (`BEGIN IMMEDIATE` ... `COMMIT`) - see `transaction()`.
* `init_db()` is idempotent: it applies `schema.sql` (CREATE ... IF NOT EXISTS),
  seeds reference data only when the database is empty, and tops up future slots
  so a database seeded days ago still has upcoming availability.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent / "models" / "schema.sql"


def _db_path() -> Path:
    return Path(get_settings().database_path)


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_connection(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Write transaction. BEGIN IMMEDIATE takes the write lock up-front so the
    "is this slot free?" check and the INSERT happen atomically."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init_db(path: Path | None = None, *, seed: bool = True) -> None:
    from app.data.seed import ensure_slot_horizon, seed_database

    with get_connection(path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        if seed:
            doctor_count = conn.execute("SELECT COUNT(*) FROM doctors").fetchone()[0]
            if doctor_count == 0:
                seed_database(conn)
                logger.info("Database seeded with fictional demo data")
            with transaction(conn):  # one commit instead of one per INSERT
                added = ensure_slot_horizon(conn)
            if added:
                logger.info("Added %d upcoming slots to keep the booking horizon full", added)


def reset_db(path: Path | None = None) -> None:
    """Delete and recreate the database (used by `python -m app.data.reset`)."""
    db_path = path or _db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()
    init_db(db_path)
