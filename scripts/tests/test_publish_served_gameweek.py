"""dim_gameweek is published under the same guards as every served table (#170).

Its floor is exact: 38 rows for every season with an admitted bootstrap-static
capture, at 0% tolerance, and a row more is refused as well as a row fewer
(#163 S11 amended). The season list comes from int_admitted_capture, not from
staging, for this table only (#163 S15): a season admitted but never staged
must still fail here. The previous-publish comparison holds it like any other
table, and from its first publish its columns are a one-way door (#74). It is
a new served table, so it publishes at the same contract_version (S6).
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
    SCHEDULE,
    SERVED,
    SHAPE,
    assert_published,
    assert_refused,
    errors,
    make_publish,
    manifest,
    season,
)

TABLE = "dim_gameweek"
BUILD = {CLOSED: season(841, 38), LIVE: season(667, 5)}

# The contract's five columns, as DDL for the harness and as the manifest
# records them.
CONTRACT = (
    "season varchar, gameweek integer, deadline_time timestamp, "
    "last_capture_before_deadline_at timestamp, state_age_seconds integer"
)
CONTRACT_SHAPE = [
    ["season", "VARCHAR"],
    ["gameweek", "INTEGER"],
    ["deadline_time", "TIMESTAMP"],
    ["last_capture_before_deadline_at", "TIMESTAMP"],
    ["state_age_seconds", "INTEGER"],
]


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous_without_the_table() -> dict:
    """A manifest from before this table was served, at contract_version 1."""
    tables = FACTS + DIMENSIONS + HISTORY + MARKET + SCHEDULE
    return manifest(
        tables,
        contract_version=1,
        columns={table: SHAPE for table in tables},
        **BUILD,
    )


# AC3 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#170 AC3")
@pytest.mark.parametrize("rows", [37, 39], ids=["one short", "one over"])
def test_a_season_other_than_38_gameweeks_is_refused_naming_it(
    publish, capsys, rows
):
    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5, gameweek_dim_rows=rows)},
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and LIVE in line and "38" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE}, {LIVE} and the expected 38"


@pytest.mark.unit
@pytest.mark.covers("#170 AC3")
def test_an_admitted_season_missing_from_staging_and_the_table_is_refused(
    publish, capsys
):
    # Admitted bootstrap-static, but nothing staged: no staging model holds
    # the season, so only admission can name it.
    admitted_only = season(
        0, 0, teams=0, fixtures=0, player_fixture_rows=0, gameweek_dim_rows=0
    )
    result = publish(
        {CLOSED: admitted_only, LIVE: season(667, 5)},
        previous_without_the_table(),
    )

    assert_refused(result)
    assert any(
        TABLE in line and CLOSED in line and " 0 " in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE} and {CLOSED} with 0 rows"


@pytest.mark.unit
@pytest.mark.covers("#170 AC3")
def test_a_season_admitted_only_for_another_endpoint_is_not_held_to_38(publish):
    # The live season's only admitted capture is a fixtures one, so it is not
    # a season with an admitted bootstrap-static capture and has no gameweeks.
    result = publish(
        {CLOSED: season(841, 38), LIVE: season(667, 5, bootstrap_admitted=False)},
        previous_without_the_table(),
    )

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["row_counts_by_season"][TABLE] == {CLOSED: 38}


@pytest.mark.unit
@pytest.mark.covers("#170 AC3")
def test_38_per_admitted_season_publishes_and_the_manifest_lists_it(publish):
    result = publish(
        BUILD, previous_without_the_table(), columns={TABLE: CONTRACT}
    )

    assert_published(result)
    _, s3 = result
    published = s3.published_manifest()
    assert published["row_counts"][TABLE] == 76
    assert published["row_counts_by_season"][TABLE] == {CLOSED: 38, LIVE: 38}
    assert published["columns"][TABLE] == CONTRACT_SHAPE


@pytest.mark.unit
@pytest.mark.covers("#170 AC3")
def test_a_season_below_its_previous_published_count_is_refused(publish, capsys):
    # 2025-26 has left the build entirely: neither admitted nor staged, so the
    # floor cannot see it, and only the previous publish's 38 can.
    gone = season(
        0,
        0,
        teams=0,
        fixtures=0,
        player_fixture_rows=0,
        bootstrap_admitted=False,
    )
    result = publish(
        {CLOSED: gone, LIVE: season(667, 5)},
        manifest(contract_version=1, **BUILD),
    )

    assert_refused(result)
    assert any(
        TABLE in line and CLOSED in line and "38" in line and "previous" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE}'s previous 38 for {CLOSED}"


@pytest.mark.unit
@pytest.mark.covers("#170 AC3")
def test_first_publish_needs_no_contract_version_bump(publish):
    result = publish(BUILD, previous_without_the_table(), version=1)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["contract_version"] == 1


# AC4 -------------------------------------------------------------------------


def previous_with_the_table() -> dict:
    """A manifest from after the first publish, listing the contract's columns."""
    return manifest(
        contract_version=1,
        columns={
            **{table: SHAPE for table in SERVED},
            TABLE: CONTRACT_SHAPE,
        },
        **BUILD,
    )


@pytest.mark.unit
@pytest.mark.covers("#170 AC4")
@pytest.mark.parametrize(
    "changed",
    [
        "season varchar, gameweek integer, deadline_time timestamp, "
        "last_capture_before_deadline_at timestamp",
        "season varchar, gameweek integer, deadline_at timestamp, "
        "last_capture_before_deadline_at timestamp, state_age_seconds integer",
        "season varchar, gameweek integer, deadline_time timestamp, "
        "last_capture_before_deadline_at timestamp, state_age_seconds bigint",
        "season varchar, gameweek integer, last_capture_before_deadline_at "
        "timestamp, deadline_time timestamp, state_age_seconds integer",
    ],
    ids=["dropped", "renamed", "retyped", "moved"],
)
def test_a_changed_column_at_the_same_contract_version_is_refused(
    publish, capsys, changed
):
    result = publish(
        BUILD, previous_with_the_table(), version=1, columns={TABLE: changed}
    )

    assert_refused(result)
    assert any(
        TABLE in line and "contract_version" in line
        for line in errors(capsys.readouterr().out)
    ), f"no error names {TABLE}'s contract change"


@pytest.mark.unit
@pytest.mark.covers("#170 AC4")
def test_the_unchanged_columns_publish_at_the_same_contract_version(publish):
    result = publish(
        BUILD, previous_with_the_table(), version=1, columns={TABLE: CONTRACT}
    )

    assert_published(result)
