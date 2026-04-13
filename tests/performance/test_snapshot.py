"""Tests for fact_player_performance_snapshot materialization.

The performance snapshot contains on-pitch performance outputs and explicit
windowed aggregates only. Tests here verify PIT correctness, per-90 math,
and the active snapshot contract column set.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpl_warehouse.builders.snapshots import materialize_player_performance_snapshot
from fpl_warehouse.warehouse.ddl import (
    DIM_PLAYERS_DDL,
    DIM_TEAMS_DDL,
    FACT_FIXTURES_DDL,
    FACT_PLAYER_GW_DDL,
    FACT_PLAYER_PERFORMANCE_SNAPSHOT_DDL,
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
    conn.execute(FACT_PLAYER_PERFORMANCE_SNAPSHOT_DDL)

    teams = [
        (1, 1, "Team 1", "Team 1", "T1"),
        (2, 2, "Team 2", "Team 2", "T2"),
        (3, 3, "Team 3", "Team 3", "T3"),
    ]
    conn.executemany(
        "INSERT INTO dim_teams (team_id, fpl_id, fpl_name, understat_name, short_name) "
        "VALUES (?, ?, ?, ?, ?)",
        teams,
    )

    players = [
        (201, "Player 201", 1, 4),
        (202, "Player 202", 2, 2),
        (203, "Player 203", 3, 2),
    ]
    conn.executemany(
        "INSERT INTO dim_players (fpl_id, web_name, team_id, element_type) "
        "VALUES (?, ?, ?, ?)",
        players,
    )

    # Columns: fpl_id, round, minutes, starts, total_points, clean_sheets,
    #          goals_conceded, bonus, expected_goals_conceded,
    #          creativity, threat, ict_index,
    #          clearances_blocks_interceptions, defensive_contribution,
    #          us_xgi, us_xa, us_xg
    player_gw_rows = [
        # P201 — forward, consistent 90 min
        (201, 1, 90, 1, 6,  0, 0, 0, 0.0,  10, 40, 8.0,  0, 0, 0.5, 0.2, 0.3),
        (201, 2, 90, 1, 8,  0, 0, 2, 0.0,  20, 60, 12.0, 0, 0, 0.8, 0.3, 0.5),
        (201, 3, 90, 1, 5,  0, 0, 0, 0.0,  5,  30, 6.0,  0, 0, 0.3, 0.1, 0.2),
        # P202 — defender, 1 appearance only
        (202, 1, 0,  0, 1,  0, 0, 0, 0.0,  0,  0,  0.0,  0, 0, 0.0, 0.0, 0.0),
        (202, 2, 45, 0, 2,  0, 0, 0, 0.0,  15, 5,  4.0,  2, 3, 0.1, 0.05, 0.05),
        (202, 3, 0,  0, 0,  0, 0, 0, 0.0,  0,  0,  0.0,  0, 0, 0.0, 0.0, 0.0),
        # P203 — defender, 3 appearances, clean sheets in GW1 + GW3
        (203, 1, 60, 1, 6,  1, 0, 0, 0.0,  5,  10, 6.0,  3, 4, 0.0, 0.0, 0.0),
        (203, 2, 90, 1, 2,  0, 1, 0, 0.8,  3,  15, 7.0,  5, 6, 0.0, 0.0, 0.0),
        (203, 3, 90, 1, 6,  1, 0, 0, 0.0,  10, 20, 8.0,  4, 5, 0.0, 0.1, 0.0),
    ]
    conn.executemany(
        "INSERT INTO fact_player_gw "
        "(fpl_id, round, minutes, starts, total_points, clean_sheets, "
        " goals_conceded, bonus, expected_goals_conceded, "
        " creativity, threat, ict_index, "
        " clearances_blocks_interceptions, defensive_contribution, us_xgi, us_xa, us_xg) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        player_gw_rows,
    )

    # Fixtures: GW1-3 finished, GW4 unfinished
    fixtures = [
        (1, 1, 1, 2, 2, 1, "2026-08-10T15:00:00Z", 1, 3, 2),
        (2, 2, 2, 3, 1, 0, "2026-08-16T15:00:00Z", 1, 2, 3),
        (3, 3, 1, 3, 1, 1, "2026-08-23T14:00:00Z", 1, 2, 2),
        (4, 4, 1, 2, None, None, "2026-08-30T14:00:00Z", 0, 2, 3),
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

    Views (int_player_gw_base, fct_player_performance_features) and the
    snapshot table are created by materialize_player_performance_snapshot.
    The returned connection has access to all three layers so SQL tests can
    run against any of them.
    """
    materialize_player_performance_snapshot(warehouse_db)
    conn = sqlite3.connect(warehouse_db)
    yield conn
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(conn: sqlite3.Connection, as_of_gw: int, fpl_id: int) -> dict:
    """Fetch a single snapshot row as a dict. Fails if the row is absent."""
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM fact_player_performance_snapshot LIMIT 0"
    ).description]
    row = conn.execute(
        "SELECT * FROM fact_player_performance_snapshot "
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
        "  FROM fact_player_performance_snapshot "
        "  GROUP BY as_of_gw, fpl_id HAVING n > 1"
        ")"
    ).fetchone()[0]
    assert dupes == 0


def test_snapshot_columns_match_contract(snapshot_conn):
    """Performance snapshot must match the active contract column set."""
    cols = [row[1] for row in snapshot_conn.execute(
        "PRAGMA table_info(fact_player_performance_snapshot)"
    ).fetchall()]
    assert cols == [
        "as_of_gw",
        "fpl_id",
        "team_fpl_id",
        "xgi_per90_last_5gws",
        "xg_per90_last_5gws",
        "xa_per90_last_5gws",
        "threat_per90_last_5gws",
        "creativity_per90_last_5gws",
        "ict_per90_last_5gws",
        "cbi_per90_last_5gws",
        "dc_per90_last_5gws",
        "gc_per90_last_5gws",
        "xgc_per90_last_5gws",
        "clean_sheet_rate_last_5gws",
        "bonus_per90_last_5gws",
        "bps_per90_last_5gws",
        "points_total_last_3_apps",
        "points_avg_last_3_apps",
        "points_std_last_3_apps",
        "xgi_total_last_3_apps",
        "threat_last_gw",
        "creativity_last_gw",
        "ict_last_gw",
        "points_last_app",
        "points_avg_prev_2_apps",
        "threat_avg_last_3_apps",
        "creativity_avg_last_3_apps",
    ]


def test_reasonable_row_coverage(snapshot_conn):
    """3 players × 3 finished GWs = 9 rows total."""
    total = snapshot_conn.execute(
        "SELECT COUNT(*) FROM fact_player_performance_snapshot"
    ).fetchone()[0]
    assert total == 9


def test_pit_window_uses_only_history_up_to_as_of_gw(snapshot_conn):
    """At as_of_gw=1, P201 window has only GW1 — xgi_per90 = 0.5*90/90 = 0.5."""
    row = _row(snapshot_conn, 1, 201)
    assert abs(row["xgi_per90_last_5gws"] - 0.5) < 1e-9


def test_per90_xa_at_gw3_p201(snapshot_conn):
    """P201 at as_of_gw=3: xa_per90 = (0.2+0.3+0.1)*90/270 = 0.2."""
    row = _row(snapshot_conn, 3, 201)
    expected = (0.2 + 0.3 + 0.1) * 90.0 / 270.0
    assert abs(row["xa_per90_last_5gws"] - expected) < 1e-9


def test_per90_xgi_at_gw3_p201(snapshot_conn):
    """P201 at as_of_gw=3: xgi_per90 = (0.5+0.8+0.3)*90/270 = 0.5333..."""
    row = _row(snapshot_conn, 3, 201)
    expected = (0.5 + 0.8 + 0.3) * 90.0 / 270.0
    assert abs(row["xgi_per90_last_5gws"] - expected) < 1e-9


def test_clean_sheet_rate_at_gw3_p203(snapshot_conn):
    """P203 at as_of_gw=3: clean sheet rate = 2 clean sheets / 3 GW window."""
    row = _row(snapshot_conn, 3, 203)
    assert abs(row["clean_sheet_rate_last_5gws"] - 2.0 / 3.0) < 1e-9


def test_per90_null_when_below_45_minutes(snapshot_conn):
    """P202 at as_of_gw=1 has 0 total minutes — per-90 rates must be NULL."""
    row = _row(snapshot_conn, 1, 202)
    assert row["xgi_per90_last_5gws"] is None
    assert row["xa_per90_last_5gws"] is None
    assert row["threat_per90_last_5gws"] is None
    assert row["creativity_per90_last_5gws"] is None


# ── SQL constraint tests (parametric) ─────────────────────────────────────────

def _collect_sql_tests() -> list[Path]:
    """Return all .sql test files in tests/performance/sql/, sorted by name."""
    if not _SQL_TEST_DIR.exists():
        return []
    return sorted(_SQL_TEST_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _collect_sql_tests(), ids=lambda p: p.stem)
def test_sql_constraint(snapshot_conn, sql_path):
    """Execute a SQL test file and assert it returns 0 failing rows.

    Each .sql file in tests/performance/sql/ is a SELECT that returns rows
    only when a constraint is violated. An empty result set means the test
    passed. This mirrors dbt's singular test format exactly.

    The snapshot_conn fixture provides access to:
      - int_player_gw_base                   (view)
      - fct_player_performance_features      (view)
      - fact_player_performance_snapshot     (table)
      - All source tables
    """
    failing_rows = run_sql_test(snapshot_conn, sql_path)
    assert failing_rows == [], (
        f"{sql_path.name} returned {len(failing_rows)} failing row(s):\n"
        + "\n".join(str(r) for r in failing_rows[:5])
    )
