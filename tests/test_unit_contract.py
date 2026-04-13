"""Unit tests for validate_table_contract() in fpl_warehouse.contracts.

All tests use in-memory SQLite — no warehouse DB required.
"""

from __future__ import annotations

import sqlite3

import pytest

from fpl_warehouse.warehouse.contracts import (
    _player_scaled_min_rows,
    _team_scaled_min_rows,
    validate_table_contract,
)

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


def test_unit_contract_fails_exact_schema_mismatch_missing_column():
    rows = [(1, i, 5) for i in range(10)]
    conn = _make_conn(_DDL, rows)
    expected_schema = [
        ("gw", "INTEGER"),
        ("fpl_id", "INTEGER"),
        ("pts", "INTEGER"),
        ("extra", "TEXT"),
    ]
    with pytest.raises(ValueError, match="schema does not match expected contract"):
        validate_table_contract(
            conn,
            "items",
            _REQUIRED,
            _GRAIN,
            min_rows=1,
            expected_schema=expected_schema,
        )
    conn.close()


def test_unit_contract_fails_exact_schema_mismatch_wrong_type():
    rows = [(1, i, 5) for i in range(10)]
    conn = _make_conn(_DDL, rows)
    expected_schema = [
        ("gw", "INTEGER"),
        ("fpl_id", "TEXT"),
        ("pts", "INTEGER"),
    ]
    with pytest.raises(ValueError, match="schema does not match expected contract"):
        validate_table_contract(
            conn,
            "items",
            _REQUIRED,
            _GRAIN,
            min_rows=1,
            expected_schema=expected_schema,
        )
    conn.close()


def test_unit_contract_passes_exact_schema_match():
    rows = [(1, i, 5) for i in range(10)]
    conn = _make_conn(_DDL, rows)
    expected_schema = [
        ("gw", "INTEGER"),
        ("fpl_id", "INTEGER"),
        ("pts", "INTEGER"),
    ]
    validate_table_contract(
        conn,
        "items",
        _REQUIRED,
        _GRAIN,
        min_rows=1,
        expected_schema=expected_schema,
    )
    conn.close()


def test_player_scaled_min_rows_tracks_finished_gameweeks():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE dim_players (fpl_id INTEGER)")
    conn.execute("CREATE TABLE fact_fixtures (event INTEGER, finished INTEGER)")
    conn.executemany("INSERT INTO dim_players VALUES (?)", [(i,) for i in range(400)])
    conn.executemany(
        "INSERT INTO fact_fixtures VALUES (?, ?)",
        [(1, 1), (1, 1), (2, 1), (2, 1), (3, 0)],
    )

    assert _player_scaled_min_rows(conn) == 400
    conn.close()


def test_team_scaled_min_rows_tracks_finished_gameweeks():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE dim_teams (fpl_id INTEGER)")
    conn.execute("CREATE TABLE fact_fixtures (event INTEGER, finished INTEGER)")
    conn.executemany("INSERT INTO dim_teams VALUES (?)", [(i,) for i in range(20)])
    conn.executemany(
        "INSERT INTO fact_fixtures VALUES (?, ?)",
        [(1, 1), (1, 1), (2, 0)],
    )

    assert _team_scaled_min_rows(conn) == 10
    conn.close()
