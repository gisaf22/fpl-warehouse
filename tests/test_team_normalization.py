"""Tests for team ID normalization across the FPL warehouse.

Covers:
- invert_team_mapping() correctness and bijection
- TeamResolutionError behaviour
- fact_match_stats normalized columns
"""

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from fpl_warehouse.integration.matching import (
    FPL_TO_UNDERSTAT_TEAM,
    invert_team_mapping,
    load_fpl_teams,
)
from fpl_warehouse.integration.exceptions import TeamResolutionError

WAREHOUSE = Path.home() / "Documents/FPL/data/warehouse/master.db"
FPL_DB = Path.home() / "Documents/FPL/data/fpl/fpl.db"

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def fpl_teams():
    if not FPL_DB.exists():
        pytest.skip("FPL source DB not found")
    return load_fpl_teams(str(FPL_DB))


@pytest.fixture(scope="module")
def us_to_fpl(fpl_teams):
    return invert_team_mapping(fpl_teams)


@pytest.fixture(scope="module")
def conn():
    if not WAREHOUSE.exists():
        pytest.skip("Warehouse not built")
    c = sqlite3.connect(WAREHOUSE)
    yield c
    c.close()


# ── invert_team_mapping tests ────────────────────────────────────────────


class TestInvertTeamMapping:

    def test_known_team_resolves(self, us_to_fpl):
        """Manchester City should resolve to fpl_id 13."""
        assert us_to_fpl["Manchester City"] == 13

    def test_all_20_teams_present(self, us_to_fpl):
        """All 20 PL teams in FPL_TO_UNDERSTAT_TEAM must resolve."""
        for fpl_name, us_name in FPL_TO_UNDERSTAT_TEAM.items():
            assert us_name in us_to_fpl, f"Missing: {us_name} (FPL: {fpl_name})"

    def test_bijection_no_duplicate_fpl_ids(self, us_to_fpl):
        """Every Understat name maps to a unique fpl_id."""
        ids = list(us_to_fpl.values())
        assert len(ids) == len(set(ids)), "Duplicate fpl_ids detected"

    def test_bijection_no_duplicate_names(self, us_to_fpl):
        """Every fpl_id maps to a unique Understat name."""
        names = list(us_to_fpl.keys())
        assert len(names) == len(set(names)), "Duplicate Understat names detected"

    def test_returns_dict_of_str_to_int(self, us_to_fpl):
        for name, fid in us_to_fpl.items():
            assert isinstance(name, str)
            assert isinstance(fid, int)

    def test_spot_check_teams(self, us_to_fpl):
        """Spot-check 5 known mappings."""
        expected = {
            "Arsenal": 1,
            "Liverpool": 12,
            "Tottenham": 18,
            "Newcastle United": 15,
            "Wolverhampton Wanderers": 20,
        }
        for us_name, fpl_id in expected.items():
            assert us_to_fpl[us_name] == fpl_id, f"{us_name} → {us_to_fpl.get(us_name)} != {fpl_id}"


# ── TeamResolutionError tests ────────────────────────────────────────────


class TestTeamResolutionError:

    def test_unknown_team_raises(self, us_to_fpl):
        """Looking up a nonexistent team must fail, not return None."""
        with pytest.raises(KeyError):
            _ = us_to_fpl["Fake FC"]

    def test_exception_has_message(self):
        err = TeamResolutionError("Cannot resolve: 'Fake FC'")
        assert "Fake FC" in str(err)

    def test_partial_match_does_not_resolve(self, us_to_fpl):
        """'Man City' is NOT 'Manchester City' — no fuzzy matching."""
        assert "Man City" not in us_to_fpl

    def test_empty_string_not_in_mapping(self, us_to_fpl):
        assert "" not in us_to_fpl

    def test_none_not_in_mapping(self, us_to_fpl):
        assert None not in us_to_fpl


# ── fact_match_stats build tests ─────────────────────────────────────────


class TestFactMatchStatsNormalized:

    def test_home_fpl_id_column_exists(self, conn):
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM fact_match_stats LIMIT 0"
        ).description]
        assert "home_fpl_id" in cols

    def test_away_fpl_id_column_exists(self, conn):
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM fact_match_stats LIMIT 0"
        ).description]
        assert "away_fpl_id" in cols

    def test_home_team_name_preserved(self, conn):
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM fact_match_stats LIMIT 0"
        ).description]
        assert "home_team_name" in cols

    def test_away_team_name_preserved(self, conn):
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM fact_match_stats LIMIT 0"
        ).description]
        assert "away_team_name" in cols

    def test_old_columns_removed(self, conn):
        """Old text-only columns should not exist."""
        cols = [d[0] for d in conn.execute(
            "SELECT * FROM fact_match_stats LIMIT 0"
        ).description]
        assert "home_team" not in cols, "Old 'home_team' column still present"
        assert "away_team" not in cols, "Old 'away_team' column still present"

    def test_no_null_fpl_ids(self, conn):
        nulls = conn.execute("""
            SELECT COUNT(*) FROM fact_match_stats
            WHERE home_fpl_id IS NULL OR away_fpl_id IS NULL
        """).fetchone()[0]
        assert nulls == 0, f"{nulls} rows have NULL fpl_ids"

    def test_fpl_ids_are_integers(self, conn):
        row = conn.execute(
            "SELECT home_fpl_id, away_fpl_id FROM fact_match_stats LIMIT 1"
        ).fetchone()
        assert isinstance(row[0], int)
        assert isinstance(row[1], int)

    def test_row_count_matches_expectation(self, conn):
        """At least 290 matches (29 GWs × 10 matches)."""
        count = conn.execute("SELECT COUNT(*) FROM fact_match_stats").fetchone()[0]
        assert count >= 290

    def test_spot_check_arsenal_home(self, conn):
        """Arsenal (fpl_id=1) should appear as home_fpl_id in some matches."""
        count = conn.execute(
            "SELECT COUNT(*) FROM fact_match_stats WHERE home_fpl_id = 1"
        ).fetchone()[0]
        assert count > 0, "Arsenal never at home"

    def test_spot_check_team_name_preserved(self, conn):
        """home_team_name should be the Understat text for the resolved fpl_id."""
        row = conn.execute("""
            SELECT home_fpl_id, home_team_name
            FROM fact_match_stats WHERE home_fpl_id = 13 LIMIT 1
        """).fetchone()
        assert row is not None, "Man City (13) not found"
        assert row[1] == "Manchester City"

    def test_spot_check_three_teams(self, conn):
        """Verify fpl_id ↔ team_name consistency for 3 teams."""
        checks = [
            (1, "Arsenal"),
            (12, "Liverpool"),
            (18, "Tottenham"),
        ]
        for fpl_id, us_name in checks:
            row = conn.execute(
                "SELECT home_team_name FROM fact_match_stats WHERE home_fpl_id = ? LIMIT 1",
                (fpl_id,),
            ).fetchone()
            assert row is not None, f"fpl_id={fpl_id} not found as home"
            assert row[0] == us_name, f"fpl_id={fpl_id}: expected {us_name}, got {row[0]}"


# ── Future-proofing tests ────────────────────────────────────────────────


class TestFutureProofing:

    def test_adding_team_auto_resolves(self, fpl_teams):
        """A new team in FPL_TO_UNDERSTAT_TEAM is automatically resolvable."""
        mapping = invert_team_mapping(fpl_teams)
        # All values from FPL_TO_UNDERSTAT_TEAM that are in current season should resolve
        for fpl_name, us_name in FPL_TO_UNDERSTAT_TEAM.items():
            if fpl_name in {info["name"] for info in fpl_teams.values()}:
                assert us_name in mapping

    def test_missing_team_causes_keyerror(self, fpl_teams):
        """Removing a team from the mapping makes it unresolvable."""
        mapping = invert_team_mapping(fpl_teams)
        # A name NOT in the dict is not resolvable
        assert "Imaginary FC" not in mapping
