"""fct_player_market_snapshot is published under the same guards as every
served table (#143).

Its floor is a season's stg_player row count, at 0% tolerance: one row per
player per admitted bootstrap-static capture, which is exactly what the table
holds. It is not the distinct player count, which is the dimensions' and the
status history's floor. The previous-publish comparison holds it like any other
table. It is a new served table, so it publishes at the same contract_version.
The harness is shared: see publish_harness.py.
"""

from __future__ import annotations

import pytest

from publish_harness import (
    CLOSED,
    DIMENSIONS,
    FACTS,
    HISTORY,
    LIVE,
    SHAPE,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)

TABLE = "fct_player_market_snapshot"
# 2025-26 has one capture; the live season several, so the floor (players x
# captures, 2,001) differs from the player count (667).
BUILD = {CLOSED: season(841, 38), LIVE: season(667, 5, captures=3)}


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous_without_the_table(**by_season) -> dict:
    """A manifest from before this table was served, at contract_version 1."""
    tables = FACTS + DIMENSIONS + HISTORY
    return manifest(
        tables,
        contract_version=1,
        columns={table: SHAPE for table in tables},
        **(by_season or BUILD),
    )


@pytest.mark.unit
@pytest.mark.covers("#143 AC3")
@pytest.mark.parametrize(
    "live_rows",
    [2000, 667],
    ids=["one row short of players x captures", "one row per player only"],
)
def test_fewer_rows_than_players_times_captures_is_refused_naming_it(
    publish, capsys, live_rows
):
    result = publish(
        {
            CLOSED: season(841, 38),
            LIVE: season(667, 5, captures=3, market_snapshot_rows=live_rows),
        },
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "2,001" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE}, {LIVE} and the expected 2,001"


@pytest.mark.unit
@pytest.mark.covers("#143 AC3")
def test_a_season_in_staging_but_missing_from_the_table_is_refused(publish, capsys):
    result = publish(
        {
            CLOSED: season(841, 38, market_snapshot_rows=0),
            LIVE: season(667, 5, captures=3),
        },
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and CLOSED in line and " 0 " in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.unit
@pytest.mark.covers("#143 AC3")
def test_players_times_captures_publishes_and_the_manifest_lists_it(publish):
    result = publish(BUILD, previous_without_the_table())

    assert_published(result)
    _, s3 = result
    published = s3.published_manifest()
    assert published["row_counts"][TABLE] == 841 + 2001
    assert published["row_counts_by_season"][TABLE] == {CLOSED: 841, LIVE: 2001}
    assert published["columns"][TABLE] == SHAPE


@pytest.mark.unit
@pytest.mark.covers("#143 AC3")
def test_fewer_rows_than_the_previous_publish_is_refused_though_above_the_floor(
    publish, capsys
):
    previous = manifest(
        contract_version=1,
        **{
            CLOSED: season(841, 38),
            LIVE: season(667, 5, captures=3, market_snapshot_rows=2668),
        },
    )

    result = publish(
        {
            CLOSED: season(841, 38),
            LIVE: season(667, 5, captures=3, market_snapshot_rows=2667),
        },
        previous,
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "2,668" in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.unit
@pytest.mark.covers("#143 AC3")
def test_first_publish_needs_no_contract_version_bump(publish):
    result = publish(BUILD, previous_without_the_table(), version=1)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["contract_version"] == 1
