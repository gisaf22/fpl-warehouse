"""Tests for fact_decision_snapshot data-type alignment.

Guards against the silent numpy.int64 ↔ SQLite INTEGER mismatch
where parameterised queries return 0 rows instead of erroring.
"""

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

WAREHOUSE = Path.home() / "Documents/FPL/data/warehouse/master.db"

# Expected SQLite column types from CREATE_SNAPSHOT_TABLE DDL
EXPECTED_TYPES = {
    "as_of_gw": "INTEGER",
    "target_gw": "INTEGER",
    "fpl_id": "INTEGER",
    "web_name": "TEXT",
    "fpl_name": "TEXT",
    "team": "TEXT",
    "team_fpl_id": "INTEGER",
    "position": "TEXT",
    "xgi_per90": "REAL",
    "bonus_per_app": "REAL",
    "cs_pct": "REAL",
    "gc_per90": "REAL",
    "xgc_per90": "REAL",
    "cbi_per90": "REAL",
    "def_per90": "REAL",
    "p_play": "REAL",
    "p_start": "REAL",
    "pts_std": "REAL",
    "now_cost": "REAL",
    "selected_by": "REAL",
    "fixture_count": "INTEGER",
    "is_home": "INTEGER",
    "pts_last_3": "REAL",
    "xgi_last_3": "REAL",
    "us_xg_last3": "REAL",
    "transfer_delta": "INTEGER",
    "avg_minutes": "REAL",
    "num_gwks_played": "INTEGER",
}

INTEGER_COLS = [c for c, t in EXPECTED_TYPES.items() if t == "INTEGER"]


@pytest.fixture(scope="module")
def conn():
    if not WAREHOUSE.exists():
        pytest.skip("Warehouse not built — run `uv run fpl-warehouse -v` first")
    c = sqlite3.connect(WAREHOUSE)
    yield c
    c.close()


@pytest.fixture(scope="module")
def sample_row(conn):
    """Fetch one row via the standard parameterised query path."""
    row = conn.execute(
        "SELECT * FROM fact_decision_snapshot WHERE as_of_gw = ? LIMIT 1",
        (1,),
    ).fetchone()
    if row is None:
        pytest.skip("fact_decision_snapshot is empty")
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM fact_decision_snapshot LIMIT 0"
    ).description]
    return dict(zip(cols, row))


class TestSnapshotSchema:
    """Verify the DDL-level schema matches expectations."""

    def test_table_exists(self, conn):
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "fact_decision_snapshot" in tables

    def test_column_names_match(self, conn):
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM fact_decision_snapshot LIMIT 0"
        ).description]
        assert set(cols) == set(EXPECTED_TYPES.keys())

    def test_column_types_match_ddl(self, conn):
        """PRAGMA table_info types must match the DDL declaration."""
        rows = conn.execute(
            "PRAGMA table_info(fact_decision_snapshot)"
        ).fetchall()
        actual = {r[1]: r[2] for r in rows}
        for col, expected_type in EXPECTED_TYPES.items():
            assert actual.get(col) == expected_type, (
                f"Column {col}: expected {expected_type}, got {actual.get(col)}"
            )


class TestSnapshotRoundtrip:
    """Verify that parameterised queries work with native Python types."""

    def test_integer_cols_are_python_int(self, sample_row):
        """INTEGER columns must come back as Python int, not numpy.int64."""
        for col in INTEGER_COLS:
            val = sample_row[col]
            if val is None:
                continue  # NULLable columns are fine
            assert type(val) is int, (
                f"Column {col}: expected int, got {type(val).__name__} ({val!r})"
            )

    def test_parameterised_query_returns_rows(self, conn):
        """Core regression test: parameterised WHERE on each INTEGER column
        must return >0 rows when the value exists in the table."""
        for col in INTEGER_COLS:
            # Get a known value for this column
            row = conn.execute(
                f"SELECT {col} FROM fact_decision_snapshot "  # noqa: S608
                f"WHERE {col} IS NOT NULL LIMIT 1"
            ).fetchone()
            if row is None:
                continue
            known_val = row[0]

            # Query with native int — must find rows
            count = conn.execute(
                f"SELECT COUNT(*) FROM fact_decision_snapshot "  # noqa: S608
                f"WHERE {col} = ?",
                (int(known_val),),
            ).fetchone()[0]
            assert count > 0, (
                f"Parameterised query on {col}={known_val} returned 0 rows"
            )

    def test_as_of_gw_param_binding(self, conn):
        """Explicit regression test for the numpy.int64 bug.

        Verifies that querying with the exact value returned by
        MAX(as_of_gw) — which pandas returns as numpy.int64 — works
        when cast to native int.
        """
        max_gw = conn.execute(
            "SELECT MAX(as_of_gw) FROM fact_decision_snapshot"
        ).fetchone()[0]
        if max_gw is None:
            pytest.skip("No snapshots")

        count = conn.execute(
            "SELECT COUNT(*) FROM fact_decision_snapshot WHERE as_of_gw = ?",
            (int(max_gw),),
        ).fetchone()[0]
        assert count > 0, (
            f"MAX(as_of_gw)={max_gw} query returned 0 rows — "
            "possible type mismatch"
        )


class TestSnapshotDataIntegrity:
    """Basic data integrity checks."""

    def test_no_orphan_target_gws(self, conn):
        """Every target_gw should equal as_of_gw + 1."""
        bad = conn.execute(
            "SELECT COUNT(*) FROM fact_decision_snapshot "
            "WHERE target_gw != as_of_gw + 1"
        ).fetchone()[0]
        assert bad == 0, f"{bad} rows have target_gw != as_of_gw + 1"

    def test_no_duplicate_player_per_gw(self, conn):
        """Primary key: (as_of_gw, fpl_id) must be unique."""
        dupes = conn.execute(
            "SELECT COUNT(*) FROM ("
            "  SELECT as_of_gw, fpl_id, COUNT(*) AS n "
            "  FROM fact_decision_snapshot "
            "  GROUP BY as_of_gw, fpl_id HAVING n > 1"
            ")"
        ).fetchone()[0]
        assert dupes == 0, f"{dupes} duplicate (as_of_gw, fpl_id) pairs"

    def test_gw_coverage_contiguous(self, conn):
        """as_of_gw values should be contiguous from 1 to max."""
        rows = conn.execute(
            "SELECT DISTINCT as_of_gw FROM fact_decision_snapshot ORDER BY as_of_gw"
        ).fetchall()
        gws = [r[0] for r in rows]
        if not gws:
            pytest.skip("No snapshots")
        assert gws == list(range(1, max(gws) + 1)), (
            f"Non-contiguous GWs: {gws}"
        )
