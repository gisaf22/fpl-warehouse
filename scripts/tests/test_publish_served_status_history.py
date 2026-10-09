"""dim_player_status_history is published under the same guards as every
served table (#127).

Its floor is a season's distinct fpl_id count in staging, at 0% tolerance:
every staged player has at least one row, so one row fewer than the players
is a lost row. More rows than players is the normal case, since a status change
opens a row. The previous-publish comparison holds it like any other table.
It is a new served table, so it publishes at the same contract_version. The
harness is shared: see publish_harness.py.
"""

from __future__ import annotations

import pytest

from publish_harness import (
    CLOSED,
    FACTS,
    DIMENSIONS,
    LIVE,
    SHAPE,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)

TABLE = "dim_player_status_history"
BUILD = {CLOSED: season(841, 38), LIVE: season(667, 5)}


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous_without_the_table(**by_season) -> dict:
    """A manifest from before this table was served, at contract_version 1."""
    tables = FACTS + DIMENSIONS
    return manifest(
        tables,
        contract_version=1,
        columns={table: SHAPE for table in tables},
        **(by_season or BUILD),
    )


@pytest.mark.unit
@pytest.mark.covers("#127 AC3")
def test_one_row_fewer_than_the_seasons_players_is_refused_naming_it(publish, capsys):
    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5, status_history_rows=666)},
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "667" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE}, {LIVE} and the expected 667"


@pytest.mark.unit
@pytest.mark.covers("#127 AC3")
def test_a_season_in_staging_but_missing_from_the_table_is_refused(publish, capsys):
    result = publish(
        {CLOSED: season(841, 38, status_history_rows=0), LIVE: season(667, 5)},
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and CLOSED in line and " 0 " in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.unit
@pytest.mark.covers("#127 AC3")
@pytest.mark.parametrize("live_rows", [667, 1122], ids=["one row per player", "more rows than players"])
def test_at_or_above_the_player_count_publishes_and_the_manifest_lists_it(
    publish, live_rows
):
    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5, status_history_rows=live_rows)},
        previous_without_the_table(),
    )

    assert_published(result)
    _, s3 = result
    published = s3.published_manifest()
    assert published["row_counts"][TABLE] == 841 + live_rows
    assert published["row_counts_by_season"][TABLE] == {CLOSED: 841, LIVE: live_rows}
    assert published["columns"][TABLE] == SHAPE


@pytest.mark.unit
@pytest.mark.covers("#127 AC3")
def test_fewer_rows_than_the_previous_publish_is_refused_though_above_the_floor(
    publish, capsys
):
    previous = manifest(
        contract_version=1,
        **{CLOSED: season(841, 38), LIVE: season(667, 5, status_history_rows=1122)},
    )

    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5, status_history_rows=1121)},
        previous,
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "1,122" in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.unit
@pytest.mark.covers("#127 AC3")
def test_first_publish_needs_no_contract_version_bump(publish):
    result = publish(BUILD, previous_without_the_table(), version=1)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["contract_version"] == 1
