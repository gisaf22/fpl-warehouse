"""Contract v2: fct_player_gameweek drops deadline_time and NULLs unobserved measures.

#186 ships #133 S17 and S19 under one served_contract_version bump. These tests
read the real models/marts/schema.yml and dbt_project.yml: the enforced
contract in schema.yml is the shape dbt builds, and the version is the one the
publish step will write. The publish harness is shared: see publish_harness.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import publish_served
from publish_harness import (
    CLOSED,
    LIVE,
    SERVED,
    SHAPE,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "models" / "marts" / "schema.yml"

BUILD = {CLOSED: season(10, 38), LIVE: season(10, 4)}

# The real project's version, read before any test points the harness's
# PROJECT_FILE at its own temporary dbt_project.yml.
PROJECT_VERSION = publish_served.contract_version()

# fct_player_gameweek's columns as served at contract_version 1, from the
# manifest's `columns` field: what the previous publish recorded.
V1_COLUMNS = [
    ["season", "VARCHAR"],
    ["fpl_id", "INTEGER"],
    ["gameweek", "INTEGER"],
    ["web_name", "VARCHAR"],
    ["deadline_time", "TIMESTAMP"],
    ["fixture_count", "INTEGER"],
    ["first_kickoff_time", "TIMESTAMP"],
    ["last_kickoff_time", "TIMESTAMP"],
    ["is_ratified", "BOOLEAN"],
    *[[name, "INTEGER"] for name in (
        "minutes", "starts", "total_points", "bonus", "bps", "goals_scored",
        "assists", "clean_sheets", "goals_conceded", "own_goals",
        "penalties_saved", "penalties_missed", "yellow_cards", "red_cards",
        "saves", "clearances_blocks_interceptions", "recoveries", "tackles",
        "defensive_contribution",
    )],
    *[[name, "DOUBLE"] for name in (
        "expected_goals", "expected_assists", "expected_goal_involvements",
        "expected_goals_conceded", "influence", "creativity", "threat",
        "ict_index",
    )],
    *[[name, "INTEGER"] for name in (
        "value", "selected", "transfers_in", "transfers_out", "transfers_balance",
    )],
]

MEASURES = [name for name, _ in V1_COLUMNS[9:36]]


def gameweek_model() -> dict:
    models = yaml.safe_load(SCHEMA.read_text())["models"]
    return next(model for model in models if model["name"] == "fct_player_gameweek")


def contract_columns() -> list[list[str]]:
    """fct_player_gameweek's enforced contract, as [name, type] in order."""
    return [[c["name"], c["data_type"]] for c in gameweek_model()["columns"]]


def ddl(columns: list[list[str]]) -> str:
    return ", ".join(f"{name} {kind}" for name, kind in columns)


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous_v1() -> dict:
    columns = {table: SHAPE for table in SERVED}
    columns["fct_player_gameweek"] = V1_COLUMNS
    return manifest(contract_version=1, columns=columns, **BUILD)


# AC3 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#186 AC3")
def test_the_contract_has_no_deadline_time_and_publishes_at_the_project_version(
    publish,
):
    columns = contract_columns()
    assert "deadline_time" not in [name for name, _ in columns]

    result = publish(
        BUILD,
        previous_v1(),
        version=PROJECT_VERSION,
        columns={"fct_player_gameweek": ddl(columns)},
    )

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["columns"]["fct_player_gameweek"] == columns


@pytest.mark.integration
@pytest.mark.covers("#186 AC3")
def test_the_contract_without_a_version_bump_is_refused(publish, capsys):
    result = publish(
        BUILD,
        previous_v1(),
        version=1,
        columns={"fct_player_gameweek": ddl(contract_columns())},
    )

    assert_refused(result)
    assert any(
        "fct_player_gameweek" in line for line in errors(capsys.readouterr().out)
    )


# AC4 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#186 AC4")
def test_no_measure_carries_a_not_null_test():
    columns = {c["name"]: c for c in gameweek_model()["columns"]}
    carrying = [
        name
        for name in MEASURES
        if any(
            "not_null" in (test if isinstance(test, dict) else {test: None})
            for test in columns[name].get("data_tests") or []
        )
    ]
    assert carrying == []


@pytest.mark.unit
@pytest.mark.covers("#186 AC4")
def test_one_null_exactly_when_test_covers_every_measure_on_fixture_count_zero():
    tests = [
        test["null_exactly_when"]
        for test in gameweek_model().get("data_tests") or []
        if isinstance(test, dict) and "null_exactly_when" in test
    ]
    assert len(tests) == 1
    arguments = tests[0]["arguments"]
    assert arguments["condition"] == "fixture_count = 0"
    assert arguments["columns"] == MEASURES


# AC5 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#186 AC5")
def test_the_served_contract_version_is_bumped_past_one():
    # "At least 2" rather than "exactly 2", so a later breaking change can bump
    # again without editing this test.
    assert PROJECT_VERSION >= 2
