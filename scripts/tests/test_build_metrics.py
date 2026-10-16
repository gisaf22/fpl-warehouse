"""Passive build metrics: per-model seconds, the record's schema, and where it goes (#191).

`build_metrics` turns one build's dbt `run_results.json` and job facts into one
metrics record. Every build writes it to the job summary; only a scheduled
build also writes it to s3://fpl-data-safari/metrics/build/<run_id>.json.
`model_seconds` per model is the primary metric, the W1 baseline for #78.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from build_metrics import (
    FIELDS,
    MODEL_FIELDS,
    build_record,
    job_outcome,
    models_from_run_results,
    schema_problems,
    writes_to_s3,
)

FIXTURES = Path(__file__).parent / "fixtures" / "build_metrics"


def run_results() -> dict:
    return json.loads((FIXTURES / "run_results.json").read_text())


def valid_record() -> dict:
    return {
        "run_id": "18000000000",
        "git_sha": "0" * 40,
        "built_at": "2026-10-15T19:45:00Z",
        "trigger": "schedule",
        "status": "success",
        "exit_code": 0,
        "build_seconds": 450.0,
        "capture_count": 31000,
        "peak_rss_mib": 14800.0,
        "runner_total_mem_mib": 15995.0,
        "cpu_count": 4,
        "models": [
            {"name": "stg_player_history_capture", "model_seconds": 412.5, "status": "success"},
        ],
    }


@pytest.mark.unit
@pytest.mark.covers("#191 AC1")
def test_model_seconds_are_read_per_model_from_run_results():
    models = {m["name"]: m for m in models_from_run_results(run_results())}
    assert models["stg_player_history_capture"]["model_seconds"] == 412.5
    assert models["stg_player_fixture"]["model_seconds"] == 3.25


@pytest.mark.unit
@pytest.mark.covers("#191 AC1")
def test_errored_and_skipped_models_keep_their_status():
    models = {m["name"]: m for m in models_from_run_results(run_results())}
    assert models["fct_player_fixture"]["status"] == "error"
    assert models["fct_player_gameweek"]["status"] == "skipped"


@pytest.mark.unit
@pytest.mark.covers("#191 AC1")
def test_only_models_are_reported_not_tests_or_seeds():
    names = {m["name"] for m in models_from_run_results(run_results())}
    assert names == {
        "stg_player_history_capture",
        "stg_player_fixture",
        "fct_player_fixture",
        "fct_player_gameweek",
    }


@pytest.mark.unit
@pytest.mark.covers("#191 AC2")
def test_the_record_fields_are_exactly_the_agreed_set():
    assert FIELDS == (
        "run_id", "git_sha", "built_at", "trigger", "status", "exit_code",
        "build_seconds", "capture_count", "peak_rss_mib", "runner_total_mem_mib",
        "cpu_count", "models",
    )
    assert MODEL_FIELDS == ("name", "model_seconds", "status")


@pytest.mark.unit
@pytest.mark.covers("#191 AC2")
def test_a_complete_record_passes_the_schema():
    assert schema_problems(valid_record()) == []


@pytest.mark.unit
@pytest.mark.covers("#191 AC2")
@pytest.mark.parametrize("field", FIELDS)
def test_a_record_missing_one_field_fails_naming_it(field):
    record = valid_record()
    del record[field]
    problems = schema_problems(record)
    assert problems and any(field in p for p in problems)


@pytest.mark.unit
@pytest.mark.covers("#191 AC2")
def test_a_record_with_an_extra_field_fails_naming_it():
    record = valid_record() | {"spill_bytes": 0}
    problems = schema_problems(record)
    assert problems and any("spill_bytes" in p for p in problems)


@pytest.mark.unit
@pytest.mark.covers("#191 AC2")
def test_a_model_entry_missing_or_adding_a_field_fails():
    missing = valid_record()
    del missing["models"][0]["model_seconds"]
    extra = valid_record()
    extra["models"][0]["rows"] = 1
    assert any("model_seconds" in p for p in schema_problems(missing))
    assert any("rows" in p for p in schema_problems(extra))


@pytest.mark.unit
@pytest.mark.covers("#191 AC4")
def test_a_scheduled_build_writes_the_s3_record():
    assert writes_to_s3("schedule") is True


@pytest.mark.unit
@pytest.mark.covers("#191 AC4")
@pytest.mark.parametrize("event", ["workflow_dispatch", "push", "pull_request", ""])
def test_any_other_trigger_writes_the_summary_only(event):
    assert writes_to_s3(event) is False


@pytest.mark.unit
@pytest.mark.covers("#191 AC5")
@pytest.mark.parametrize(
    ("job_status", "dbt_exit", "expected"),
    [
        ("success", "0", ("success", 0)),
        ("failure", "1", ("failure", 1)),
        ("failure", "2", ("failure", 2)),
        ("cancelled", "", ("cancelled", None)),
    ],
    ids=["success", "dbt-failure", "dbt-error", "cancelled-before-dbt-returned"],
)
def test_job_status_and_dbt_exit_code_map_to_status_and_exit_code(job_status, dbt_exit, expected):
    assert job_outcome(job_status, dbt_exit) == expected


@pytest.mark.unit
@pytest.mark.covers("#191 AC5")
def test_an_unknown_job_status_is_refused():
    with pytest.raises(ValueError):
        job_outcome("skipped", "0")


# --- #205 G5: the build record no longer carries compaction ----------------------------


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_build_record_still_carrying_compaction_fails_naming_it():
    record = valid_record()
    record["compaction"] = {"n": 0, "seconds": None, "days_selected": None, "days": [],
                            "peak_rss_mib": None}
    assert any("extra field compaction" in p for p in schema_problems(record))


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_build_record_ignores_a_compaction_object_left_in_its_directory(tmp_path):
    out = tmp_path / "metrics"
    out.mkdir()
    (out / "compaction.json").write_text(json.dumps(
        {"n": 0, "seconds": 0.1, "days_selected": 0, "days": [], "peak_rss_mib": 80.0}
    ))
    record = build_record(out, "success")
    assert "compaction" not in record
    assert schema_problems(record) == []


@pytest.mark.unit
@pytest.mark.covers("#198 AC4")
@pytest.mark.covers("#205 AC5")
def test_the_191_extraction_query_reads_records_with_and_without_the_object(tmp_path):
    old = valid_record()  # as #198 wrote it, with the W13 object
    old["compaction"] = {
        "n": 0, "seconds": 0.1, "days_selected": 0, "days": [], "peak_rss_mib": 80.0,
    }
    old["run_id"] = "1"
    new = valid_record()  # as #205 writes it, without
    new["run_id"] = "2"
    for record in (old, new):
        (tmp_path / f"{record['run_id']}.json").write_text(json.dumps(record))
    rows = duckdb.sql(f"""
        select run_id, built_at, m.model_seconds
        from (select run_id, built_at, unnest(models) as m
              from read_json('{tmp_path}/*.json', format = 'auto'))
        where m.name = 'stg_player_history_capture'
        order by built_at
    """).fetchall()
    assert sorted(r[0] for r in rows) == ["1", "2"]
    assert all(r[2] == 412.5 for r in rows)
