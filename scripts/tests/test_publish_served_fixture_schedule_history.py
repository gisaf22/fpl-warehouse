"""dim_fixture_schedule_history is published under the same guards as every
served table (#154).

Its floor is a season's distinct fixture_id count in stg_fixture, at 0%
tolerance (#151 C10): every staged fixture has at least one row, its first
capture opening it, so one row fewer than the fixtures is a lost row. More
rows than fixtures is normal, since a schedule change opens a row. The floor is
the distinct count, not stg_fixture's rows, which hold one per fixture per
capture. The previous-publish comparison holds it like any other table. It is
a new served table, so it publishes at the same contract_version (#151 C11).
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
    MARKET,
    SHAPE,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)

TABLE = "dim_fixture_schedule_history"
# 2025-26 has one fixtures capture; the live season several, and one more
# fixture than a season's 380, as the fixture tree's synthetic fixture 999
# gives it. Its floor is 381 distinct fixtures, not its 1,143 staged rows.
BUILD = {
    CLOSED: season(841, 38),
    LIVE: season(667, 5, fixtures=381, fixture_rows=380, fixture_captures=3),
}


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous_without_the_table() -> dict:
    """A manifest from before this table was served, at contract_version 1."""
    tables = FACTS + DIMENSIONS + HISTORY + MARKET
    return manifest(
        tables,
        contract_version=1,
        columns={table: SHAPE for table in tables},
        **BUILD,
    )


def live(**served) -> dict:
    return season(
        667, 5, fixtures=381, fixture_rows=380, fixture_captures=3, **served
    )


@pytest.mark.unit
@pytest.mark.covers("#154 AC3")
def test_one_row_fewer_than_the_seasons_fixtures_is_refused_naming_it(
    publish, capsys
):
    result = publish(
        {CLOSED: season(841, 38), LIVE: live(schedule_history_rows=380)},
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "381" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE}, {LIVE} and the expected 381"


@pytest.mark.unit
@pytest.mark.covers("#154 AC3")
def test_a_season_in_staging_but_missing_from_the_table_is_refused(publish, capsys):
    result = publish(
        {CLOSED: season(841, 38, schedule_history_rows=0), LIVE: live()},
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and CLOSED in line and " 0 " in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.unit
@pytest.mark.covers("#154 AC3")
@pytest.mark.parametrize(
    "live_rows",
    [381, 577],
    ids=["one row per fixture", "more rows than fixtures"],
)
def test_at_or_above_the_fixture_count_publishes_and_the_manifest_lists_it(
    publish, live_rows
):
    result = publish(
        {CLOSED: season(841, 38), LIVE: live(schedule_history_rows=live_rows)},
        previous_without_the_table(),
    )

    assert_published(result)
    _, s3 = result
    published = s3.published_manifest()
    assert published["row_counts"][TABLE] == 380 + live_rows
    assert published["row_counts_by_season"][TABLE] == {CLOSED: 380, LIVE: live_rows}
    assert published["columns"][TABLE] == SHAPE


@pytest.mark.unit
@pytest.mark.covers("#154 AC3")
def test_fewer_rows_than_the_previous_publish_is_refused_though_above_the_floor(
    publish, capsys
):
    previous = manifest(
        contract_version=1,
        **{CLOSED: season(841, 38), LIVE: live(schedule_history_rows=577)},
    )

    result = publish(
        {CLOSED: season(841, 38), LIVE: live(schedule_history_rows=576)},
        previous,
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "577" in line
        for line in errors(capsys.readouterr().out)
    )


@pytest.mark.unit
@pytest.mark.covers("#154 AC3")
def test_first_publish_needs_no_contract_version_bump(publish):
    result = publish(BUILD, previous_without_the_table(), version=1)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["contract_version"] == 1
