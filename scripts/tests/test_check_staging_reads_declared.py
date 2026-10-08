"""CI fails when a payload staging model reads its source around the declared columns.

`problems` is the pure core of scripts/check_staging_reads_declared.py: given a
parsed dbt manifest, it returns one message per violation, and CI's validate
job fails when the list is non-empty. A payload staging model must read its
source through `declared_records`, which selects only the columns declared in
sources.yml; calling `source()` itself would let it read any field. These tests
feed it hand-built manifests.
"""

from __future__ import annotations

import pytest

from check_staging_reads_declared import problems

VIA_MACRO = (
    "with raw as (\n"
    "    {{ declared_records('event_status', '$.status[*]') }}\n"
    ")\nselect cast(event as integer) as gameweek from raw"
)
DIRECT = (
    "with raw as (\n"
    "    select unnest(status) as st from {{ source('fpl_raw', 'event_status') }}\n"
    ")\nselect cast(st.event as integer) as gameweek from raw"
)


def source_id(table: str) -> str:
    return f"source.fpl_warehouse.fpl_raw.{table}"


def model(name: str, table: str, raw_code: str) -> tuple[str, dict]:
    return f"model.fpl_warehouse.{name}", {
        "resource_type": "model",
        "name": name,
        "raw_code": raw_code,
        "depends_on": {"nodes": [source_id(table)]},
    }


def manifest(*models: tuple[str, dict]) -> dict:
    return {"nodes": dict(models)}


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
def test_a_staging_model_reading_through_the_macro_passes():
    assert problems(manifest(model("stg_gameweek_status", "event_status", VIA_MACRO))) == []


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
def test_a_staging_model_calling_source_itself_fails_naming_the_model_and_source():
    found = problems(manifest(model("stg_gameweek_status", "event_status", DIRECT)))
    assert len(found) == 1
    assert "stg_gameweek_status" in found[0] and "event_status" in found[0]


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
@pytest.mark.parametrize("table", ["run_manifests", "backfill_catalog"])
def test_a_model_reading_an_explicit_column_source_directly_passes(table):
    code = f"select run_id from {{{{ source('fpl_raw', '{table}') }}}}"
    found = problems(
        manifest(
            model("stg_gameweek_status", "event_status", VIA_MACRO),
            model("stg_run", table, code),
        )
    )
    assert found == []


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
def test_no_payload_staging_model_found_fails_rather_than_passing_vacuously():
    found = problems(manifest())
    assert len(found) == 1
    assert "nothing was checked" in found[0]


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
def test_a_new_staging_model_calling_source_itself_fails_though_older_ones_await_conversion():
    found = problems(
        manifest(
            model("stg_gameweek_status", "event_status", VIA_MACRO),
            model("stg_new_payload", "fixtures", DIRECT),
        )
    )
    assert len(found) == 1
    assert "stg_new_payload" in found[0] and "fixtures" in found[0]


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
@pytest.mark.parametrize("name", ["stg_player", "stg_team", "stg_position", "stg_gameweek"])
def test_a_bootstrap_static_model_calling_source_itself_fails(name):
    code = "select unnest(elements) as e from {{ source('fpl_raw', 'bootstrap_static') }}"
    found = problems(manifest(model(name, "bootstrap_static", code)))
    assert len(found) == 1
    assert name in found[0] and "bootstrap_static" in found[0]


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
def test_stg_fixture_calling_source_itself_fails():
    code = "select * from {{ source('fpl_raw', 'fixtures') }}"
    found = problems(manifest(model("stg_fixture", "fixtures", code)))
    assert len(found) == 1
    assert "stg_fixture" in found[0] and "fixtures" in found[0]


@pytest.mark.unit
@pytest.mark.covers("#115 AC1")
def test_stg_player_fixture_calling_source_itself_fails():
    code = "select unnest(history) as h from {{ source('fpl_raw', 'element_summary') }}"
    found = problems(manifest(model("stg_player_fixture", "element_summary", code)))
    assert len(found) == 1
    assert "stg_player_fixture" in found[0] and "element_summary" in found[0]
