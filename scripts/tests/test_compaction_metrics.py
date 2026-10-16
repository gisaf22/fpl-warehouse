"""The compaction record: its pinned schema and where it goes (#205 G5).

`compaction_metrics` wraps the compaction step's W13 object (#198 D4) in one
record, `run_id`, `git_sha`, `built_at`, `status` and `compaction`. Every run
writes it to its job summary; only a scheduled run also writes it to
s3://fpl-data-safari/metrics/compaction/<run_id>.json, the gate #191 AC4 uses
for build records.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import compaction_metrics
from compaction_step import load_config
from compaction_metrics import (
    COMPACTION_DAY_FIELDS,
    COMPACTION_FIELDS,
    FIELDS,
    build_record,
    s3_key,
    schema_problems,
    writes_to_s3,
)

FIXTURE = Path(__file__).parent / "fixtures" / "compaction_metrics" / "compaction.json"


def step_output(tmp_path: Path) -> Path:
    """A metrics directory holding the real dry run's W13 object."""
    out = tmp_path / "metrics"
    out.mkdir()
    (out / "compaction.json").write_text(FIXTURE.read_text())
    return out


def valid_record(tmp_path: Path) -> dict:
    return {
        "run_id": "18000000000",
        "git_sha": "0" * 40,
        "built_at": "2026-10-16T01:30:00Z",
        "status": "success",
        "compaction": json.loads(FIXTURE.read_text()),
    }


# --- the pinned schema ----------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_the_record_fields_are_exactly_the_agreed_set():
    assert FIELDS == ("run_id", "git_sha", "built_at", "status", "compaction")
    assert COMPACTION_FIELDS == ("budget_seconds", "seconds", "days_selected", "days", "peak_rss_mib")
    assert COMPACTION_DAY_FIELDS == (
        "capture_day", "ok", "reason", "seconds", "files_read", "rows_written",
    )


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_record_built_from_the_real_dry_runs_object_passes_the_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_RUN_ID", "18000000000")
    monkeypatch.setenv("GITHUB_SHA", "0" * 40)
    record = build_record(step_output(tmp_path), "success")
    assert schema_problems(record) == []
    assert record["run_id"] == "18000000000" and record["status"] == "success"
    assert record["compaction"] == json.loads(FIXTURE.read_text())


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
@pytest.mark.parametrize("field", FIELDS)
def test_a_record_missing_one_field_fails_naming_it(tmp_path, field):
    record = valid_record(tmp_path)
    del record[field]
    assert f"missing field {field}" in schema_problems(record)


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
@pytest.mark.parametrize("field", ["trigger", "models", "build_seconds"])
def test_a_record_with_an_extra_field_fails_naming_it(tmp_path, field):
    record = valid_record(tmp_path)
    record[field] = None
    assert f"extra field {field}" in schema_problems(record)


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
@pytest.mark.parametrize("field", COMPACTION_FIELDS)
def test_a_compaction_object_missing_one_field_fails_naming_it(tmp_path, field):
    record = valid_record(tmp_path)
    del record["compaction"][field]
    assert f"compaction missing field {field}" in schema_problems(record)


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
@pytest.mark.parametrize("field", ["n", "max_days_per_run"])
def test_a_compaction_object_with_an_extra_field_fails_naming_it(tmp_path, field):
    record = valid_record(tmp_path)
    record["compaction"][field] = 0  # `n` is W13's name before the budget_seconds rename
    assert f"compaction extra field {field}" in schema_problems(record)


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
@pytest.mark.parametrize("field", COMPACTION_DAY_FIELDS)
def test_a_compaction_day_missing_one_field_fails_naming_it(tmp_path, field):
    record = valid_record(tmp_path)
    del record["compaction"]["days"][1][field]
    assert f"compaction days[1] missing field {field}" in schema_problems(record)


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_compaction_day_with_an_extra_field_fails_naming_it(tmp_path):
    record = valid_record(tmp_path)
    record["compaction"]["days"][0]["parquet_bytes"] = 1
    assert "compaction days[0] extra field parquet_bytes" in schema_problems(record)


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_run_whose_step_wrote_no_object_records_nulls_never_a_guess(tmp_path):
    out = tmp_path / "metrics"
    out.mkdir()
    record = build_record(out, "failure")
    assert record["compaction"] == {
        "budget_seconds": load_config().max_seconds_per_run, "seconds": None, "days_selected": None, "days": [], "peak_rss_mib": None,
    }
    assert schema_problems(record) == []


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_an_unknown_job_status_is_refused(tmp_path):
    with pytest.raises(ValueError):
        build_record(step_output(tmp_path), "skipped")


# --- where it goes --------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_scheduled_run_writes_the_s3_record_under_metrics_compaction():
    assert writes_to_s3("schedule") is True
    assert s3_key("18000000000") == "metrics/compaction/18000000000.json"


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
@pytest.mark.parametrize("event", ["workflow_dispatch", "push", "pull_request", ""])
def test_any_other_trigger_writes_the_summary_only(event):
    assert writes_to_s3(event) is False


def run_main(monkeypatch, out: Path, summary: Path, event: str, puts: list) -> int:
    class Client:
        def put_object(self, **kwargs):
            puts.append(kwargs)

    import boto3

    monkeypatch.setattr(boto3, "client", lambda name: Client())
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_RUN_ID", "18000000000")
    monkeypatch.setattr(sys, "argv", [
        "compaction_metrics.py", "--out", str(out), "--job-status", "success",
        "--summary", str(summary),
    ])
    return compaction_metrics.main()


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_scheduled_run_puts_the_record_and_summarises_it(tmp_path, monkeypatch):
    out = step_output(tmp_path)
    enabled = json.loads(FIXTURE.read_text()) | {"budget_seconds": 1800}
    (out / "compaction.json").write_text(json.dumps(enabled))
    puts: list = []
    summary = tmp_path / "summary.md"
    assert run_main(monkeypatch, out, summary, "schedule", puts) == 0
    (put,) = puts
    assert put["Bucket"] == "fpl-data-safari"
    assert put["Key"] == "metrics/compaction/18000000000.json"
    assert json.loads(put["Body"])["compaction"]["days_selected"] == 3
    text = summary.read_text()
    assert "2026-08-30" in text and "metrics/compaction/18000000000.json" in text


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_dispatched_run_summarises_the_record_and_puts_nothing(tmp_path, monkeypatch):
    puts: list = []
    summary = tmp_path / "summary.md"
    assert run_main(monkeypatch, step_output(tmp_path), summary, "workflow_dispatch", puts) == 0
    assert puts == []
    assert "2026-08-30" in summary.read_text()


@pytest.mark.unit
@pytest.mark.covers("#205 AC5")
def test_a_scheduled_run_with_a_zero_budget_summarises_the_record_and_puts_nothing(
    tmp_path, monkeypatch
):
    # Proposed: compaction ships disabled, and a disabled run writes nothing to
    # production, metrics/compaction/ included (#205 constraints).
    out = tmp_path / "metrics"
    out.mkdir()
    disabled = json.loads(FIXTURE.read_text()) | {"days_selected": 0, "days": []}
    (out / "compaction.json").write_text(json.dumps(disabled))
    puts: list = []
    summary = tmp_path / "summary.md"
    assert run_main(monkeypatch, out, summary, "schedule", puts) == 0
    assert puts == []
    assert "not written" in summary.read_text()
