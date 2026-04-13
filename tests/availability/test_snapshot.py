"""Tests for fact_player_availability_snapshot materialization.

Structure
---------
Fixture setup
    warehouse_db  — creates schema and inserts controlled test data into a
                    temp SQLite file. Data is designed to exercise DGW, BGW,
                    standard, and edge-case scenarios explicitly.
    snapshot_conn — calls materialize_player_availability_snapshot, then
                    returns an open connection for assertions.

Test groups
    Behavioural tests (test_*)
        Assert specific known values from the controlled fixture data.
        These are the primary regression tests — they verify PIT correctness,
        DGW/BGW semantics, null policy, and grain.

    SQL constraint tests (test_sql_constraint)
        Parametric: one test case per .sql file in tests/sql/availability/.
        Each file returns 0 rows on pass. These run against the same
        snapshot_conn fixture, so they exercise both layers and the
        materialised fact table.

        int_test_*  — tests on int_player_gw_base view
        fct_test_*  — tests on fct_player_availability_features view
        fact_test_* — tests on fact_player_availability_snapshot table
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpl_warehouse.builders.snapshots import materialize_player_availability_snapshot
from fpl_warehouse.warehouse.ddl import (
    DIM_PLAYERS_DDL,
    DIM_TEAMS_DDL,
    FACT_FIXTURES_DDL,
    FACT_PLAYER_AVAILABILITY_SNAPSHOT_DDL,
    FACT_PLAYER_GW_DDL,
)
from fpl_warehouse.sql_runner import run_sql_test

pytestmark = pytest.mark.unit

_SQL_TEST_DIR = Path(__file__).parent / "sql"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def warehouse_db(tmp_path):
    """Minimal warehouse database with controlled data for deterministic tests.

    Player coverage
    ---------------
    Player 101 (T1): played GW1 (90 min, started), GW2 (45 min, not started)
    Player 102 (T2): played GW1 (0 min), GW2 (90 min, started)
    Player 103 (T3): played GW1 (30 min), GW2 (60 min, started)
    Player 107 (T7): played GW1 (0 min), GW2 (0 min)

    Fixture data is included to drive the all_gws spine (fact_fixtures.finished=1).
    GW1 and GW2 are finished; GW3+ are unfinished.
    """
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(DIM_TEAMS_DDL)
    conn.execute(DIM_PLAYERS_DDL)
    conn.execute(FACT_PLAYER_GW_DDL)
    conn.execute(FACT_FIXTURES_DDL)
    conn.execute(FACT_PLAYER_AVAILABILITY_SNAPSHOT_DDL)

    teams = [
        (1, 1, "Team 1", "Team 1", "T1"),
        (2, 2, "Team 2", "Team 2", "T2"),
        (3, 3, "Team 3", "Team 3", "T3"),
        (4, 4, "Team 4", "Team 4", "T4"),
        (5, 5, "Team 5", "Team 5", "T5"),
        (6, 6, "Team 6", "Team 6", "T6"),
        (7, 7, "Team 7", "Team 7", "T7"),
        (8, 8, "Team 8", "Team 8", "T8"),
    ]
    conn.executemany(
        "INSERT INTO dim_teams (team_id, fpl_id, fpl_name, understat_name, short_name) "
        "VALUES (?, ?, ?, ?, ?)",
        teams,
    )

    players = [
        (101, "Player 101", 1),
        (102, "Player 102", 2),
        (103, "Player 103", 3),
        (107, "Player 107", 7),
    ]
    conn.executemany(
        "INSERT INTO dim_players (fpl_id, web_name, team_id, element_type) "
        "VALUES (?, ?, ?, 3)",
        players,
    )

    player_gw_rows = [
        (101, 1, 90, 1, 5),
        (101, 2, 45, 0, 2),
        (102, 1, 0, 0, 0),
        (102, 2, 90, 1, 6),
        (103, 1, 30, 0, 1),
        (103, 2, 60, 1, 4),
        (107, 1, 0, 0, 0),
        (107, 2, 0, 0, 0),
    ]
    conn.executemany(
        "INSERT INTO fact_player_gw (fpl_id, round, minutes, starts, total_points) "
        "VALUES (?, ?, ?, ?, ?)",
        player_gw_rows,
    )

    # Fixture layout — see docstring above for team/GW mapping.
    # Columns: fixture_id, event, home_team_id, away_team_id, home_score,
    #          away_score, kickoff_time, finished, home_difficulty, away_difficulty
    fixtures = [
        (1, 1, 1, 2, 2, 1, "2026-08-10T15:00:00Z", 1, 3, 2),
        (2, 1, 7, 8, 0, 0, "2026-08-11T15:00:00Z", 1, 3, 3),
        (3, 2, 2, 4, 1, 0, "2026-08-16T15:00:00Z", 1, 2, 3),
        (4, 2, 1, 3, 1, 1, "2026-08-17T15:00:00Z", 1, 2, 2),
        (5, 2, 7, 8, 0, 0, "2026-08-18T15:00:00Z", 1, 3, 3),
        (6, 3, 1, 4, None, None, "2026-08-20T19:00:00Z", 0, 2, 3),
        (7, 3, 5, 1, None, None, "2026-08-23T14:00:00Z", 0, 3, 2),
        (8, 3, 3, 6, None, None, "2026-08-24T19:00:00Z", 0, 2, 3),
        (9, 4, 2, 6, None, None, "2026-08-30T14:00:00Z", 0, 2, 3),
        (10, 1, 3, 4, 1, 0, "2026-08-10T12:30:00Z", 1, 2, 3),
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

    Views (int_player_gw_base, fct_player_availability_features) and the
    snapshot table are created by materialize_player_availability_snapshot.
    The returned connection has access to all three layers so SQL tests can
    run against any of them.
    """
    materialize_player_availability_snapshot(warehouse_db)
    conn = sqlite3.connect(warehouse_db)
    yield conn
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(conn: sqlite3.Connection, as_of_gw: int, fpl_id: int) -> dict:
    """Fetch a single snapshot row as a dict. Fails if the row is absent."""
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM fact_player_availability_snapshot LIMIT 0"
    ).description]
    row = conn.execute(
        "SELECT * FROM fact_player_availability_snapshot "
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
        "  FROM fact_player_availability_snapshot "
        "  GROUP BY as_of_gw, fpl_id HAVING n > 1"
        ")"
    ).fetchone()[0]
    assert dupes == 0


def test_pit_window_uses_only_history_up_to_as_of_gw(snapshot_conn):
    """GW1 rows must reflect only round=1 data, not round=2.

    Player 101 played 90 min in GW1. At as_of_gw=1, minutes_last_gw must
    be 90 and minutes_total_last_3gws must be 90 (only one GW in the window).
    Player 102 played 0 min in GW1 — all counts must be 0.
    """
    p101_gw1 = _row(snapshot_conn, 1, 101)
    assert p101_gw1["minutes_last_gw"] == 90
    assert p101_gw1["minutes_total_last_3gws"] == 90
    assert p101_gw1["starts_count_last_3gws"] == 1

    p102_gw1 = _row(snapshot_conn, 1, 102)
    assert p102_gw1["minutes_total_last_3gws"] == 0
    assert p102_gw1["starts_count_last_3gws"] == 0


def test_player_with_zero_minutes_all_windows_zero(snapshot_conn):
    """Player 107 (T7) at as_of_gw=2: played 0 minutes in both GW1 and GW2.

    All count features must be 0 (COALESCE default). minutes_last_gw must
    be 0 (player had a row in round=2 with 0 minutes).
    """
    row = _row(snapshot_conn, 2, 107)
    assert row["minutes_last_gw"] == 0
    assert row["minutes_total_last_3gws"] == 0
    assert row["minutes_total_last_5gws"] == 0
    assert row["starts_count_last_3gws"] == 0
    assert row["appearances_count_last_3gws"] == 0


def test_reasonable_row_coverage(snapshot_conn):
    """4 players × 2 finished GWs = 8 rows total."""
    total = snapshot_conn.execute(
        "SELECT COUNT(*) FROM fact_player_availability_snapshot"
    ).fetchone()[0]
    assert total == 8


# ── SQL constraint tests (parametric) ─────────────────────────────────────────

def _collect_sql_tests() -> list[Path]:
    """Return all .sql test files in tests/sql/availability/, sorted by name."""
    if not _SQL_TEST_DIR.exists():
        return []
    return sorted(_SQL_TEST_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _collect_sql_tests(), ids=lambda p: p.stem)
def test_sql_constraint(snapshot_conn, sql_path):
    """Execute a SQL test file and assert it returns 0 failing rows.

    Each .sql file in tests/availability/sql/ is a SELECT that returns rows
    only when a constraint is violated. An empty result set means the test
    passed. This mirrors dbt's singular test format exactly.

    The snapshot_conn fixture provides access to:
      - int_player_gw_base                (view)
      - fct_player_availability_features  (view)
      - fact_player_availability_snapshot (table)
      - All source tables (fact_player_gw, fact_fixtures, dim_players, dim_teams)
    """
    failing_rows = run_sql_test(snapshot_conn, sql_path)
    assert failing_rows == [], (
        f"{sql_path.name} returned {len(failing_rows)} failing row(s):\n"
        + "\n".join(str(r) for r in failing_rows[:5])
    )
