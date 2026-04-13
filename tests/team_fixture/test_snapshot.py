"""Tests for fact_team_fixture_snapshot materialization.

The fixture snapshot is contractually restricted to exogenous schedule and rest
context only. Tests here verify PIT correctness, BGW/DGW handling, home/away
flags, and congestion arithmetic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from fpl_warehouse.builders.snapshots import materialize_team_fixture_snapshot
from fpl_warehouse.warehouse.ddl import (
    DIM_PLAYERS_DDL,
    DIM_TEAMS_DDL,
    FACT_FIXTURES_DDL,
    FACT_MATCH_STATS_DDL,
    FACT_TEAM_FIXTURE_SNAPSHOT_DDL,
)
from fpl_warehouse.sql_runner import run_sql_test

pytestmark = pytest.mark.unit

_SQL_TEST_DIR = Path(__file__).parent / "sql"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def warehouse_db(tmp_path):
    """Warehouse DB with 4 standard teams + 1 BGW team (T5, no GW3 fixture).

    Fixture/kickoff layout is documented in module docstring above.
    """
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(DIM_TEAMS_DDL)
    conn.execute(DIM_PLAYERS_DDL)
    conn.execute(FACT_FIXTURES_DDL)
    conn.execute(FACT_MATCH_STATS_DDL)
    conn.execute(FACT_TEAM_FIXTURE_SNAPSHOT_DDL)

    teams = [
        (1, 1, "Team 1", "Team 1", "T1"),
        (2, 2, "Team 2", "Team 2", "T2"),
        (3, 3, "Team 3", "Team 3", "T3"),
        (4, 4, "Team 4", "Team 4", "T4"),
        (5, 5, "Team 5", "Team 5", "T5"),
    ]
    conn.executemany(
        "INSERT INTO dim_teams (team_id, fpl_id, fpl_name, understat_name, short_name) "
        "VALUES (?, ?, ?, ?, ?)",
        teams,
    )

    # fact_fixtures: event, home_team_id, away_team_id, home_score, away_score,
    #                kickoff_time, finished, home_difficulty, away_difficulty
    fixtures = [
        # GW1 finished
        (1, 1, 1, 2, 2, 1, "2026-08-10T15:00:00Z", 1, 3, 2),
        (2, 1, 3, 4, 2, 0, "2026-08-10T17:30:00Z", 1, 2, 3),
        # T5 only plays GW1
        (3, 1, 5, 1, 0, 1, "2026-08-10T12:00:00Z", 1, 3, 2),
        # GW2 finished — T1 plays on 2026-08-14 (short gap from GW1)
        (4, 2, 1, 3, 1, 0, "2026-08-14T15:00:00Z", 1, 2, 3),
        (5, 2, 2, 4, 0, 2, "2026-08-17T15:00:00Z", 1, 3, 2),
        # GW3 unfinished (target)
        (6, 3, 1, 4, None, None, "2026-08-21T15:00:00Z", 0, 2, 3),
        (7, 3, 2, 3, None, None, "2026-08-21T17:30:00Z", 0, 3, 2),
        # T5 has NO GW3 fixture → BGW
    ]
    conn.executemany(
        "INSERT INTO fact_fixtures "
        "(fixture_id, event, home_team_id, away_team_id, home_score, away_score, "
        " kickoff_time, finished, home_difficulty, away_difficulty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fixtures,
    )

    # fact_match_stats: understat_match_id, fpl_fixture_id, event,
    #   home_fpl_id, away_fpl_id, home_team_name, away_team_name,
    #   home_goals, away_goals, home_xg, away_xg,
    #   home_ppda, away_ppda, home_deep, away_deep,
    #   home_shots, away_shots, home_sot, away_sot,
    #   prob_home, prob_draw, prob_away, datetime
    match_stats = [
        # GW1: T1(home) vs T2(away)
        (101, 1, 1, 1, 2, "T1", "T2",
         2, 1, 1.5, 0.8, 9.2, 11.5, 8, 4, 10, 7, 5, 3,
         0.5, 0.3, 0.2, "2026-08-10T15:00:00"),
        # GW1: T3(home) vs T4(away)
        (102, 2, 1, 3, 4, "T3", "T4",
         2, 0, 2.0, 1.0, 8.0, 10.0, 10, 5, 12, 8, 6, 4,
         0.6, 0.25, 0.15, "2026-08-10T17:30:00"),
        # GW2: T1(home) vs T3(away)
        (103, 4, 2, 1, 3, "T1", "T3",
         1, 0, 1.0, 0.6, 10.0, 12.0, 6, 3, 9, 6, 4, 2,
         0.55, 0.25, 0.2, "2026-08-14T15:00:00"),
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
    materialize_team_fixture_snapshot(warehouse_db)
    conn = sqlite3.connect(warehouse_db)
    yield conn
    conn.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(conn: sqlite3.Connection, as_of_gw: int, team_fpl_id: int) -> dict:
    """Fetch a single snapshot row as a dict. Fails if the row is absent."""
    cols = [d[0] for d in conn.execute(
        "SELECT * FROM fact_team_fixture_snapshot LIMIT 0"
    ).description]
    row = conn.execute(
        "SELECT * FROM fact_team_fixture_snapshot "
        "WHERE as_of_gw = ? AND team_fpl_id = ?",
        (as_of_gw, team_fpl_id),
    ).fetchone()
    assert row is not None, f"No row for as_of_gw={as_of_gw}, team_fpl_id={team_fpl_id}"
    return dict(zip(cols, row))


# ── Behavioural tests ─────────────────────────────────────────────────────────

def test_snapshot_grain_is_unique(snapshot_conn):
    """Primary key (as_of_gw, team_fpl_id) must have no duplicates."""
    dupes = snapshot_conn.execute(
        "SELECT COUNT(*) FROM ("
        "  SELECT as_of_gw, team_fpl_id, COUNT(*) AS n "
        "  FROM fact_team_fixture_snapshot "
        "  GROUP BY as_of_gw, team_fpl_id HAVING n > 1"
        ")"
    ).fetchone()[0]
    assert dupes == 0


def test_snapshot_columns_match_contract(snapshot_conn):
    """Fixture snapshot must not include team or opponent form columns."""
    cols = [row[1] for row in snapshot_conn.execute(
        "PRAGMA table_info(fact_team_fixture_snapshot)"
    ).fetchall()]
    assert cols == [
        "as_of_gw",
        "team_fpl_id",
        "fixture_count",
        "upcoming_dgw_flag",
        "upcoming_bgw_flag",
        "has_home_fixture_flag",
        "has_away_fixture_flag",
        "fixture_difficulty",
        "opponent_team_fpl_id",
        "days_since_last_fixture",
        "matches_count_last_7d",
        "matches_count_last_14d",
        "days_until_next_fixture",
        "days_between_last_and_next_fixture",
        "midweek_turnaround_flag",
    ]


def test_reasonable_row_coverage(snapshot_conn):
    """5 teams × 2 finished GWs = 10 rows total."""
    total = snapshot_conn.execute(
        "SELECT COUNT(*) FROM fact_team_fixture_snapshot"
    ).fetchone()[0]
    assert total == 10


def test_standard_fixture_count(snapshot_conn):
    """T1 at as_of_gw=2 has one GW3 fixture: fixture_count=1."""
    row = _row(snapshot_conn, 2, 1)
    assert row["fixture_count"] == 1
    assert row["upcoming_dgw_flag"] == 0
    assert row["upcoming_bgw_flag"] == 0


def test_standard_home_away_flags(snapshot_conn):
    """T1 at as_of_gw=2 is home in GW3 (vs T4): has_home=1, has_away=0."""
    row = _row(snapshot_conn, 2, 1)
    assert row["has_home_fixture_flag"] == 1
    assert row["has_away_fixture_flag"] == 0


def test_standard_away_team_flags(snapshot_conn):
    """T4 at as_of_gw=2 is away in GW3 (at T1): has_home=0, has_away=1."""
    row = _row(snapshot_conn, 2, 4)
    assert row["has_home_fixture_flag"] == 0
    assert row["has_away_fixture_flag"] == 1


def test_fixture_difficulty_single_fixture(snapshot_conn):
    """T1 at as_of_gw=2: GW3 fixture is T1 home vs T4, home_difficulty=2."""
    row = _row(snapshot_conn, 2, 1)
    assert row["fixture_difficulty"] == 2


def test_opp_team_fpl_id_single_fixture(snapshot_conn):
    """T1 at as_of_gw=2: opponent in GW3 is T4 (fpl_id=4)."""
    row = _row(snapshot_conn, 2, 1)
    assert row["opponent_team_fpl_id"] == 4


def test_bgw_fixture_count_zero(snapshot_conn):
    """T5 at as_of_gw=2 has no GW3 fixture: fixture_count=0, bgw_flag=1."""
    row = _row(snapshot_conn, 2, 5)
    assert row["fixture_count"] == 0
    assert row["upcoming_bgw_flag"] == 1
    assert row["upcoming_dgw_flag"] == 0


def test_bgw_has_no_home_or_away_fixture(snapshot_conn):
    """T5 at as_of_gw=2: no fixture so both home/away flags are 0."""
    row = _row(snapshot_conn, 2, 5)
    assert row["has_home_fixture_flag"] == 0
    assert row["has_away_fixture_flag"] == 0


def test_bgw_fixture_difficulty_null(snapshot_conn):
    """T5 at as_of_gw=2: no fixture → fixture_difficulty and opponent_team_fpl_id NULL."""
    row = _row(snapshot_conn, 2, 5)
    assert row["fixture_difficulty"] is None
    assert row["opponent_team_fpl_id"] is None


def test_congestion_days_since_t1_at_gw2(snapshot_conn):
    """T1 at as_of_gw=2: last kickoff 2026-08-14, global_cutoff 2026-08-17.
    days_since = floor(julianday(17) - julianday(14)) = 3.
    """
    row = _row(snapshot_conn, 2, 1)
    assert row["days_since_last_fixture"] == 3


def test_congestion_days_until_t1_at_gw2(snapshot_conn):
    """T1 at as_of_gw=2: next kickoff 2026-08-21, global_cutoff 2026-08-17.
    days_until = floor(julianday(21) - julianday(17)) = 4.
    """
    row = _row(snapshot_conn, 2, 1)
    assert row["days_until_next_fixture"] == 4


def test_congestion_days_between_t1_at_gw2(snapshot_conn):
    """T1 at as_of_gw=2: days_between = 3 + 4 = 7."""
    row = _row(snapshot_conn, 2, 1)
    assert row["days_between_last_and_next_fixture"] == 7


def test_midweek_turnaround_flag_false(snapshot_conn):
    """T1 at as_of_gw=2: days_between = 7, which is > 4 → flag = 0."""
    row = _row(snapshot_conn, 2, 1)
    assert row["midweek_turnaround_flag"] == 0


def test_matches_last_7d_t1_at_gw2(snapshot_conn):
    """T1 at as_of_gw=2: global_cutoff=2026-08-17. T1 played 2026-08-10 and
    2026-08-14. Both within 7 days of cutoff (cutoff - 7 = 2026-08-10).
    team_matches_last_7d = 2.
    """
    row = _row(snapshot_conn, 2, 1)
    assert row["matches_count_last_7d"] == 2


def test_matches_last_14d_t1_at_gw2(snapshot_conn):
    """T1 at as_of_gw=2: T1 played 3 fixtures within 14 days of cutoff (2026-08-17).
    T5 vs T1 on 2026-08-10T12:00 + T1 vs T2 on 2026-08-10T15:00 + T1 vs T3 on 2026-08-14.
    The 7d boundary (cutoff - 7 = 2026-08-10T15:00) excludes T5 vs T1 (12:00 < 15:00),
    but the 14d boundary (cutoff - 14 = 2026-08-03) includes all three.
    team_matches_last_14d = 3.
    """
    row = _row(snapshot_conn, 2, 1)
    assert row["matches_count_last_14d"] == 3


def test_congestion_null_at_gw1_for_t5_no_last(snapshot_conn):
    """T5 at as_of_gw=1: no prior fact_match_stats (not fixture based for cutoff).
    T5 did play GW1 (fixture exists), so days_since should be calculable.
    T5 next fixture: none after GW1 → days_until = NULL.
    """
    row = _row(snapshot_conn, 1, 5)
    # T5 has no future fixture in our data → days_until should be NULL
    assert row["days_until_next_fixture"] is None
    assert row["days_between_last_and_next_fixture"] is None
    assert row["midweek_turnaround_flag"] is None


# ── DGW fixtures and tests ────────────────────────────────────────────────────
#
# Layout:
#   Teams: T1 (fpl_id=1), T2 (fpl_id=2)
#   GW1 (finished): T1 home vs T2 away (kickoff 2026-08-10T15:00:00Z)
#   GW2 (target, unfinished): two fixtures both involving T1 → DGW for T1
#     fixture A: T1 home vs T2 away (kickoff 2026-08-17T15:00:00Z)
#     fixture B: T2 home vs T1 away (kickoff 2026-08-17T18:00:00Z)
#   T2 also has DGW (appears in both GW2 fixtures).
#
# Expected at as_of_gw=1, target=GW2:
#   T1: fixture_count=2, dgw_flag=1, bgw_flag=0
#       has_home_fixture=1 (fixture A), has_away_fixture=1 (fixture B)
#       fixture_difficulty=NULL (two fixtures), opp_team_fpl_id=NULL
#       all opp output columns=NULL

@pytest.fixture()
def warehouse_db_dgw(tmp_path):
    """Warehouse DB for DGW testing. T1 and T2 each have two GW2 fixtures."""
    db_path = tmp_path / "warehouse_dgw.db"
    conn = sqlite3.connect(db_path)
    conn.execute(DIM_TEAMS_DDL)
    conn.execute(DIM_PLAYERS_DDL)
    conn.execute(FACT_FIXTURES_DDL)
    conn.execute(FACT_MATCH_STATS_DDL)
    conn.execute(FACT_TEAM_FIXTURE_SNAPSHOT_DDL)

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
        # GW1 finished
        (1, 1, 1, 2, 2, 1, "2026-08-10T15:00:00Z", 1, 3, 2),
        # GW2 unfinished — DGW for both T1 and T2
        (2, 2, 1, 2, None, None, "2026-08-17T15:00:00Z", 0, 3, 2),
        (3, 2, 2, 1, None, None, "2026-08-17T18:00:00Z", 0, 2, 3),
    ]
    conn.executemany(
        "INSERT INTO fact_fixtures "
        "(fixture_id, event, home_team_id, away_team_id, home_score, away_score, "
        " kickoff_time, finished, home_difficulty, away_difficulty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fixtures,
    )

    match_stats = [
        # GW1: T1(home) vs T2(away)
        (201, 1, 1, 1, 2, "T1", "T2",
         2, 1, 1.5, 0.8, 9.2, 11.5, 8, 4, 10, 7, 5, 3,
         0.5, 0.3, 0.2, "2026-08-10T15:00:00"),
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
def snapshot_conn_dgw(warehouse_db_dgw):
    """Materialise the snapshot from the DGW database."""
    materialize_team_fixture_snapshot(warehouse_db_dgw)
    conn = sqlite3.connect(warehouse_db_dgw)
    yield conn
    conn.close()


def test_dgw_fixture_count(snapshot_conn_dgw):
    """T1 at as_of_gw=1 has two GW2 fixtures: fixture_count=2, dgw_flag=1."""
    cols = [d[0] for d in snapshot_conn_dgw.execute(
        "SELECT * FROM fact_team_fixture_snapshot LIMIT 0"
    ).description]
    row = dict(zip(cols, snapshot_conn_dgw.execute(
        "SELECT * FROM fact_team_fixture_snapshot WHERE as_of_gw=1 AND team_fpl_id=1"
    ).fetchone()))
    assert row["fixture_count"] == 2
    assert row["upcoming_dgw_flag"] == 1
    assert row["upcoming_bgw_flag"] == 0


def test_dgw_has_home_and_away(snapshot_conn_dgw):
    """T1 is home in fixture A and away in fixture B → both flags set to 1."""
    cols = [d[0] for d in snapshot_conn_dgw.execute(
        "SELECT * FROM fact_team_fixture_snapshot LIMIT 0"
    ).description]
    row = dict(zip(cols, snapshot_conn_dgw.execute(
        "SELECT * FROM fact_team_fixture_snapshot WHERE as_of_gw=1 AND team_fpl_id=1"
    ).fetchone()))
    assert row["has_home_fixture_flag"] == 1
    assert row["has_away_fixture_flag"] == 1


def test_dgw_fixture_difficulty_null(snapshot_conn_dgw):
    """DGW: two fixtures with different difficulties — fixture_difficulty=NULL."""
    cols = [d[0] for d in snapshot_conn_dgw.execute(
        "SELECT * FROM fact_team_fixture_snapshot LIMIT 0"
    ).description]
    row = dict(zip(cols, snapshot_conn_dgw.execute(
        "SELECT * FROM fact_team_fixture_snapshot WHERE as_of_gw=1 AND team_fpl_id=1"
    ).fetchone()))
    assert row["fixture_difficulty"] is None
    assert row["opponent_team_fpl_id"] is None


# ── Window cap and midweek turnaround = 1 fixtures and tests ──────────────────
#
# Layout:
#   Teams: T1 (fpl_id=1), T2 (fpl_id=2)
#   T1 has 4 finished matches across GW1–GW4. Only the last 3 should count.
#   GW1 (finished): T1 home vs T2 away  kickoff 2026-08-10T15:00:00Z  xg=5.0 (intentionally large)
#   GW2 (finished): T1 home vs T2 away  kickoff 2026-08-17T15:00:00Z  xg=1.0
#   GW3 (finished): T1 home vs T2 away  kickoff 2026-08-24T15:00:00Z  xg=1.0
#   GW4 (finished): T1 home vs T2 away  kickoff 2026-08-27T15:00:00Z  xg=1.0  [3 days after GW3]
#   GW5 (target, unfinished): T1 home vs T2 away  kickoff 2026-08-30T15:00:00Z  [3 days after GW4]
#
# At as_of_gw=4, target=GW5:
#   rn_match window: GW4(rn=1), GW3(rn=2), GW2(rn=3), GW1(rn=4 → excluded)
#   team_xg_last_3 = 1.0 + 1.0 + 1.0 = 3.0  (NOT 5.0+1.0+1.0+1.0=8.0)
#
# Congestion at as_of_gw=4:
#   global_cutoff = max finished kickoff = 2026-08-27T15:00:00Z (GW4)
#   T1 last = 2026-08-27T15:00:00Z → days_since = 0
#   T1 next = 2026-08-30T15:00:00Z → days_until = 3
#   days_between = 0 + 3 = 3 → midweek_turnaround_flag = 1  (3 <= 4)

@pytest.fixture()
def warehouse_db_window(tmp_path):
    """Warehouse DB for rn_match window cap and midweek_turnaround=1 testing."""
    db_path = tmp_path / "warehouse_window.db"
    conn = sqlite3.connect(db_path)
    conn.execute(DIM_TEAMS_DDL)
    conn.execute(DIM_PLAYERS_DDL)
    conn.execute(FACT_FIXTURES_DDL)
    conn.execute(FACT_MATCH_STATS_DDL)
    conn.execute(FACT_TEAM_FIXTURE_SNAPSHOT_DDL)

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
        (1, 1, 1, 2, 2, 0, "2026-08-10T15:00:00Z", 1, 3, 2),
        (2, 2, 1, 2, 1, 0, "2026-08-17T15:00:00Z", 1, 3, 2),
        (3, 3, 1, 2, 1, 0, "2026-08-24T15:00:00Z", 1, 3, 2),
        (4, 4, 1, 2, 1, 0, "2026-08-27T15:00:00Z", 1, 3, 2),
        (5, 5, 1, 2, None, None, "2026-08-30T15:00:00Z", 0, 3, 2),
    ]
    conn.executemany(
        "INSERT INTO fact_fixtures "
        "(fixture_id, event, home_team_id, away_team_id, home_score, away_score, "
        " kickoff_time, finished, home_difficulty, away_difficulty) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        fixtures,
    )

    # GW1: large xg=5.0 to make it obvious if the window cap fails.
    # GW2–GW4: xg=1.0 each. Only GW2+GW3+GW4 should sum (last 3).
    match_stats = [
        (301, 1, 1, 1, 2, "T1", "T2",
         2, 0, 5.0, 0.2, 8.0, 12.0, 10, 2, 14, 5, 7, 2,
         0.6, 0.25, 0.15, "2026-08-10T15:00:00"),
        (302, 2, 2, 1, 2, "T1", "T2",
         1, 0, 1.0, 0.3, 9.0, 11.0, 6, 3, 10, 5, 4, 2,
         0.55, 0.25, 0.2, "2026-08-17T15:00:00"),
        (303, 3, 3, 1, 2, "T1", "T2",
         1, 0, 1.0, 0.4, 10.0, 10.0, 5, 4, 9, 6, 4, 3,
         0.5, 0.3, 0.2, "2026-08-24T15:00:00"),
        (304, 4, 4, 1, 2, "T1", "T2",
         1, 0, 1.0, 0.5, 11.0, 9.0, 4, 5, 8, 7, 4, 4,
         0.45, 0.3, 0.25, "2026-08-27T15:00:00"),
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
def snapshot_conn_window(warehouse_db_window):
    """Materialise the snapshot from the window-cap database."""
    materialize_team_fixture_snapshot(warehouse_db_window)
    conn = sqlite3.connect(warehouse_db_window)
    yield conn
    conn.close()


def test_midweek_turnaround_flag_true(snapshot_conn_window):
    """T1 at as_of_gw=4: days_between = 0 + 3 = 3 → midweek_turnaround_flag = 1.

    global_cutoff = GW4 kickoff = 2026-08-27. T1's last match is also GW4
    (days_since=0). T1's next is GW5 on 2026-08-30 (days_until=3).
    3 <= 4 → flag = 1.
    """
    cols = [d[0] for d in snapshot_conn_window.execute(
        "SELECT * FROM fact_team_fixture_snapshot LIMIT 0"
    ).description]
    row = dict(zip(cols, snapshot_conn_window.execute(
        "SELECT * FROM fact_team_fixture_snapshot WHERE as_of_gw=4 AND team_fpl_id=1"
    ).fetchone()))
    assert row["midweek_turnaround_flag"] == 1


# ── SQL constraint tests (parametric) ─────────────────────────────────────────

def _collect_sql_tests() -> list[Path]:
    """Return all .sql test files in tests/team_fixture/sql/, sorted by name."""
    if not _SQL_TEST_DIR.exists():
        return []
    return sorted(_SQL_TEST_DIR.glob("*.sql"))


@pytest.mark.parametrize("sql_path", _collect_sql_tests(), ids=lambda p: p.stem)
def test_sql_constraint(snapshot_conn, sql_path):
    """Execute a SQL test file and assert it returns 0 failing rows.

    Each .sql file in tests/team_fixture/sql/ is a SELECT that returns rows
    only when a constraint is violated.

    The snapshot_conn fixture provides access to:
      - int_team_fixture_base        (view)
      - fct_team_fixture_features    (view)
      - fact_team_fixture_snapshot   (table)
      - All source tables
    """
    failing_rows = run_sql_test(snapshot_conn, sql_path)
    assert failing_rows == [], (
        f"{sql_path.name} returned {len(failing_rows)} failing row(s):\n"
        + "\n".join(str(r) for r in failing_rows[:5])
    )
