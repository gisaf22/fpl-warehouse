"""The served contract carries a version, and a shape break needs a bump.

The manifest records `contract_version`, read from dbt_project.yml's
served_contract_version var, and each served table's columns as uploaded. A
publish is refused when the version goes down, or when an existing column is
dropped, renamed, retyped or moved without a higher version. The harness is
shared: see publish_harness.py.
"""

from __future__ import annotations

import pytest

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

BUILD = {CLOSED: season(10, 38), LIVE: season(10, 4)}


@pytest.fixture
def publish(tmp_path, monkeypatch):
    return make_publish(tmp_path, monkeypatch)


def previous(version: int = 1, tables: tuple[str, ...] = SERVED) -> dict:
    """A previous manifest at `version`, listing the harness shape for `tables`."""
    return manifest(
        contract_version=version,
        columns={table: SHAPE for table in tables},
        **BUILD,
    )


# AC1 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#74 AC1")
def test_the_manifest_carries_the_contract_version_from_the_project_file(publish):
    result = publish(BUILD, previous(), version=1)

    assert_published(result)
    _, s3 = result
    value = s3.published_manifest()["contract_version"]
    assert value == 1 and type(value) is int


@pytest.mark.integration
@pytest.mark.covers("#74 AC1")
def test_the_manifest_lists_every_served_tables_columns_in_order(publish):
    result = publish(
        BUILD,
        previous(),
        columns={"dim_team": "season varchar, row_number integer, short_name varchar"},
    )

    assert_published(result)
    _, s3 = result
    columns = s3.published_manifest()["columns"]
    assert set(columns) == set(SERVED)
    assert columns["dim_team"] == [*SHAPE, ["short_name", "VARCHAR"]]
    assert columns["fct_player_fixture"] == SHAPE


# AC2 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#74 AC2")
def test_a_lower_contract_version_is_refused_and_named(publish, capsys):
    result = publish(BUILD, previous(version=2), version=1)

    assert_refused(result)
    assert any(
        "contract_version" in line and "1" in line and "2" in line
        for line in errors(capsys.readouterr().out)
    )


# AC3 -------------------------------------------------------------------------

BREAKS = {
    "dropped": "season varchar",
    "renamed": "season varchar, row_id integer",
    "retyped": "season varchar, row_number bigint",
    "reordered": "row_number integer, season varchar",
}


@pytest.mark.unit
@pytest.mark.covers("#74 AC3")
@pytest.mark.parametrize("ddl", BREAKS.values(), ids=BREAKS.keys())
def test_a_shape_break_at_the_same_version_is_refused_and_names_the_table(
    publish, capsys, ddl
):
    result = publish(BUILD, previous(version=1), version=1, columns={"dim_player": ddl})

    assert_refused(result)
    assert any("dim_player" in line for line in errors(capsys.readouterr().out))


@pytest.mark.unit
@pytest.mark.covers("#74 AC3")
@pytest.mark.parametrize("ddl", BREAKS.values(), ids=BREAKS.keys())
def test_a_shape_break_with_a_higher_version_publishes(publish, ddl):
    result = publish(BUILD, previous(version=1), version=2, columns={"dim_player": ddl})

    assert_published(result)


# AC4 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#74 AC4")
def test_a_column_appended_last_at_the_same_version_publishes(publish):
    result = publish(
        BUILD,
        previous(version=1),
        version=1,
        columns={
            "fct_player_fixture": "season varchar, row_number integer, extra integer"
        },
    )

    assert_published(result)


@pytest.mark.unit
@pytest.mark.covers("#74 AC4")
def test_a_table_the_previous_manifest_did_not_list_publishes_at_the_same_version(
    publish,
):
    result = publish(
        BUILD,
        previous(version=1, tables=("fct_player_fixture", "fct_player_gameweek")),
        version=1,
        columns={"dim_team": "team_name varchar, season varchar"},
    )

    assert_published(result)


# AC5 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#74 AC5")
def test_a_previous_manifest_without_a_version_or_columns_is_a_valid_baseline(
    publish,
):
    before = manifest(**BUILD)
    assert "contract_version" not in before and "columns" not in before

    result = publish(BUILD, before, version=1, columns={"dim_player": "season varchar"})

    assert_published(result)
    _, s3 = result
    published = s3.published_manifest()
    assert published["contract_version"] == 1
    assert set(published["columns"]) == set(SERVED)
