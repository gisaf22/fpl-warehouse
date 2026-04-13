"""Database connection helpers shared across the warehouse pipeline."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def _load_fpl_env() -> None:
    """Load ~/Documents/FPL/.env into os.environ without overriding existing vars."""
    env_file = Path.home() / "Documents" / "FPL" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_fpl_env()

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_WAREHOUSE_PATH = _REPO_ROOT / "data" / "warehouse" / "master.db"
_DEFAULT_FPL_PATH = Path.home() / "Documents/FPL/data/fpl/fpl.db"
_DEFAULT_UNDERSTAT_PATH = Path.home() / "Documents/FPL/data/understat/understat.db"

DEFAULT_WAREHOUSE_DB: str = str(
    os.environ.get("WAREHOUSE_DB_PATH", _DEFAULT_WAREHOUSE_PATH)
)
DEFAULT_FPL_DB: str = str(
    os.environ.get("FPL_DB_PATH", _DEFAULT_FPL_PATH)
)
DEFAULT_UNDERSTAT_DB: str = str(
    os.environ.get("UNDERSTAT_DB_PATH", _DEFAULT_UNDERSTAT_PATH)
)


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply common SQLite settings for all project connections."""
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row


def connect_db(db_path: str) -> sqlite3.Connection:
    """Open an existing SQLite database without creating new files.

    Use this for source databases and read-only access paths where a missing
    file should fail fast instead of silently creating an empty database.
    """
    if db_path != ":memory:" and not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    _configure_connection(conn)
    return conn


def connect_warehouse(db_path: str) -> sqlite3.Connection:
    """Open or create the writable warehouse database.

    The warehouse is the single SQLite file this project owns and writes to.
    WAL mode is enabled here to support the single-writer, read-many pattern
    used by downstream consumers.
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    _configure_connection(conn)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn