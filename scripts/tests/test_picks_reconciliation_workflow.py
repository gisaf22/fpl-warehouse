"""The picks reconciliation warns visibly in the scheduled build (#216 D13).

The reconciliation test (tests/int_test_manager_gameweek_points_reconcile_warns.sql)
warns rather than errors, so its rows reach only the dbt log. As for missed
pre-deadline captures (#111, the #80 pattern), a step after the build puts each
difference in the job summary and raises an annotation. It reads the same
model as the test, runs whatever the build's outcome, and can never block the
publish.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/scheduled_build.yml"
STEP = "Report picks reconciliation differences"


def steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["build"]["steps"]


def step_named(name: str) -> tuple[int, dict]:
    for position, step in enumerate(steps()):
        if step.get("name") == name:
            return position, step
    raise AssertionError(f"no step named {name!r} in {WORKFLOW.name}")


@pytest.mark.unit
@pytest.mark.covers("#216 AC13")
def test_differences_go_to_the_job_summary_and_an_annotation():
    _, step = step_named(STEP)
    run = step["run"]

    assert "int_manager_gameweek_points" in run
    assert "GITHUB_STEP_SUMMARY" in run
    assert "::warning::" in run


@pytest.mark.unit
@pytest.mark.covers("#216 AC13")
def test_the_report_runs_after_the_build_and_never_blocks_the_publish():
    position, step = step_named(STEP)
    build, _ = step_named("Build and test against live S3")
    publish, _ = step_named("Publish served tables to S3")

    assert build < position < publish
    assert step.get("if") == "always()"
    assert step.get("continue-on-error") is True
