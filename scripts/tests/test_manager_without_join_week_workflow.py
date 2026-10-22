"""A panel manager with no join week warns visibly in the scheduled build (#216 N1).

The warn test (tests/int_test_manager_panel_without_join_week_warns.sql) names
each such manager only in the dbt log. As for the picks reconciliation (D13,
the #80 pattern), a step after the build puts each one in the job summary and
raises an annotation. It runs whatever the build's outcome and can never block
the publish.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/scheduled_build.yml"
STEP = "Report panel managers without a join week"


def step_named(name: str) -> tuple[int, dict]:
    steps = yaml.safe_load(WORKFLOW.read_text())["jobs"]["build"]["steps"]
    for position, step in enumerate(steps):
        if step.get("name") == name:
            return position, step
    raise AssertionError(f"no step named {name!r} in {WORKFLOW.name}")


@pytest.mark.unit
@pytest.mark.covers("#216 AC1")
def test_managers_without_a_join_week_go_to_the_job_summary_and_an_annotation():
    _, step = step_named(STEP)
    run = step["run"]

    assert "dim_manager_panel" in run
    assert "first_active_gw is null" in run
    assert "GITHUB_STEP_SUMMARY" in run
    assert "::warning::" in run


@pytest.mark.unit
@pytest.mark.covers("#216 AC1")
def test_the_report_runs_after_the_build_and_never_blocks_the_publish():
    position, step = step_named(STEP)
    build, _ = step_named("Build and test against live S3")
    publish, _ = step_named("Publish served tables to S3")

    assert build < position < publish
    assert step.get("if") == "always()"
    assert step.get("continue-on-error") is True
