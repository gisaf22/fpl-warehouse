"""fct_manager_pick and fct_manager_gameweek are published under the guards (#216).

Both floors are exact, in both directions, like dim_gameweek's (#216 D13): a
season's expected fct_manager_gameweek rows are, for every gameweek with a
picks settlement marker, the panel managers whose join week (the first
gameweek of their entry-history, D6) is on or before it; fct_manager_pick
expects 15 per such row. A late joiner therefore counts only from their join
week. The expectation is read from staging (stg_manager_panel,
stg_entry_history, stg_entry_picks_settlement), never from the models'
parents. The previous-publish comparison holds both like any other table.
Both are new served tables, so they publish at the same contract_version.
The harness is shared: see publish_harness.py.
"""

from __future__ import annotations

import pytest

from publish_harness import (
    CLOSED,
    DIMENSIONS,
    FACTS,
    GAMEWEEK,
    HISTORY,
    LIVE,
    MARKET,
    SCHEDULE,
    SHAPE,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)

GAMEWEEK_TABLE = "fct_manager_gameweek"
PICK_TABLE = "fct_manager_pick"
# Three managers: two joined in gameweek 1, one in gameweek 3. Four marked
# gameweeks: 2 + 2 + 3 + 3 = 10 manager-gameweeks, 150 picks.
JOINS = (1, 1, 3)
LIVE_SHAPE = dict(manager_join_weeks=JOINS, marked_gameweeks=4)
BUILD = {CLOSED: season(841, 38), LIVE: season(667, 5, **LIVE_SHAPE)}


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous_without_the_tables() -> dict:
    """A manifest from before these tables were served, at contract_version 1."""
    tables = FACTS + DIMENSIONS + HISTORY + MARKET + SCHEDULE + GAMEWEEK
    return manifest(
        tables,
        contract_version=1,
        columns={table: SHAPE for table in tables},
        **BUILD,
    )


@pytest.mark.unit
@pytest.mark.covers("#216 AC17")
def test_one_row_per_manager_per_marked_gameweek_from_their_join_week_publishes(
    publish,
):
    result = publish(BUILD, previous_without_the_tables())

    assert_published(result)
    _, s3 = result
    published = s3.published_manifest()
    assert published["row_counts_by_season"][GAMEWEEK_TABLE] == {CLOSED: 0, LIVE: 10}
    assert published["row_counts_by_season"][PICK_TABLE] == {CLOSED: 0, LIVE: 150}
    assert published["contract_version"] == 1


@pytest.mark.unit
@pytest.mark.covers("#216 AC17")
@pytest.mark.parametrize("rows", [9, 11], ids=["one short", "one over"])
def test_a_manager_gameweek_count_other_than_expected_is_refused_naming_it(
    publish, capsys, rows
):
    result = publish(
        {
            CLOSED: season(841, 38),
            LIVE: season(667, 5, **LIVE_SHAPE, manager_gameweek_rows=rows),
        },
        previous_without_the_tables(),
    )

    assert_refused(result)
    assert any(
        GAMEWEEK_TABLE in line and LIVE in line and "10" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {GAMEWEEK_TABLE}, {LIVE} and the expected 10"


@pytest.mark.unit
@pytest.mark.covers("#216 AC17")
@pytest.mark.parametrize("rows", [149, 151], ids=["one short", "one over"])
def test_a_pick_count_other_than_fifteen_per_manager_gameweek_is_refused(
    publish, capsys, rows
):
    result = publish(
        {
            CLOSED: season(841, 38),
            LIVE: season(667, 5, **LIVE_SHAPE, manager_pick_rows=rows),
        },
        previous_without_the_tables(),
    )

    assert_refused(result)
    assert any(
        PICK_TABLE in line and LIVE in line and "150" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {PICK_TABLE}, {LIVE} and the expected 150"


@pytest.mark.unit
@pytest.mark.covers("#216 AC17")
def test_a_late_joiner_counted_before_their_join_week_is_refused(publish):
    # 12 rows is what every manager from gameweek 1 would give: the late
    # joiner's two pre-join weeks must not be expected or served.
    result = publish(
        {
            CLOSED: season(841, 38),
            LIVE: season(
                667, 5, **LIVE_SHAPE, manager_gameweek_rows=12, manager_pick_rows=180
            ),
        },
        previous_without_the_tables(),
    )

    assert_refused(result)


@pytest.mark.unit
@pytest.mark.covers("#216 AC17")
def test_a_season_below_its_previous_published_count_is_refused(publish, capsys):
    # The panel left staging entirely, so the floor expects nothing; only the
    # previous publish's 10 can see the loss.
    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5)},
        manifest(contract_version=1, **BUILD),
    )

    assert_refused(result)
    assert any(
        GAMEWEEK_TABLE in line and LIVE in line and "previous" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {GAMEWEEK_TABLE}'s previous count for {LIVE}"
