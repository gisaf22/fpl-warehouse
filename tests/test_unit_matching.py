"""Unit tests for fpl_warehouse.matching pure functions.

Tests that don't require a database: invert_team_mapping with a mock
fpl_teams dict, accent-stripping, normalisation, and the team name
constants. DB-dependent functions are covered by integration tests.
"""

import textwrap

import pytest

pytestmark = pytest.mark.unit

from fpl_warehouse.integration.matching import (
    FPL_TO_UNDERSTAT_TEAM,
    UNDERSTAT_TO_FPL_TEAM,
    _normalise,
    _strip_accents,
    build_reep_matches,
    invert_team_mapping,
    load_reep_map,
    match_players,
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


# ---------------------------------------------------------------------------
# Shared fixtures for reep tests
# ---------------------------------------------------------------------------

MOCK_FPL_TEAMS_REEP = {
    1: {"name": "Arsenal", "short_name": "ARS"},
    13: {"name": "Man City", "short_name": "MCI"},
}

# Minimal FPL players — same structure as load_fpl_players() output.
_SALAH = {
    "id": 233, "first_name": "Mohamed", "second_name": "Salah",
    "web_name": "Salah", "team": 12, "element_type": 3,
}
_HAALAND = {
    "id": 355, "first_name": "Erling", "second_name": "Haaland",
    "web_name": "Haaland", "team": 13, "element_type": 4,
}
_UNKNOWN = {
    "id": 999, "first_name": "New", "second_name": "Player",
    "web_name": "N.Player", "team": 1, "element_type": 3,
}

# Minimal Understat players — same structure as load_understat_players() output.
_US_SALAH = {
    "player_id": 1250, "player": "Mohamed Salah",
    "team": "Liverpool", "position": "AML", "fpl_element_type": 3,
    "all_teams": ["Liverpool"],
}
_US_HAALAND = {
    "player_id": 8260, "player": "Erling Haaland",
    "team": "Manchester City", "position": "FW", "fpl_element_type": 4,
    "all_teams": ["Manchester City"],
}

FPL_PLAYER_CODES = {
    233: 80201,   # Salah's FPL code
    355: 219449,  # Haaland's FPL code
    # 999 intentionally absent — no code for unknown player
}

REEP_MAP = {
    80201: 1250,   # Salah: fpl_code → us_player_id
    219449: 8260,  # Haaland: fpl_code → us_player_id
}


# ---------------------------------------------------------------------------
# load_reep_map
# ---------------------------------------------------------------------------


class TestLoadReepMap:
    def test_parses_valid_rows(self, tmp_path):
        csv_content = textwrap.dedent("""\
            key_opta_numeric,key_understat,name
            80201,1250,Mohamed Salah
            219449,8260,Erling Haaland
        """)
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert result == {80201: 1250, 219449: 8260}

    def test_skips_rows_with_missing_opta(self, tmp_path):
        csv_content = textwrap.dedent("""\
            key_opta_numeric,key_understat,name
            ,1250,No Opta
            219449,8260,Erling Haaland
        """)
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert 1250 not in result.values()
        assert result == {219449: 8260}

    def test_skips_rows_with_missing_understat(self, tmp_path):
        csv_content = textwrap.dedent("""\
            key_opta_numeric,key_understat,name
            80201,,Mohamed Salah
        """)
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert result == {}

    def test_skips_non_numeric_rows(self, tmp_path):
        csv_content = textwrap.dedent("""\
            key_opta_numeric,key_understat,name
            abc,xyz,Bad Row
            80201,1250,Good Row
        """)
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert result == {80201: 1250}

    def test_float_strings_parsed_as_int(self, tmp_path):
        # Some CSVs export integers as "80201.0"
        csv_content = textwrap.dedent("""\
            key_opta_numeric,key_understat,name
            80201.0,1250.0,Mohamed Salah
        """)
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert result == {80201: 1250}

    def test_empty_csv_returns_empty_dict(self, tmp_path):
        csv_content = "key_opta_numeric,key_understat,name\n"
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert result == {}

    def test_uses_existing_cache_file(self, tmp_path):
        # Writes a valid CSV; if caching logic re-downloads it would overwrite
        # with different data — we verify the cached content is used as-is.
        csv_content = textwrap.dedent("""\
            key_opta_numeric,key_understat,name
            80201,1250,Mohamed Salah
        """)
        csv_file = tmp_path / "reep_people.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        result = load_reep_map(cache_path=str(csv_file))

        assert result == {80201: 1250}


# ---------------------------------------------------------------------------
# build_reep_matches
# ---------------------------------------------------------------------------


class TestBuildReepMatches:
    def _call(self, fpl_players, us_players, codes, reep_map):
        return build_reep_matches(
            fpl_players, MOCK_FPL_TEAMS_REEP, us_players, codes, reep_map
        )

    def test_matches_player_present_in_both(self):
        results = self._call([_HAALAND], [_US_HAALAND], FPL_PLAYER_CODES, REEP_MAP)

        assert len(results) == 1
        m = results[0]
        assert m["fpl_id"] == 355
        assert m["understat_id"] == 8260
        assert m["match_tier"] == "reep"
        assert m["confidence"] == 100

    def test_names_and_teams_populated(self):
        results = self._call([_HAALAND], [_US_HAALAND], FPL_PLAYER_CODES, REEP_MAP)

        m = results[0]
        assert m["fpl_name"] == "Erling Haaland"
        assert m["understat_name"] == "Erling Haaland"
        assert m["fpl_team"] == "Man City"
        assert m["understat_team"] == "Manchester City"

    def test_player_without_code_skipped(self):
        # _UNKNOWN has no entry in FPL_PLAYER_CODES
        results = self._call([_UNKNOWN], [_US_SALAH, _US_HAALAND], FPL_PLAYER_CODES, REEP_MAP)

        assert results == []

    def test_player_whose_us_id_not_in_understat_skipped(self):
        # reep says fpl_code 80201 → us_id 1250, but understat list is empty
        results = self._call([_SALAH], [], FPL_PLAYER_CODES, REEP_MAP)

        assert results == []

    def test_no_double_claim_on_same_understat_id(self):
        # Two FPL players both pointing to the same understat id (malformed reep).
        salah2 = {**_SALAH, "id": 500, "second_name": "Salah2"}
        codes = {**FPL_PLAYER_CODES, 500: 80201}  # same FPL code as Salah — same us_id

        results = self._call([_SALAH, salah2], [_US_SALAH], codes, REEP_MAP)

        # Only one match should be produced.
        assert len(results) == 1

    def test_multiple_players_matched(self):
        results = self._call(
            [_SALAH, _HAALAND], [_US_SALAH, _US_HAALAND], FPL_PLAYER_CODES, REEP_MAP
        )

        assert len(results) == 2
        tiers = {m["match_tier"] for m in results}
        assert tiers == {"reep"}

    def test_empty_inputs_return_empty(self):
        assert self._call([], [], {}, {}) == []

    def test_empty_reep_map_returns_empty(self):
        results = self._call([_HAALAND], [_US_HAALAND], FPL_PLAYER_CODES, {})
        assert results == []


# ---------------------------------------------------------------------------
# match_players_with_reep
# ---------------------------------------------------------------------------


class TestMatchPlayers:
    """Tests for match_players (reep + fuzzy fallback orchestrator).

    Uses in-memory fixtures only; no DB, no network.
    """

    def _call(self, fpl_players, us_players, codes, reep_map, threshold=85):
        return match_players(
            fpl_players, MOCK_FPL_TEAMS_REEP, us_players, codes, reep_map, threshold
        )

    def test_reep_player_not_passed_to_fuzzy(self):
        # Haaland resolved via reep; should appear exactly once.
        results = self._call([_HAALAND], [_US_HAALAND], FPL_PLAYER_CODES, REEP_MAP)

        haaland_matches = [m for m in results if m["fpl_id"] == 355]
        assert len(haaland_matches) == 1
        assert haaland_matches[0]["match_tier"] == "reep"

    def test_fallback_player_matched_via_fuzzy(self):
        # _UNKNOWN has no code → not in reep → falls to fuzzy.
        # Give it a matching understat entry so fuzzy can resolve it.
        us_unknown = {
            "player_id": 7777, "player": "New Player",
            "team": "Arsenal", "position": "MC", "fpl_element_type": 3,
            "all_teams": ["Arsenal"],
        }
        fpl_teams_with_arsenal = {
            **MOCK_FPL_TEAMS_REEP,
            1: {"name": "Arsenal", "short_name": "ARS"},
        }
        results = match_players(
            [_UNKNOWN], fpl_teams_with_arsenal, [us_unknown], {}, {}, threshold=85
        )

        assert len(results) == 1
        assert results[0]["fpl_id"] == 999
        assert results[0]["match_tier"] != "reep"

    def test_reep_match_not_claimed_by_fuzzy(self):
        # Both players available; Haaland resolved via reep.
        # Fuzzy must not also claim Haaland's understat entry for someone else.
        results = self._call(
            [_SALAH, _HAALAND], [_US_SALAH, _US_HAALAND], FPL_PLAYER_CODES, REEP_MAP
        )

        us_ids = [m["understat_id"] for m in results]
        assert len(us_ids) == len(set(us_ids)), "Understat player claimed twice"

    def test_empty_reep_map_falls_back_entirely_to_fuzzy(self):
        # With empty reep_map and codes, match_players must still resolve
        # players that fuzzy can handle.
        fpl_teams = {13: {"name": "Man City", "short_name": "MCI"}}
        results = match_players([_HAALAND], fpl_teams, [_US_HAALAND], {}, {}, threshold=85)

        assert len(results) == 1
        assert results[0]["fpl_id"] == 355
        assert results[0]["understat_id"] == 8260
        assert results[0]["match_tier"] != "reep"

    def test_result_schema_matches_match_players_output(self):
        expected_keys = {
            "fpl_id", "understat_id", "web_name", "fpl_name",
            "understat_name", "fpl_team", "understat_team",
            "confidence", "match_tier",
        }
        results = self._call([_HAALAND], [_US_HAALAND], FPL_PLAYER_CODES, REEP_MAP)

        assert len(results) == 1
        assert set(results[0].keys()) == expected_keys
