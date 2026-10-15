"""The scheduled compaction step: which days, how many, and what it reports (#198).

`compaction_step` reads `compaction.yml` (N and the ingest job timeout), selects
closed, uncompacted candidate days oldest first, at most N, runs the #193 writer
on them, and returns the W13 `compaction` object plus a job summary. With N = 0
it lists nothing. `compaction_dry_run` passes explicit days and a local
destination. Every test reads a synthetic tree under tmp_path; no S3.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import compaction_step as step
from compact_element_summary import DestinationRefused, manifest_path
from compaction_step import load_config, run_step, select_days
from compaction_tree import Capture, Run, build_tree, history_row

REPO = Path(__file__).resolve().parents[2]
TIMEOUT = timedelta(hours=6)
D1, D2, D3, D4 = "2026-09-20", "2026-09-21", "2026-09-22", "2026-09-23"
# Every day above is closed at this moment: D4+1 00:00 + 6h has passed.
LATE = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)


def run(day: str, suffix: str, **kwargs) -> Run:
    captures = kwargs.pop("captures", [Capture(1, [history_row(1, 0)], "x")])
    return Run(f"{day.replace('-', '')}T190000Z-{suffix}", day, captures, **kwargs)


def tree(tmp_path: Path, runs: list[Run]) -> tuple[str, str]:
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, runs)
    return str(raw), str(dest)


def compact_outright(raw: str, dest: str, day: str) -> None:
    """Gives a day its compaction manifest, as an earlier run would have."""
    path = Path(manifest_path(dest, day))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")


# --- O3: one config file -----------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_the_checked_in_config_ships_disabled_with_a_six_hour_timeout():
    config = load_config()
    assert config.max_days_per_run == 0
    assert config.ingest_job_timeout == timedelta(hours=6)


@pytest.mark.unit
@pytest.mark.covers("#198 AC1")
def test_the_close_day_rule_reads_the_timeout_from_the_config(tmp_path):
    (tmp_path / "compaction.yml").write_text(
        "max_days_per_run: 3\ningest_job_timeout_hours: 9\n"
    )
    config = load_config(tmp_path / "compaction.yml")
    assert config.max_days_per_run == 3
    assert config.ingest_job_timeout == timedelta(hours=9)


# --- D1: close-day rule ----------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC1")
def test_a_day_within_its_grace_is_not_selected(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    # D1+1 00:00 + 6h = 2026-09-21 06:00; one second before it.
    now = datetime(2026, 9, 21, 5, 59, 59, tzinfo=timezone.utc)
    assert select_days(raw, dest, now, n=5, timeout=TIMEOUT).days == []


@pytest.mark.integration
@pytest.mark.covers("#198 AC1")
def test_a_day_past_its_grace_with_every_run_finalized_is_selected(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D1, "bbbbbb", status="FAILED")])
    now = datetime(2026, 9, 21, 6, 0, 1, tzinfo=timezone.utc)
    assert select_days(raw, dest, now, n=5, timeout=TIMEOUT).days == [D1]


@pytest.mark.integration
@pytest.mark.covers("#198 AC1")
def test_a_killed_run_keeps_its_day_open_and_is_flagged(tmp_path):
    raw, dest = tree(tmp_path, [
        run(D1, "aaaaaa"),
        run(D1, "bbbbbb", status="IN_PROGRESS"),  # payload objects present
        run(D2, "cccccc"),
    ])
    selection = select_days(raw, dest, LATE, n=5, timeout=TIMEOUT)
    assert selection.days == [D2]
    assert selection.killed == [D1]
    result = run_step(raw, dest, LATE, n=5, timeout=TIMEOUT)
    assert D1 in result.summary and "IN_PROGRESS" in result.summary


# --- D2: capped catch-up ---------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_more_eligible_days_than_n_selects_the_oldest_n(tmp_path):
    raw, dest = tree(tmp_path, [run(D3, "cccccc"), run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    assert select_days(raw, dest, LATE, n=2, timeout=TIMEOUT).days == [D1, D2]


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_a_day_already_compacted_is_not_selected_again(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    compact_outright(raw, dest, D1)
    assert select_days(raw, dest, LATE, n=2, timeout=TIMEOUT).days == [D2]


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_n_zero_selects_no_days_and_lists_nothing(tmp_path, monkeypatch):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])

    def no_listing(*args, **kwargs):
        raise AssertionError("listed S3 with N = 0")

    monkeypatch.setattr(step, "list_run_manifests", no_listing)
    monkeypatch.setattr(step, "compact_days", no_listing)
    result = run_step(raw, dest, LATE, n=0, timeout=TIMEOUT)
    assert result.compaction["days_selected"] == 0
    assert result.compaction["days"] == []


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_a_day_whose_runs_wrote_no_element_summary_is_skipped_and_the_queue_advances(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa", captures=[]), run(D2, "bbbbbb")])
    selection = select_days(raw, dest, LATE, n=1, timeout=TIMEOUT)
    assert selection.days == [D2]
    assert selection.skipped_empty == [D1]
    result = run_step(raw, dest, LATE, n=1, timeout=TIMEOUT)
    assert D1 in result.summary
    assert not Path(manifest_path(dest, D1)).exists()


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_an_oldest_day_that_fails_every_run_does_not_stop_the_next_day_with_n_two(tmp_path):
    raw, dest = tree(tmp_path, [
        run(D1, "aaaaaa", index="none"),  # fails reconciliation on every run
        run(D2, "bbbbbb"),
        run(D3, "cccccc"),
    ])
    first = run_step(raw, dest, LATE, n=2, timeout=TIMEOUT)
    assert [d["capture_day"] for d in first.compaction["days"]] == [D1, D2]
    assert [d["ok"] for d in first.compaction["days"]] == [False, True]
    second = run_step(raw, dest, LATE, n=2, timeout=TIMEOUT)
    assert [d["capture_day"] for d in second.compaction["days"]] == [D1, D3]
    assert [d["ok"] for d in second.compaction["days"]] == [False, True]
    assert D1 in second.summary and "failed" in second.summary.lower()


# --- D3: failure marks the summary -----------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_a_failed_day_marks_the_step_summary_failed_and_the_step_exit_nonzero(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa", index="none")])
    result = run_step(raw, dest, LATE, n=1, timeout=TIMEOUT)
    heading = result.summary.splitlines()[0]
    assert heading.startswith("### Compaction") and "**failed**" in heading
    assert result.exit_code != 0


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_a_clean_step_summary_is_not_marked_failed(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    heading = run_step(raw, dest, LATE, n=1, timeout=TIMEOUT).summary.splitlines()[0]
    assert "failed" not in heading.lower()


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_a_clean_step_exits_zero(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    assert run_step(raw, dest, LATE, n=1, timeout=TIMEOUT).exit_code == 0


# --- D4: the W13 object ----------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC4")
def test_a_compacting_run_reports_each_day_with_its_files_and_rows(tmp_path):
    raw, dest = tree(tmp_path, [
        run(D1, "aaaaaa", captures=[Capture(1, [], "x"), Capture(2, [], "x")]),
        run(D2, "bbbbbb", index="none"),
    ])
    obj = run_step(raw, dest, LATE, n=2, timeout=TIMEOUT).compaction
    assert obj["n"] == 2
    assert obj["days_selected"] == 2
    assert obj["seconds"] >= 0
    assert obj["peak_rss_mib"] > 0
    ok, failed = obj["days"]
    assert ok == {
        "capture_day": D1, "ok": True, "reason": "", "seconds": ok["seconds"],
        "files_read": 2, "rows_written": 2,
    }
    assert failed["capture_day"] == D2 and failed["ok"] is False and failed["reason"]


@pytest.mark.integration
@pytest.mark.covers("#198 AC4")
def test_the_step_writes_its_object_where_build_metrics_reads_it(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    out = tmp_path / "metrics" / "compaction.json"
    result = run_step(raw, dest, LATE, n=1, timeout=TIMEOUT, out=out)
    assert json.loads(out.read_text()) == result.compaction


# --- D6: dry run -----------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC6")
def test_a_dry_run_compacts_the_given_days_to_a_local_destination(tmp_path, monkeypatch):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    seen = []
    real = step.compact_days

    def spy(days, raw_root, dest_root, **kwargs):
        seen.append(dest_root)
        return real(days, raw_root=raw_root, dest_root=dest_root, **kwargs)

    monkeypatch.setattr(step, "compact_days", spy)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    # Inside grace and N = 0: a dry run ignores selection and takes its days as given.
    result = run_step(raw, dest, datetime(2026, 9, 20, tzinfo=timezone.utc), n=0,
                      timeout=TIMEOUT, days=[D2])
    assert [d["capture_day"] for d in result.compaction["days"]] == [D2]
    assert seen and not any(d.startswith("s3://") for d in seen)
    assert Path(manifest_path(dest, D2)).exists()


@pytest.mark.integration
@pytest.mark.covers("#198 AC6")
def test_a_dry_run_from_a_dispatch_cannot_reach_the_production_prefix(tmp_path, monkeypatch):
    raw, _ = tree(tmp_path, [run(D1, "aaaaaa")])
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    with pytest.raises(DestinationRefused):
        run_step(raw, "s3://fpl-data-safari/compacted", LATE, n=0, timeout=TIMEOUT,
                 days=[D1])
