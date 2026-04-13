"""SQL model runner for the fpl_warehouse layered architecture.

Provides two primitives used by build.py and the test suite:

  create_view(conn, sql_path)
      Reads a .sql file containing a CREATE VIEW statement and executes it
      against the given connection. Idempotent: uses CREATE VIEW IF NOT EXISTS.

  run_sql_test(conn, sql_path) -> list[tuple]
      Reads a .sql file containing a SELECT query that returns 0 rows on pass
      and non-zero rows on failure. Returns the failing rows. An empty list
      means the test passed.

Design contract
---------------
- SQL files are read from disk at call time — no caching. This ensures the
  test suite always reflects the file on disk, not a stale in-memory copy.
- No parameters are injected into SQL files. All bindings (e.g. as_of_gw) are
  resolved inside the SQL itself via CTEs (e.g. the all_gws spine).
- The runner does not manage transactions. The caller is responsible for
  commit/rollback.
- This module has no dependencies beyond the Python standard library and
  sqlite3.

Future dbt migration
--------------------
This module is the manual equivalent of dbt's model executor and test runner.
When migrating to dbt, this file can be deleted. The layered .sql files in
models/ map directly to dbt model files; tests/sql/ maps to dbt singular tests.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def create_view(conn: sqlite3.Connection, sql_path: Path) -> None:
    """Execute a CREATE VIEW statement from a .sql file.

    Args:
        conn:     Open SQLite connection. Caller owns the transaction.
        sql_path: Path to a .sql file containing exactly one CREATE VIEW
                  statement. The file must use CREATE VIEW IF NOT EXISTS so
                  repeated calls are safe within the same session.

    Raises:
        sqlite3.OperationalError: if the SQL is malformed or the view name
            conflicts with an existing table (not a view).
        FileNotFoundError: if sql_path does not exist.
    """
    sql = sql_path.read_text()
    conn.execute(sql)


def run_sql_test(conn: sqlite3.Connection, sql_path: Path) -> list[tuple]:
    """Execute a SQL test file and return any failing rows.

    A SQL test file is a SELECT query designed so that:
      - 0 rows returned  → test passes
      - >0 rows returned → test fails; each row describes a violation

    Args:
        conn:     Open SQLite connection with the target tables/views available.
        sql_path: Path to a .sql file containing a single SELECT statement.

    Returns:
        A list of tuples, one per failing row. Empty list means the test passed.

    Raises:
        sqlite3.OperationalError: if the SQL references a table or view that
            does not exist in conn, or if the SQL is malformed.
        FileNotFoundError: if sql_path does not exist.
    """
    sql = sql_path.read_text()
    return conn.execute(sql).fetchall()
