"""Tests for fact_team_performance_context_snapshot materialization.

These tests focus on PIT safety for historical team and opponent context,
including timestamp-gated validation where match-level source times exist.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpl_warehouse.builders.snapshots import (
    materialize_team_performance_context_snapshot,
)
from fpl_warehouse.sql_runner import run_sql_test
from fpl_warehouse.warehouse.ddl import (
    DIM_TEAMS_DDL,
    FACT_FIXTURES_DDL,
    FACT_MATCH_STATS_DDL,
    FACT_TEAM_PERFORMANCE_CONTEXT_SNAPSHOT_DDL,
)

pytestmark = pytest.mark.unit

_SQL_TEST_DIR = Path(__file__).parent / "sql"


@pytest.fixture()
def warehouse_db(tmp_path):
    """Warehouse DB with one dirty post-cutoff match_stats row.

    The dirty row has event=2 but a datetime after the finished-fixture cutoff
    for as_of_gw=2. PIT validation should exclude it from historical context.
    """
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(DIM_TEAMS_DDL)
    conn.execute(FACT_FIXTURES_DDL)
    conn.execute(FACT_MATCH_STATS_DDL)
    conn.execute(FACT_TEAM_PERFORMANCE_CONTEXT_SNAPSHOT_DDL)

    teams = [
        (1, 1, "Team 1", "Team 1", "T1"),
        (2, 2, "Team 2", "Team 2", "T2"),
    ]
    conn.executemany(
        "INSERT INTO dim_teams (team_id, fpl_id, fpl_name, understat_name, short_name) "
        "VALUES (?, ?, ?, ?, ?)",
        teams,
    )

    fixtures = [
        (1, 1, 1, 2, 2, 1, "2026-08-10T15:00:00Z", 1, 3, 2),
        (2, 2, 1, 2, 1, 0, "2026-08-17T15:00:00Z", 1, 3, 2),
        (3, 3, 1, 2, None, None, "2026-08-24T15:00:00Z", 0, 3, 2),
    ]
    conn.executemany(
        "INSERT INTO fact_fixtures "
        "(fixture_id, event, home_team_id, away_team_id, home_score, away_score, "
        " kickoff_time, finished, home_difficulty, away_difficulty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fixtures,
    )

    match_stats = [
        (101, 1, 1, 1, 2, "T1", "T2",
         2, 1, 1.0, 0.5, 9.0, 11.0, 8, 4, 10, 7, 5, 3,
         0.5, 0.3, 0.2, "2026-08-10T15:00:00"),
        (102, 2, 2, 1, 2, "T1", "T2",
         1, 0, 2.0, 0.7, 10.0, 10.0, 6, 3, 9, 6, 4, 2,
         0.55, 0.25, 0.2, "2026-08-17T15:00:00"),
        (999, 99, 2, 1, 2, "T1", "T2",
         5, 4, 5.0, 4.0, 7.0, 13.0, 12, 9, 16, 13, 8, 7,
         0.5, 0.25, 0.25, "2026-08-20T15:00:00"),
    ]
    conn.executemany(
        "INSERT INTO fact_match_stats "
        "(understat_match_id, fpl_fixture_id, event, "
        " home_fpl_id, away_fpl_id, home_team_name, away_team_name, "
        " home_goals, away_goals, home_xg, away_xg, "
        " home_ppda, away_ppda, home_deep, away_deep, "
        " home_shots, away_shots, home_sot, away_sot, "
        " prob_home, prob_draw, prob_away, datetime) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        match_stats,
    )
    conn.commit()
    conn.close()
    return str(db_path)


@pytest.fixture()
def snapshot_conn(warehouse_db):
    """Materialise the snapshot and return an open connection."""
    materialize_team_performance_context_snapshot(warehouse_db)
    conn = sqlite3.connect(warehouse_db)
    yield conn
    conn.close()


def _row(conn: sqlite3.Connection, as_of_gw: int, team_fpl_id: int) -> dict:
    """Fetch a single snapshot row as a dict. Fails if the row is absent."""
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM fact_team_performance_context_snapshot LIMIT 0"
    ).description]
    row = conn.execute(
        "SELECT * FROM fact_team_performance_context_snapshot "
        "WHERE as_of_gw = ? AND team_fpl_id = ?",
        (as_of_gw, team_fpl_id),
    ).fetchone()
    assert row is not None, (
        f"No row for as_of_gw={as_of_gw}, team_fpl_id={team_fpl_id}"
    )
    return dict(zip(cols, row))


def test_snapshot_grain_is_unique(snapshot_conn):
    """Primary key (as_of_gw, team_fpl_id) must have no duplicates."""
    dupes = snapshot_conn.execute(
        "SELECT COUNT(*) FROM ("
        "  SELECT as_of_gw, team_fpl_id, COUNT(*) AS n "
        "  FROM fact_team_performance_context_snapshot "
        "  GROUP BY as_of_gw, team_fpl_id HAVING n > 1"
        ")"
    ).fetchone()[0]
    assert dupes == 0


def test_snapshot_columns_match_contract(snapshot_conn):
    """Team performance context snapshot must match the active contract."""
    cols = [row[1] for row in snapshot_conn.execute(
        "PRAGMA table_info(fact_team_performance_context_snapshot)"
    ).fetchall()]
    assert cols == [
        "as_of_gw",
        "team_fpl_id",
        "opponent_team_fpl_id",
        "team_xg_total_last_3gws",
        "team_xgc_total_last_3gws",
        "team_ppda_avg_last_3gws",
        "team_deep_total_last_3gws",
        "team_sot_total_last_3gws",
        "opponent_xg_total_last_3gws",
        "opponent_xgc_total_last_3gws",
        "opponent_xgc_avg_last_3gws",
        "opponent_ppda_avg_last_3gws",
        "opponent_sot_total_last_3gws",
    ]


def test_reasonable_row_coverage(snapshot_conn):
    """2 teams × 2 finished GWs = 4 rows total."""
    total = snapshot_conn.execute(
        "SELECT COUNT(*) FROM fact_team_performance_context_snapshot"
    ).fetchone()[0]
    assert total == 4


def test_post_cutoff_match_datetime_is_excluded(snapshot_conn):
    """The dirty event=2 row dated after the GW2 cutoff must be excluded."""
    count_rows = snapshot_conn.execute(
        "SELECT COUNT(*) FROM int_team_fixture_base "
        "WHERE as_of_gw = 2 AND team_fpl_id = 1"
    ).fetchone()[0]
    assert count_rows == 2

    row = _row(snapshot_conn, 2, 1)
    assert abs(row["team_xg_total_last_3gws"] - 3.0) < 1e-9
    assert abs(row["team_xgc_total_last_3gws"] - 1.2) < 1e-9


def _collect_sql_tests() -> list[Path]:
    """Return all .sql test files in tests/team_performance_context/sql/."""
    if not _SQL_TEST_DIR.exists():
        return []
    return sorted(_SQL_TEST_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _collect_sql_tests(), ids=lambda p: p.stem)
def test_sql_constraint(snapshot_conn, sql_path):
    """Execute a SQL test file and assert it returns 0 failing rows."""
    failing_rows = run_sql_test(snapshot_conn, sql_path)
    assert failing_rows == [], (
        f"{sql_path.name} returned {len(failing_rows)} failing row(s):\n"
        + "\n".join(str(r) for r in failing_rows[:5])
    )