"""The dimensions are held to their own per-season floors, and a short table of
either kind publishes nothing.

The harness is shared with the previous-manifest tests: see publish_harness.py.
Most tests here run against a previous manifest written before the dimensions
were served (tables=FACTS), which is what the first publish after they are
added reads. The dimensions then have no previous count, so only their floor
can refuse them, and that is what these tests isolate.
"""

from __future__ import annotations

import pytest

from publish_harness import (
    CLOSED,
    FACTS,
    LIVE,
    SERVED,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)


@pytest.fixture
def publish(tmp_path, monkeypatch):
    """Build a warehouse from `build`, then run main() against `previous`."""
    return make_publish(tmp_path, monkeypatch)


def facts_only_previous() -> dict:
    return manifest(FACTS, **{CLOSED: season(10, 38), LIVE: season(10, 4)})


# AC2 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#44 AC2")
@pytest.mark.parametrize(
    ("table", "short", "expected"),
    [
        ("dim_team", {"team_rows": 19}, 20),
        ("dim_fixture", {"fixture_rows": 379}, 380),
        ("dim_player", {"player_rows": 9}, 10),
    ],
    ids=["19 teams", "379 fixtures", "one player fewer than staged"],
)
def test_a_dimension_below_its_per_season_expectation_is_refused(
    publish, capsys, table, short, expected
):
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4, **short)},
        facts_only_previous(),
    )

    assert_refused(result)
    assert any(
        table in line and LIVE in line and f"{expected:,}" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {table}, {LIVE} and the expected {expected}"


@pytest.mark.integration
@pytest.mark.covers("#44 AC2")
@pytest.mark.parametrize(
    ("table", "missing"),
    [
        ("dim_team", {"team_rows": 0}),
        ("dim_fixture", {"fixture_rows": 0}),
        ("dim_player", {"player_rows": 0}),
    ],
    ids=["dim_team", "dim_fixture", "dim_player"],
)
def test_a_season_in_staging_but_missing_from_a_dimension_scores_zero_and_is_refused(
    publish, capsys, table, missing
):
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4, **missing)},
        facts_only_previous(),
    )

    assert_refused(result)
    assert any(
        table in line and LIVE in line and " 0 " in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.integration
@pytest.mark.covers("#44 AC2")
def test_dimensions_exactly_at_their_expectation_publish_and_are_listed_per_season(
    publish,
):
    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5)}, facts_only_previous()
    )

    assert_published(result)
    _, s3 = result
    by_season = s3.published_manifest()["row_counts_by_season"]
    assert by_season["dim_team"] == {CLOSED: 20, LIVE: 20}
    assert by_season["dim_fixture"] == {CLOSED: 380, LIVE: 380}
    assert by_season["dim_player"] == {CLOSED: 841, LIVE: 667}


# AC6 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#44 AC6")
@pytest.mark.parametrize(
    "short",
    [
        {"fixture": 1},
        {"gameweek": 1},
        {"team_rows": 19},
        {"player_rows": 9},
        {"fixture_rows": 379},
    ],
    ids=list(SERVED),
)
def test_any_one_served_table_below_its_floor_publishes_nothing(publish, short):
    # Every other table clears its floor; the one short table must stop all
    # five uploads and the manifest, so served/ never pairs new tables with
    # stale ones.
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4, **short)},
        facts_only_previous(),
    )

    assert_refused(result)


# AC7 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#44 AC7")
def test_a_season_whose_team_captures_were_all_empty_is_flagged(publish, capsys):
    # Empty teams arrays never reach stg_team, so the season has no staged
    # teams and dim_team has none either. Players and fixtures still stage it.
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4, teams=0)},
        facts_only_previous(),
    )

    assert_refused(result)
    assert any(
        "dim_team" in line and LIVE in line and "20" in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.integration
@pytest.mark.covers("#44 AC7")
def test_the_floor_finds_a_season_that_only_fixtures_and_history_still_stage(
    publish, capsys
):
    # Every bootstrap-static capture of the season came back empty: no
    # players, no rounds, no teams. Only the fixtures endpoint and
    # element-summary history still carry the season, so a season list read
    # from bootstrap-derived staging alone would never check it.
    result = publish(
        {
            CLOSED: season(10, 38),
            LIVE: season(0, 0, teams=0, player_fixture_rows=5),
        },
        # No previous count for the live season, so the previous-publish check
        # cannot refuse it and only the floor can.
        manifest(FACTS, **{CLOSED: season(10, 38)}),
    )

    assert_refused(result)
    assert any(
        "dim_team" in line and LIVE in line
        for line in errors(capsys.readouterr().out)
    )
