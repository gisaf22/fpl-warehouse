"""The publish is refused when a season shrinks against the previous publish.

The harness is shared with the dimension tests: see publish_harness.py.
"Refused" means exit 1 with nothing uploaded; "proceeds" means exit 0 with
every served table and the manifest uploaded.
"""

from __future__ import annotations

import json

import pytest

from publish_harness import (
    CLOSED,
    LIVE,
    SERVED,
    assert_published,
    assert_refused,
    make_publish,
    manifest,
    season,
)


@pytest.fixture
def publish(tmp_path, monkeypatch):
    """Build a warehouse from `build`, then run main() against `previous`."""
    return make_publish(tmp_path, monkeypatch)


# AC1 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC1")
def test_a_season_lost_upstream_of_staging_is_refused(publish, capsys):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38)}, previous)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    for table in SERVED:
        before = previous["row_counts_by_season"][table][LIVE]
        assert any(
            table in line and LIVE in line and f"{before:,}" in line and " 0 " in line
            for line in errors
        ), f"no error names {table}, {LIVE}, the previous {before} and the new 0: {errors}"


@pytest.mark.unit
@pytest.mark.covers("#63 AC1")
def test_a_season_that_loses_some_rows_while_clearing_its_floor_is_refused(
    publish, capsys
):
    # A round of captures vanished upstream: staging expects 3 gameweeks, not 4,
    # so the floor passes at 30 while the last publish served 40.
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 3)}, previous)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any(
        "fct_player_gameweek" in line and LIVE in line and "40" in line and "30" in line
        for line in errors
    ), errors


@pytest.mark.unit
@pytest.mark.covers("#63 AC1")
def test_a_closed_season_that_shrinks_is_refused(publish, capsys):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    # One row fewer in one table, well inside that table's 15% floor.
    result = publish(
        {CLOSED: season(10, 38, fixture=379), LIVE: season(10, 4)}, previous
    )

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any(
        "fct_player_fixture" in line
        and CLOSED in line
        and "380" in line
        and "379" in line
        for line in errors
    ), errors


# AC2 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC2")
def test_a_named_restatement_lets_that_season_shrink_and_is_recorded(publish, capsys):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 3)}, previous, ["--restate", LIVE]
    )

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["restated_seasons"] == [LIVE]
    log = capsys.readouterr().out
    assert any(
        "restate" in line.lower() and LIVE in line for line in log.splitlines()
    ), log


@pytest.mark.unit
@pytest.mark.covers("#63 AC2")
def test_a_restatement_does_not_cover_a_season_it_does_not_name(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish(
        {CLOSED: season(10, 38, fixture=379), LIVE: season(10, 3)},
        previous,
        ["--restate", LIVE],
    )

    assert_refused(result)


@pytest.mark.unit
@pytest.mark.covers("#63 AC2")
def test_a_publish_without_a_restatement_records_none(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["restated_seasons"] == []


# AC3 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC3")
def test_a_season_published_for_the_first_time_is_not_held_to_a_previous_count(publish):
    previous = manifest(**{CLOSED: season(10, 38)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 1)}, previous)

    assert_published(result)


@pytest.mark.unit
@pytest.mark.covers("#63 AC3")
def test_a_season_published_for_the_first_time_is_still_held_to_its_floor(publish):
    previous = manifest(**{CLOSED: season(10, 38)})

    # 30 of an expected 40 is 25% short, below fct_player_gameweek's 2% floor.
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4, gameweek=30)}, previous
    )

    assert_refused(result)


# AC4 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_a_missing_previous_manifest_is_refused_and_named(publish, capsys):
    result = publish({CLOSED: season(10, 38), LIVE: season(10, 4)}, None)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any("manifest" in line and "NoSuchKey" in line for line in errors), errors


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
@pytest.mark.parametrize(
    "body",
    [b"not json", json.dumps({"run_id": "previous"}).encode()],
    ids=["not JSON", "no per-season counts"],
)
def test_an_unreadable_previous_manifest_is_refused_and_named(publish, capsys, body):
    result = publish({CLOSED: season(10, 38), LIVE: season(10, 4)}, body)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any("manifest" in line for line in errors), errors


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_publishing_without_a_baseline_proceeds_when_explicitly_overridden(publish):
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4)}, None, ["--without-baseline"]
    )

    assert_published(result)


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_publishing_without_a_baseline_is_recorded_in_the_manifest_and_log(
    publish, capsys
):
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4)}, None, ["--without-baseline"]
    )

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["published_without_baseline"] is True
    log = capsys.readouterr().out
    assert any("without-baseline" in line for line in log.splitlines()), log


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_a_publish_with_a_baseline_records_no_baseline_override(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["published_without_baseline"] is False


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_a_previous_manifest_written_before_restatements_existed_is_accepted(publish):
    # Today's published manifest: per-season counts, no restated_seasons or
    # published_without_baseline keys. The first publish after this change
    # reads exactly this shape.
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})
    assert "restated_seasons" not in previous

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)


# AC5 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC5")
def test_a_build_where_every_season_grows_or_holds_proceeds(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(11, 5)}, previous)

    assert_published(result)
