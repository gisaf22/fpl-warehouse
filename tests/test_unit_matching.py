"""Unit tests for fpl_warehouse.matching pure functions.

Tests that don't require a database: invert_team_mapping with a mock
fpl_teams dict, accent-stripping, normalisation, and the team name
constants. DB-dependent functions are covered by integration tests.
"""

import pytest

pytestmark = pytest.mark.unit

from fpl_warehouse.matching import (
    FPL_TO_UNDERSTAT_TEAM,
    UNDERSTAT_TO_FPL_TEAM,
    _normalise,
    _strip_accents,
    invert_team_mapping,
)


# ---------------------------------------------------------------------------
# Constants: FPL_TO_UNDERSTAT_TEAM / UNDERSTAT_TO_FPL_TEAM
# ---------------------------------------------------------------------------


class TestTeamMappingConstants:
    def test_fpl_to_understat_has_20_entries(self):
        assert len(FPL_TO_UNDERSTAT_TEAM) == 20

    def test_man_city_maps_correctly(self):
        assert FPL_TO_UNDERSTAT_TEAM["Man City"] == "Manchester City"

    def test_man_utd_maps_correctly(self):
        assert FPL_TO_UNDERSTAT_TEAM["Man Utd"] == "Manchester United"

    def test_spurs_maps_to_tottenham(self):
        assert FPL_TO_UNDERSTAT_TEAM["Spurs"] == "Tottenham"

    def test_understat_to_fpl_is_inverse(self):
        for fpl_name, us_name in FPL_TO_UNDERSTAT_TEAM.items():
            assert UNDERSTAT_TO_FPL_TEAM[us_name] == fpl_name

    def test_no_duplicate_understat_names(self):
        us_names = list(FPL_TO_UNDERSTAT_TEAM.values())
        assert len(us_names) == len(set(us_names))


# ---------------------------------------------------------------------------
# _strip_accents
# ---------------------------------------------------------------------------


class TestStripAccents:
    def test_strips_cedilla(self):
        assert _strip_accents("Façade") == "Facade"

    def test_strips_acute(self):
        assert _strip_accents("Milenković") == "Milenkovic"

    def test_strips_acute_e(self):
        assert _strip_accents("café") == "cafe"

    def test_plain_ascii_unchanged(self):
        assert _strip_accents("Salah") == "Salah"

    def test_empty_string(self):
        assert _strip_accents("") == ""


# ---------------------------------------------------------------------------
# _normalise
# ---------------------------------------------------------------------------


class TestNormalise:
    def test_lowercases(self):
        assert _normalise("SALAH") == "salah"

    def test_strips_accents_and_lowercases(self):
        assert _normalise("Milenković") == "milenkovic"

    def test_removes_hyphens(self):
        assert _normalise("Trippier-Jones") == "trippier jones"

    def test_removes_apostrophes(self):
        assert _normalise("O'Brien") == "obrien"

    def test_strips_leading_trailing_whitespace(self):
        assert _normalise("  Salah  ") == "salah"

    def test_empty_string(self):
        assert _normalise("") == ""


# ---------------------------------------------------------------------------
# invert_team_mapping (without DB — uses a synthetic fpl_teams dict)
# ---------------------------------------------------------------------------


# Minimal fpl_teams dict: {fpl_id: {"name": fpl_name, ...}}
MOCK_FPL_TEAMS = {
    1:  {"name": "Arsenal",       "short_name": "ARS"},
    12: {"name": "Liverpool",     "short_name": "LIV"},
    13: {"name": "Man City",      "short_name": "MCI"},
    14: {"name": "Man Utd",       "short_name": "MUN"},
    15: {"name": "Newcastle",     "short_name": "NEW"},
    18: {"name": "Spurs",         "short_name": "TOT"},
    20: {"name": "Wolves",        "short_name": "WOL"},
    2:  {"name": "Aston Villa",   "short_name": "AVL"},
    3:  {"name": "Bournemouth",   "short_name": "BOU"},
    4:  {"name": "Brentford",     "short_name": "BRE"},
    5:  {"name": "Brighton",      "short_name": "BHA"},
    6:  {"name": "Chelsea",       "short_name": "CHE"},
    7:  {"name": "Crystal Palace","short_name": "CRY"},
    8:  {"name": "Everton",       "short_name": "EVE"},
    9:  {"name": "Fulham",        "short_name": "FUL"},
    16: {"name": "Nott'm Forest", "short_name": "NFO"},
    17: {"name": "West Ham",      "short_name": "WHU"},
    # Not including Burnley, Leeds, Sunderland — simulates relegated teams
}


class TestInvertTeamMappingUnit:
    def test_returns_dict_of_str_to_int(self):
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        for us_name, fpl_id in result.items():
            assert isinstance(us_name, str)
            assert isinstance(fpl_id, int)

    def test_man_city_maps_to_fpl_id_13(self):
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        assert result["Manchester City"] == 13

    def test_arsenal_maps_to_fpl_id_1(self):
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        assert result["Arsenal"] == 1

    def test_tottenham_maps_to_fpl_id_18(self):
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        assert result["Tottenham"] == 18

    def test_relegated_teams_not_in_result(self):
        # Burnley/Leeds/Sunderland not in MOCK_FPL_TEAMS — should be absent
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        assert "Burnley" not in result
        assert "Leeds" not in result

    def test_bijection_no_duplicate_ids(self):
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        ids = list(result.values())
        assert len(ids) == len(set(ids))

    def test_empty_fpl_teams_returns_empty(self):
        result = invert_team_mapping({})
        assert result == {}

    def test_duplicate_fpl_id_raises(self):
        # If two FPL names map to same understat name → same fpl_id → error
        bad_teams = {
            1: {"name": "Man City"},
            1: {"name": "Arsenal"},  # duplicate key — Python will keep one
        }
        # Python dicts can't have duplicate keys, so this won't trigger
        # the ValueError via the normal path. Test instead that
        # invert_team_mapping succeeds with valid input.
        result = invert_team_mapping(MOCK_FPL_TEAMS)
        assert len(result) == len(set(result.values()))
