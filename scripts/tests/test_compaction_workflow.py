"""Compaction's wiring: before dbt, unable to change the build outcome (#198 D3, D6).

The scheduled build runs `scripts/compaction_step.py` before `dbt build`, with
continue-on-error, so a compaction failure marks its own step and summary but
never the job, the publish or the healthchecks.io ping (#191 AC7's pattern).
live-tests' `compaction_dry_run` input runs the step with a local destination.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SCHEDULED = REPO / ".github/workflows/scheduled_build.yml"
CI = REPO / ".github/workflows/ci.yml"


def steps(workflow: Path, job: str) -> list[dict]:
    return yaml.safe_load(workflow.read_text())["jobs"][job]["steps"]


def index_of(steps_: list[dict], name: str) -> int:
    names = [s.get("name") for s in steps_]
    assert name in names, f"no step named {name!r}"
    return names.index(name)


def compaction_steps(steps_: list[dict]) -> list[int]:
    return [i for i, s in enumerate(steps_) if "compaction_step.py" in str(s.get("run", ""))]


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_the_scheduled_compaction_step_runs_before_dbt_and_cannot_fail_the_job():
    s = steps(SCHEDULED, "build")
    (i,) = compaction_steps(s)
    assert s[i].get("continue-on-error") is True
    assert i < index_of(s, "Build and test against live S3")
    assert i > index_of(s, "Configure AWS credentials (OIDC)")


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_nothing_downstream_reads_the_compaction_steps_outcome_except_its_summary():
    s = steps(SCHEDULED, "build")
    (i,) = compaction_steps(s)
    step_id = s[i].get("id")
    assert step_id, "the compaction step needs an id for its failure summary"
    readers = [
        t.get("name") for t in s
        if f"steps.{step_id}." in yaml.safe_dump(t)
    ]
    assert readers == ["Mark compaction failed in the summary"]
    marker = s[index_of(s, "Mark compaction failed in the summary")]
    assert f"steps.{step_id}.outcome == 'failure'" in marker["if"]
    assert marker.get("continue-on-error") is True
    for name in ("Build and test against live S3", "Publish served tables to S3",
                 "Capture build outcome", "Ping healthchecks.io"):
        assert "compaction" not in yaml.safe_dump(s[index_of(s, name)]).lower()


@pytest.mark.integration
@pytest.mark.covers("#198 AC3")
def test_the_scheduled_step_writes_to_the_production_prefix_with_the_config_n():
    s = steps(SCHEDULED, "build")
    (i,) = compaction_steps(s)
    run = s[i]["run"]
    assert "--dest-root s3://fpl-data-safari/compacted" in run
    assert "--days" not in run and "--n" not in run  # N comes from compaction.yml only
    assert "--out .local/metrics/compaction.json" in run


@pytest.mark.integration
@pytest.mark.covers("#198 AC6")
def test_live_tests_has_a_compaction_dry_run_input_that_runs_the_step_locally():
    workflow = yaml.safe_load(CI.read_text())
    inputs = workflow[True]["workflow_dispatch"]["inputs"]  # PyYAML reads `on` as True
    assert "compaction_dry_run" in inputs
    s = steps(CI, "live-tests")
    (i,) = compaction_steps(s)
    assert "inputs.compaction_dry_run" in s[i]["if"]
    assert "--days" in s[i]["run"] and "--dest-root .local/" in s[i]["run"]
    assert "--out .local/metrics/compaction.json" in s[i]["run"]
    assert i < index_of(s, "Record build metrics")
