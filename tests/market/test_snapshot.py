"""Tests for fact_player_market_snapshot materialization.

Structure
---------
Fixture setup
    warehouse_db  — creates schema and inserts controlled test data into a
                    temp SQLite file. Data exercises point-in-time state,
                    3-GW velocity, NULL policy, and PIT correctness.
    snapshot_conn — calls materialize_player_market_snapshot, then
                    returns an open connection for assertions.

Test groups
    Behavioural tests (test_*)
        Assert specific known values from the controlled fixture data.
        These verify PIT correctness, now_cost math, transfer_delta
        arithmetic, velocity computation, and NULL semantics.

    SQL constraint tests (test_sql_constraint)
        Parametric: one test case per .sql file in tests/market/sql/.
        Each file returns 0 rows on pass. These run against snapshot_conn.

        fct_test_*  — tests on fct_player_market_features view
        fact_test_* — tests on fact_player_market_snapshot table

Player coverage
---------------
Player 301 (T1): present in GW1–GW4.
    GW1: value=55, selected=50000, transfers_in=10000, transfers_out=5000
    GW2: value=55, selected=60000, transfers_in=8000,  transfers_out=3000
    GW3: value=56, selected=65000, transfers_in=12000, transfers_out=4000
    GW4: value=57, selected=70000, transfers_in=15000, transfers_out=2000

Player 302 (T2): present in GW2–GW4 only (no GW1 row).
    GW2: value=45, selected=80000, transfers_in=5000,  transfers_out=1000
    GW3: value=46, selected=85000, transfers_in=6000,  transfers_out=2000
    GW4: value=47, selected=90000, transfers_in=7000,  transfers_out=3000

GW1–GW4 are finished. GW5 is unfinished.

Expected snapshot rows:
    GW1: P301 only        → 1 row
    GW2: P301 + P302      → 2 rows
    GW3: P301 + P302      → 2 rows
    GW4: P301 + P302      → 2 rows
    Total: 7 rows
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpl_warehouse.builders.snapshots import materialize_player_market_snapshot
from fpl_warehouse.warehouse.ddl import (
    DIM_PLAYERS_DDL,
    DIM_TEAMS_DDL,
    FACT_FIXTURES_DDL,
    FACT_PLAYER_GW_DDL,
    FACT_PLAYER_MARKET_SNAPSHOT_DDL,
)
from fpl_warehouse.sql_runner import run_sql_test

pytestmark = pytest.mark.unit

_SQL_TEST_DIR = Path(__file__).parent / "sql"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def warehouse_db(tmp_path):
    """Minimal warehouse database with controlled data for deterministic tests."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(DIM_TEAMS_DDL)
    conn.execute(DIM_PLAYERS_DDL)
    conn.execute(FACT_PLAYER_GW_DDL)
    conn.execute(FACT_FIXTURES_DDL)
    conn.execute(FACT_PLAYER_MARKET_SNAPSHOT_DDL)

    teams = [
        (1, 1, "Team 1", "Team 1", "T1"),
        (2, 2, "Team 2", "Team 2", "T2"),
    ]
    conn.executemany(
        "INSERT INTO dim_teams (team_id, fpl_id, fpl_name, understat_name, short_name) "
        "VALUES (?, ?, ?, ?, ?)",
        teams,
    )

    players = [
        (301, "Player 301", 1, 4),
        (302, "Player 302", 2, 3),
    ]
    conn.executemany(
        "INSERT INTO dim_players (fpl_id, web_name, team_id, element_type) "
        "VALUES (?, ?, ?, ?)",
        players,
    )

    # Columns: fpl_id, round, minutes, starts, total_points, value, selected,
    #          transfers_in, transfers_out
    player_gw_rows = [
        # P301 — present in all 4 GWs
        (301, 1, 90, 1, 6, 55, 50000, 10000, 5000),
        (301, 2, 90, 1, 8, 55, 60000,  8000, 3000),
        (301, 3, 90, 1, 5, 56, 65000, 12000, 4000),
        (301, 4, 90, 1, 7, 57, 70000, 15000, 2000),
        # P302 — no GW1 row
        (302, 2, 60, 1, 4, 45, 80000,  5000, 1000),
        (302, 3, 90, 1, 3, 46, 85000,  6000, 2000),
        (302, 4, 45, 0, 2, 47, 90000,  7000, 3000),
    ]
    conn.executemany(
        "INSERT INTO fact_player_gw "
        "(fpl_id, round, minutes, starts, total_points, value, selected, "
        " transfers_in, transfers_out) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        player_gw_rows,
    )

    # GW1–GW4 finished, GW5 unfinished
    fixtures = [
        (1, 1, 1, 2, 2, 1, "2026-08-10T15:00:00Z", 1, 3, 2),
        (2, 2, 1, 2, 1, 0, "2026-08-17T15:00:00Z", 1, 2, 3),
        (3, 3, 2, 1, 1, 1, "2026-08-24T14:00:00Z", 1, 2, 2),
        (4, 4, 1, 2, 3, 0, "2026-08-31T14:00:00Z", 1, 3, 2),
        (5, 5, 2, 1, None, None, "2026-09-07T14:00:00Z", 0, 2, 3),
    ]
    conn.executemany(
        "INSERT INTO fact_fixtures "
        "(fixture_id, event, home_team_id, away_team_id, home_score, away_score, "
        " kickoff_time, finished, home_difficulty, away_difficulty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fixtures,
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture()
def snapshot_conn(warehouse_db):
    """Materialise the snapshot and return an open connection.

    Views (int_player_gw_base, fct_player_market_features) and the snapshot
    table are created by materialize_player_market_snapshot. The returned
    connection has access to all three layers so SQL tests can run against any.
    """
    materialize_player_market_snapshot(warehouse_db)
    conn = sqlite3.connect(warehouse_db)
    yield conn
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(conn: sqlite3.Connection, as_of_gw: int, fpl_id: int) -> dict:
    """Fetch a single snapshot row as a dict. Fails if the row is absent."""
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM fact_player_market_snapshot LIMIT 0"
    ).description]
    row = conn.execute(
        "SELECT * FROM fact_player_market_snapshot "
        "WHERE as_of_gw = ? AND fpl_id = ?",
        (as_of_gw, fpl_id),
    ).fetchone()
    assert row is not None, f"No row for as_of_gw={as_of_gw}, fpl_id={fpl_id}"
    return dict(zip(cols, row))


# ── Behavioural tests ─────────────────────────────────────────────────────────

def test_snapshot_grain_is_unique(snapshot_conn):
    """Primary key (as_of_gw, fpl_id) must have no duplicates."""
    dupes = snapshot_conn.execute(
        "SELECT COUNT(*) FROM ("
        "  SELECT as_of_gw, fpl_id, COUNT(*) AS n "
        "  FROM fact_player_market_snapshot "
        "  GROUP BY as_of_gw, fpl_id HAVING n > 1"
        ")"
    ).fetchone()[0]
    assert dupes == 0


def test_snapshot_columns_match_contract(snapshot_conn):
    """Market snapshot must expose raw market state plus derived velocity only."""
    cols = [row[1] for row in snapshot_conn.execute(
        "PRAGMA table_info(fact_player_market_snapshot)"
    ).fetchall()]
    assert cols == [
        "as_of_gw",
        "fpl_id",
        "now_cost",
        "selected_by",
        "transfers_in",
        "transfers_out",
        "transfers_net",
        "price_delta_last_3gws",
        "ownership_delta_last_3gws",
    ]


def test_reasonable_row_coverage(snapshot_conn):
    """GW1: P301 only (1 row); GW2–GW4: P301 + P302 (2 rows each) = 7 total."""
    total = snapshot_conn.execute(
        "SELECT COUNT(*) FROM fact_player_market_snapshot"
    ).fetchone()[0]
    assert total == 7


def test_p302_absent_at_gw1(snapshot_conn):
    """P302 has no fact_player_gw row for round=1 — must not appear at as_of_gw=1."""
    row = snapshot_conn.execute(
        "SELECT * FROM fact_player_market_snapshot "
        "WHERE as_of_gw = 1 AND fpl_id = 302"
    ).fetchone()
    assert row is None


def test_now_cost_divided_by_10(snapshot_conn):
    """P301 at as_of_gw=4: now_cost = value(57) / 10 = 5.7."""
    row = _row(snapshot_conn, 4, 301)
    assert abs(row["now_cost"] - 5.7) < 1e-9


def test_now_cost_at_gw1(snapshot_conn):
    """P301 at as_of_gw=1: now_cost = 55 / 10 = 5.5."""
    row = _row(snapshot_conn, 1, 301)
    assert abs(row["now_cost"] - 5.5) < 1e-9


def test_selected_by_is_raw_count(snapshot_conn):
    """P301 at as_of_gw=2: selected_by = 60000 (raw, not normalised)."""
    row = _row(snapshot_conn, 2, 301)
    assert row["selected_by"] == 60000


def test_transfers_net_is_in_minus_out(snapshot_conn):
    """P301 at as_of_gw=3: transfers_net = 12000 - 4000 = 8000."""
    row = _row(snapshot_conn, 3, 301)
    assert row["transfers_net"] == 8000


def test_raw_transfer_columns_are_preserved(snapshot_conn):
    """Market snapshot must retain raw transfer counts alongside transfers_net."""
    row = _row(snapshot_conn, 3, 301)
    assert row["transfers_in"] == 12000
    assert row["transfers_out"] == 4000


def test_pit_uses_only_anchor_round(snapshot_conn):
    """P301 at as_of_gw=1 must reflect only GW1 data, not GW4.

    now_cost at as_of_gw=1 should be 5.5 (value=55), not 5.7 (GW4 value=57).
    """
    row = _row(snapshot_conn, 1, 301)
    assert abs(row["now_cost"] - 5.5) < 1e-9
    assert row["now_cost"] != 5.7


def test_velocity_null_before_gw4(snapshot_conn):
    """Price and ownership velocity must be NULL at as_of_gw < 4.

    The lag anchor round = as_of_gw - 3 would be <= 0 for GW1–3, which does
    not exist in fact_player_gw. velocity must be NULL, not 0.
    """
    for gw in (1, 2, 3):
        row = _row(snapshot_conn, gw, 301)
        assert row["price_delta_last_3gws"] is None, (
            f"Expected price_delta_last_3gws NULL at as_of_gw={gw}"
        )
        assert row["ownership_delta_last_3gws"] is None, (
            f"Expected ownership_delta_last_3gws NULL at as_of_gw={gw}"
        )


def test_price_velocity_at_gw4_p301(snapshot_conn):
    """P301 at as_of_gw=4: price_velocity_3gw = (57 - 55) / 10 = 0.2.

    Lag anchor: round = 4 - 3 = 1, value = 55.
    Now anchor: round = 4, value = 57.
    """
    row = _row(snapshot_conn, 4, 301)
    assert abs(row["price_delta_last_3gws"] - 0.2) < 1e-9


def test_ownership_velocity_at_gw4_p301(snapshot_conn):
    """P301 at as_of_gw=4: ownership_velocity_3gw = 70000 - 50000 = 20000.

    Lag anchor: round = 1, selected = 50000.
    Now anchor: round = 4, selected = 70000.
    """
    row = _row(snapshot_conn, 4, 301)
    assert row["ownership_delta_last_3gws"] == 20000


def test_velocity_null_when_lag_anchor_missing(snapshot_conn):
    """P302 at as_of_gw=4: lag anchor is round=1 which P302 has no row for.

    Both velocity features must be NULL.
    """
    row = _row(snapshot_conn, 4, 302)
    assert row["price_delta_last_3gws"] is None
    assert row["ownership_delta_last_3gws"] is None


def test_now_cost_null_when_anchor_round_missing(snapshot_conn):
    """P302 at as_of_gw=2: now_cost from round=2 — P302 has a GW2 row, so not NULL.

    This also verifies the LEFT JOIN returns values when the row exists.
    """
    row = _row(snapshot_conn, 2, 302)
    assert row["now_cost"] is not None
    assert abs(row["now_cost"] - 4.5) < 1e-9


# ── SQL constraint tests (parametric) ─────────────────────────────────────────

def _collect_sql_tests() -> list[Path]:
    """Return all .sql test files in tests/market/sql/, sorted by name."""
    if not _SQL_TEST_DIR.exists():
        return []
    return sorted(_SQL_TEST_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _collect_sql_tests(), ids=lambda p: p.stem)
def test_sql_constraint(snapshot_conn, sql_path):
    """Execute a SQL test file and assert it returns 0 failing rows.

    Each .sql file in tests/market/sql/ is a SELECT that returns rows only
    when a constraint is violated. An empty result set means the test passed.

    The snapshot_conn fixture provides access to:
      - int_player_gw_base             (view)
      - fct_player_market_features     (view)
      - fact_player_market_snapshot    (table)
      - All source tables
    """
    failing_rows = run_sql_test(snapshot_conn, sql_path)
    assert failing_rows == [], (
        f"{sql_path.name} returned {len(failing_rows)} failing row(s):\n"
        + "\n".join(str(r) for r in failing_rows[:5])
    )
