"""Compaction's wiring: its own scheduled workflow, out of the build (#198, #205 W16).

`scheduled_compaction.yml` runs `scripts/compaction_step.py` at 01:30 and 13:30
UTC, away from the 07:45/19:45 builds, with OIDC credentials, a 50-minute
timeout, runs that never overlap, and its own job summary and metrics record.
`scheduled_build.yml` no longer runs it. live-tests' `compaction_dry_run` input
still runs the step with a local destination, so the budget can be re-measured.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github/workflows"
SCHEDULED = WORKFLOWS / "scheduled_build.yml"
COMPACTION = WORKFLOWS / "scheduled_compaction.yml"
CI = WORKFLOWS / "ci.yml"


def load(workflow: Path) -> dict:
    return yaml.safe_load(workflow.read_text())


def steps(workflow: Path, job: str) -> list[dict]:
    return load(workflow)["jobs"][job]["steps"]


def only_job(workflow: Path) -> tuple[str, dict]:
    (item,) = load(workflow)["jobs"].items()
    return item


def index_of(steps_: list[dict], name: str) -> int:
    names = [s.get("name") for s in steps_]
    assert name in names, f"no step named {name!r}"
    return names.index(name)


def index_using(steps_: list[dict], action: str) -> int:
    (i,) = [i for i, s in enumerate(steps_) if str(s.get("uses", "")).startswith(action)]
    return i


def compaction_steps(steps_: list[dict]) -> list[int]:
    return [i for i, s in enumerate(steps_) if "compaction_step.py" in str(s.get("run", ""))]


# --- G1: the new workflow -------------------------------------------------------------


REGULAR_CRON = "30 1,13 * * *"
# #200's one-off first live run, 02:45 UTC 2026-10-16; removed by 78h.
ONE_OFF_CRON = "45 2 16 10 *"


def triggers_allowed(on: dict) -> bool:
    """Only a schedule: the regular cron, plus at most the #200 one-off entry."""
    if set(on) != {"schedule"}:
        return False
    crons = [entry.get("cron") for entry in on["schedule"]]
    return crons in ([REGULAR_CRON], [REGULAR_CRON, ONE_OFF_CRON])


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
@pytest.mark.covers("#200 AC1")
def test_compaction_runs_on_its_own_schedule_and_nothing_else_triggers_it():
    on = load(COMPACTION)[True]  # PyYAML reads `on` as True
    assert triggers_allowed(on)


@pytest.mark.unit
@pytest.mark.covers("#205 AC1")
@pytest.mark.covers("#200 AC1")
@pytest.mark.parametrize(("crons", "allowed"), [
    ([REGULAR_CRON], True),
    ([REGULAR_CRON, ONE_OFF_CRON], True),
    ([ONE_OFF_CRON], False),
    ([REGULAR_CRON, "45 2 * * *"], False),
    (["45 7,19 * * *"], False),
    ([REGULAR_CRON, ONE_OFF_CRON, "0 3 17 10 *"], False),
], ids=["regular", "regular-and-one-off", "one-off-alone", "daily-extra", "build-slot",
        "second-one-off"])
def test_any_other_compaction_schedule_fails(crons, allowed):
    on = {"schedule": [{"cron": c} for c in crons]}
    assert triggers_allowed(on) is allowed
    assert not triggers_allowed(on | {"workflow_dispatch": None})


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
def test_compaction_runs_never_overlap_and_are_never_cancelled():
    concurrency = load(COMPACTION)["concurrency"]
    assert concurrency["group"]
    assert concurrency["cancel-in-progress"] is False


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
def test_the_compaction_job_times_out_at_fifty_minutes():
    _, job = only_job(COMPACTION)
    assert job["timeout-minutes"] == 50


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
def test_the_compaction_job_assumes_the_role_by_oidc_before_compacting():
    assert load(COMPACTION)["permissions"]["id-token"] == "write"
    name, job = only_job(COMPACTION)
    s = job["steps"]
    creds = index_using(s, "aws-actions/configure-aws-credentials@")
    assert s[creds]["with"]["role-to-assume"] == "${{ vars.AWS_ROLE_ARN }}"
    (i,) = compaction_steps(s)
    assert creds < i


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
def test_the_compaction_step_writes_production_with_the_config_budget_and_its_own_summary():
    _, job = only_job(COMPACTION)
    s = job["steps"]
    (i,) = compaction_steps(s)
    run = s[i]["run"]
    assert "--dest-root s3://fpl-data-safari/compacted" in run
    assert "--days" not in run  # the budget comes from compaction.yml only
    assert '--summary "$GITHUB_STEP_SUMMARY"' in run
    assert "--out .local/metrics/compaction.json" in run


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
@pytest.mark.covers("#205 AC5")
def test_the_compaction_record_is_written_after_the_step_whatever_its_outcome():
    _, job = only_job(COMPACTION)
    s = job["steps"]
    (i,) = compaction_steps(s)
    j = index_of(s, "Record compaction metrics")
    assert i < j
    assert s[j]["if"].startswith("always()")
    assert "scripts/compaction_metrics.py" in s[j]["run"]
    assert "--out .local/metrics" in s[j]["run"]
    assert '--summary "$GITHUB_STEP_SUMMARY"' in s[j]["run"]


# --- G1: out of the build -------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
def test_the_scheduled_build_no_longer_runs_or_mentions_compaction():
    s = steps(SCHEDULED, "build")
    assert compaction_steps(s) == []
    assert not [t.get("name") for t in s if "compaction" in yaml.safe_dump(t).lower()]


@pytest.mark.integration
@pytest.mark.covers("#205 AC1")
def test_the_scheduled_build_ping_and_outcome_steps_are_unchanged():
    s = steps(SCHEDULED, "build")
    assert s[index_of(s, "Capture build outcome")] == {
        "name": "Capture build outcome",
        "id": "build_outcome",
        "if": "always()",
        "run": 'echo "status=${{ job.status }}" >> "$GITHUB_OUTPUT"',
    }
    assert s[index_of(s, "Ping healthchecks.io")] == {
        "name": "Ping healthchecks.io",
        "if": "always() && github.event_name == 'schedule'",
        "continue-on-error": True,
        "timeout-minutes": 2,
        "env": {
            "HEALTHCHECKS_PING_URL": "${{ secrets.HEALTHCHECKS_PING_URL_SCHEDULED_BUILD }}",
            "JOB_STATUS": "${{ steps.build_outcome.outputs.status }}",
        },
        "run": 'bash scripts/healthchecks_ping.sh "$JOB_STATUS"',
    }


# --- #198 D6: the dry run stays -------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#198 AC6")
@pytest.mark.covers("#205 AC1")
def test_live_tests_has_a_compaction_dry_run_input_that_runs_the_step_locally():
    inputs = load(CI)[True]["workflow_dispatch"]["inputs"]
    assert "compaction_dry_run" in inputs
    s = steps(CI, "live-tests")
    (i,) = compaction_steps(s)
    assert "inputs.compaction_dry_run" in s[i]["if"]
    assert "--days" in s[i]["run"] and "--dest-root .local/" in s[i]["run"]
    assert "--out .local/metrics/compaction.json" in s[i]["run"]


@pytest.mark.integration
@pytest.mark.covers("#205 AC5")
def test_live_tests_reports_the_dry_runs_compaction_record_in_its_summary():
    s = steps(CI, "live-tests")
    (i,) = compaction_steps(s)
    j = index_of(s, "Record compaction metrics")
    assert i < j
    assert "inputs.compaction_dry_run" in s[j]["if"]
    assert "scripts/compaction_metrics.py" in s[j]["run"]
