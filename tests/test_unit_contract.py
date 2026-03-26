"""Unit tests for validate_table_contract() in fpl_warehouse.build.

All tests use in-memory SQLite — no warehouse DB required.
"""

from __future__ import annotations

import sqlite3

import pytest

from fpl_warehouse.build import validate_table_contract

pytestmark = pytest.mark.unit


def _make_conn(ddl: str, rows: list[tuple]) -> sqlite3.Connection:
    """Create an in-memory DB with a single 'items' table."""
    conn = sqlite3.connect(":memory:")
    conn.execute(ddl)
    conn.executemany("INSERT INTO items VALUES (?, ?, ?)", rows)
    conn.commit()
    return conn


_DDL = "CREATE TABLE items (gw INTEGER, fpl_id INTEGER, pts INTEGER)"
_REQUIRED = ["gw", "fpl_id", "pts"]
_GRAIN = ["gw", "fpl_id"]


def test_unit_contract_passes_clean_table():
    rows = [(gw, i, 5) for gw in range(1, 5) for i in range(300)]
    conn = _make_conn(_DDL, rows)
    # Should not raise
    validate_table_contract(conn, "items", _REQUIRED, _GRAIN, min_rows=1)
    conn.close()


def test_unit_contract_fails_missing_col():
    rows = [(1, i, 5) for i in range(10)]
    conn = _make_conn(_DDL, rows)
    with pytest.raises(ValueError, match="missing required columns"):
        validate_table_contract(
            conn, "items", ["gw", "fpl_id", "nonexistent"], _GRAIN, min_rows=1
        )
    conn.close()


def test_unit_contract_fails_duplicate_grain():
    # Insert duplicate (gw=1, fpl_id=99) pair
    rows = [(1, 99, 5), (1, 99, 8), (1, 100, 3)]
    conn = _make_conn(_DDL, rows)
    with pytest.raises(ValueError, match="duplicate"):
        validate_table_contract(conn, "items", _REQUIRED, _GRAIN, min_rows=1)
    conn.close()
