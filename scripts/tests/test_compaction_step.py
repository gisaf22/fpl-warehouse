"""The scheduled compaction step: which days, how many, and what it reports (#198, #205).

`compaction_step` reads `compaction.yml` (the time budget and the ingest job
timeout), selects closed, uncompacted candidate days oldest first, runs the #193
writer on them until the budget is spent (W16), and returns the W13 `compaction`
object plus a job summary. With a budget of 0 it makes no S3 call. `compaction_dry_run` passes explicit days and a local
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
HOUR = 3600
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
@pytest.mark.covers("#205 AC3")
def test_the_checked_in_config_ships_a_1800_second_budget_with_a_six_hour_timeout():
    config = load_config()
    assert config.max_seconds_per_run == 1800
    assert config.ingest_job_timeout == timedelta(hours=6)


@pytest.mark.unit
@pytest.mark.covers("#205 AC3")
def test_the_checked_in_config_no_longer_carries_a_day_count():
    import yaml

    keys = set(yaml.safe_load((REPO / "compaction.yml").read_text()))
    assert keys == {"max_seconds_per_run", "ingest_job_timeout_hours"}


@pytest.mark.unit
@pytest.mark.covers("#205 AC3")
def test_a_config_without_a_budget_is_refused_not_read_as_off(tmp_path):
    (tmp_path / "compaction.yml").write_text(
        "max_days_per_run: 3\ningest_job_timeout_hours: 6\n"
    )
    with pytest.raises(KeyError, match="max_seconds_per_run"):
        load_config(tmp_path / "compaction.yml")


@pytest.mark.unit
@pytest.mark.covers("#198 AC1")
@pytest.mark.covers("#205 AC3")
def test_the_close_day_rule_reads_the_timeout_from_the_config(tmp_path):
    (tmp_path / "compaction.yml").write_text(
        "max_seconds_per_run: 1800\ningest_job_timeout_hours: 9\n"
    )
    config = load_config(tmp_path / "compaction.yml")
    assert config.max_seconds_per_run == 1800
    assert config.ingest_job_timeout == timedelta(hours=9)


# --- D1: close-day rule ----------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC1")
def test_a_day_within_its_grace_is_not_selected(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    # D1+1 00:00 + 6h = 2026-09-21 06:00; one second before it.
    now = datetime(2026, 9, 21, 5, 59, 59, tzinfo=timezone.utc)
    assert select_days(raw, dest, now, timeout=TIMEOUT).days == []


@pytest.mark.integration
@pytest.mark.covers("#198 AC1")
def test_a_day_past_its_grace_with_every_run_finalized_is_selected(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D1, "bbbbbb", status="FAILED")])
    now = datetime(2026, 9, 21, 6, 0, 1, tzinfo=timezone.utc)
    assert select_days(raw, dest, now, timeout=TIMEOUT).days == [D1]


@pytest.mark.integration
@pytest.mark.covers("#198 AC1")
def test_a_killed_run_keeps_its_day_open_and_is_flagged(tmp_path):
    raw, dest = tree(tmp_path, [
        run(D1, "aaaaaa"),
        run(D1, "bbbbbb", status="IN_PROGRESS"),  # payload objects present
        run(D2, "cccccc"),
    ])
    selection = select_days(raw, dest, LATE, timeout=TIMEOUT)
    assert selection.days == [D2]
    assert selection.killed == [D1]
    result = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT)
    assert D1 in result.summary and "IN_PROGRESS" in result.summary


# --- D2: catch-up, oldest first --------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
@pytest.mark.covers("#205 AC2")
def test_every_eligible_day_is_queued_oldest_first(tmp_path):
    raw, dest = tree(tmp_path, [run(D3, "cccccc"), run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    assert select_days(raw, dest, LATE, timeout=TIMEOUT).days == [D1, D2, D3]


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_a_day_already_compacted_is_not_selected_again(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    compact_outright(raw, dest, D1)
    assert select_days(raw, dest, LATE, timeout=TIMEOUT).days == [D2]


@pytest.mark.unit
@pytest.mark.covers("#205 AC2")
def test_a_zero_budget_selects_no_days_and_makes_no_s3_call(monkeypatch):
    def no_call(*args, **kwargs):
        raise AssertionError("touched S3 with a budget of 0")

    for name in ("_connect", "list_run_manifests", "list_payloads", "compact_days"):
        monkeypatch.setattr(step, name, no_call)
    result = run_step("s3://fpl-data-safari/raw", "s3://fpl-data-safari/compacted", LATE,
                      budget_seconds=0, timeout=TIMEOUT, event_name="schedule")
    assert result.compaction["days_selected"] == 0
    assert result.compaction["days"] == []
    assert result.exit_code == 0


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_a_day_whose_runs_wrote_no_element_summary_is_skipped_and_the_queue_advances(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa", captures=[]), run(D2, "bbbbbb")])
    selection = select_days(raw, dest, LATE, timeout=TIMEOUT)
    assert selection.days == [D2]
    assert selection.skipped_empty == [D1]
    result = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT)
    assert D1 in result.summary
    assert not Path(manifest_path(dest, D1)).exists()


@pytest.mark.unit
@pytest.mark.covers("#198 AC2")
def test_an_oldest_day_that_fails_every_run_does_not_stop_the_days_after_it(tmp_path):
    raw, dest = tree(tmp_path, [
        run(D1, "aaaaaa", index="none"),  # fails reconciliation on every run
        run(D2, "bbbbbb"),
        run(D3, "cccccc"),
    ])
    first = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT)
    assert [d["capture_day"] for d in first.compaction["days"]] == [D1, D2, D3]
    assert [d["ok"] for d in first.compaction["days"]] == [False, True, True]
    second = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT)
    assert [d["capture_day"] for d in second.compaction["days"]] == [D1]
    assert D1 in second.summary and "failed" in second.summary.lower()


# --- #205 G2: the time budget (W16) -----------------------------------------------------


class Clock:
    """A monotonic clock each compacted day advances by its own cost."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def costed(monkeypatch, clock: Clock, cost: dict[str, float]) -> list[str]:
    """Makes compacting each day cost `cost[day]` seconds; returns the days started."""
    started = []
    real = step.compact_days

    def spy(days, **kwargs):
        started.extend(days)
        result = real(days, **kwargs)
        clock.now += sum(cost[d] for d in days)
        return result

    monkeypatch.setattr(step, "compact_days", spy)
    return started


@pytest.mark.integration
@pytest.mark.covers("#205 AC2")
def test_a_budget_spent_by_the_first_day_starts_no_second_day(tmp_path, monkeypatch):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb"), run(D3, "cccccc")])
    clock = Clock()
    started = costed(monkeypatch, clock, {D1: 60, D2: 60, D3: 60})
    result = run_step(raw, dest, LATE, budget_seconds=60, timeout=TIMEOUT, clock=clock)
    assert started == [D1]
    assert [d["capture_day"] for d in result.compaction["days"]] == [D1]
    assert Path(manifest_path(dest, D1)).exists()
    assert not Path(manifest_path(dest, D2)).exists()


@pytest.mark.integration
@pytest.mark.covers("#205 AC2")
def test_days_keep_starting_oldest_first_while_the_budget_lasts(tmp_path, monkeypatch):
    raw, dest = tree(tmp_path, [run(D3, "cccccc"), run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    clock = Clock()
    started = costed(monkeypatch, clock, {D1: 40, D2: 40, D3: 40})
    # 0 < 100 starts D1; 40 < 100 starts D2; 80 < 100 starts D3.
    run_step(raw, dest, LATE, budget_seconds=100, timeout=TIMEOUT, clock=clock)
    assert started == [D1, D2, D3]


@pytest.mark.integration
@pytest.mark.covers("#205 AC2")
def test_a_heavy_first_day_runs_to_completion_past_the_budget(tmp_path, monkeypatch):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    clock = Clock()
    started = costed(monkeypatch, clock, {D1: 1084.4, D2: 131.6})
    result = run_step(raw, dest, LATE, budget_seconds=10, timeout=TIMEOUT, clock=clock)
    assert started == [D1]
    (day,) = result.compaction["days"]
    assert day["capture_day"] == D1 and day["ok"] is True
    assert Path(manifest_path(dest, D1)).exists()



# --- D3: failure marks the summary -----------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_a_failed_day_marks_the_step_summary_failed_and_the_step_exit_nonzero(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa", index="none")])
    result = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT)
    heading = result.summary.splitlines()[0]
    assert heading.startswith("### Compaction") and "**failed**" in heading
    assert result.exit_code != 0


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_a_clean_step_summary_is_not_marked_failed(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    heading = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT).summary.splitlines()[0]
    assert "failed" not in heading.lower()


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_a_clean_step_exits_zero(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    assert run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT).exit_code == 0


# --- D4: the W13 object ----------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC4")
def test_a_compacting_run_reports_each_day_with_its_files_and_rows(tmp_path):
    raw, dest = tree(tmp_path, [
        run(D1, "aaaaaa", captures=[Capture(1, [], "x"), Capture(2, [], "x")]),
        run(D2, "bbbbbb", index="none"),
    ])
    obj = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT).compaction
    assert obj["budget_seconds"] == HOUR  # W13 as amended by #205
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
def test_the_step_writes_its_object_where_the_compaction_record_reads_it(tmp_path):
    raw, dest = tree(tmp_path, [run(D1, "aaaaaa")])
    out = tmp_path / "metrics" / "compaction.json"
    result = run_step(raw, dest, LATE, budget_seconds=HOUR, timeout=TIMEOUT, out=out)
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
    result = run_step(raw, dest, datetime(2026, 9, 20, tzinfo=timezone.utc), budget_seconds=0,
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
        run_step(raw, "s3://fpl-data-safari/compacted", LATE, budget_seconds=0, timeout=TIMEOUT,
                 days=[D1])


# --- #203 F4: per-day progress ------------------------------------------------------

PROGRESS = r"^compaction: day=(\S+) files=(\d+) seconds=\d+\.\d ok=(True|False)$"


@pytest.mark.integration
@pytest.mark.covers("#203 AC4")
def test_each_compacted_day_prints_a_progress_line(tmp_path, capsys):
    import re

    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb", index="none")])
    run_step(raw, dest, LATE, budget_seconds=0, timeout=TIMEOUT, days=[D1, D2])
    lines = [re.match(PROGRESS, l) for l in capsys.readouterr().out.splitlines()]
    assert [m.groups() for m in lines if m] == [(D1, "1", "True"), (D2, "1", "False")]


@pytest.mark.integration
@pytest.mark.covers("#203 AC4")
def test_a_run_killed_mid_day_has_already_printed_the_days_before_it(
    tmp_path, capsys, monkeypatch
):
    import re

    raw, dest = tree(tmp_path, [run(D1, "aaaaaa"), run(D2, "bbbbbb")])
    real = step.compact_days

    def killed_on_d2(days, **kwargs):
        if days == [D2]:
            raise RuntimeError("killed")
        return real(days, **kwargs)

    monkeypatch.setattr(step, "compact_days", killed_on_d2)
    with pytest.raises(RuntimeError):
        run_step(raw, dest, LATE, budget_seconds=0, timeout=TIMEOUT, days=[D1, D2])
    out = capsys.readouterr().out.splitlines()
    assert [re.match(PROGRESS, l).group(1) for l in out if re.match(PROGRESS, l)] == [D1]


# --- #203 F6: selection reads the index's real shape ---------------------------------

REAL = Path(__file__).resolve().parent / "fixtures" / "compaction_real" / "raw"
AFTER_REAL = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


@pytest.mark.integration
@pytest.mark.covers("#203 AC6")
def test_a_real_contract_1_0_0_day_is_selected_as_a_candidate(tmp_path):
    selection = select_days(str(REAL), str(tmp_path / "compacted"), AFTER_REAL,
                            timeout=TIMEOUT)
    assert "2026-08-29" in selection.days
    assert "2026-08-29" not in selection.skipped_empty


@pytest.mark.integration
@pytest.mark.covers("#203 AC6")
def test_a_real_captures_list_alone_makes_its_day_a_candidate(tmp_path):
    raw = tmp_path / "raw"
    path = "fpl/_manifests/2026-10-13/20261013T072947Z-8f09c4/manifest.json"
    manifest = json.loads((REAL / path).read_text())
    del manifest["objects"]
    (raw / path).parent.mkdir(parents=True)
    (raw / path).write_text(json.dumps(manifest))
    selection = select_days(str(raw), str(tmp_path / "compacted"), AFTER_REAL,
                            timeout=TIMEOUT)
    assert selection.days == ["2026-10-13"]
