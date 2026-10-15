"""The scheduled build's ping reports the build, and timing keeps dbt's exit code (#191 AC7).

The metrics step runs after the publish and can fail the job when its S3 write
fails. The healthchecks.io ping must still report what the build and publish
did, so the workflow captures `job.status` in a step before the metrics step
and the ping reads that capture, not `job.status`.

`scripts/timed_build.sh` wraps `dbt build` in `/usr/bin/time -v` for peak RSS
and wall time. It must exit with the wrapped command's own code and record it,
so a failed build still fails the step and the metrics record its exit code.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/scheduled_build.yml"
TIMED_BUILD = REPO / "scripts/timed_build.sh"


def steps() -> list[dict]:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["build"]["steps"]


def index(name: str) -> int:
    names = [s.get("name") for s in steps()]
    assert name in names, f"no step named {name!r}"
    return names.index(name)


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
def test_the_build_outcome_is_captured_after_the_publish_and_before_the_metrics_step():
    captured = steps()[index("Capture build outcome")]
    assert captured.get("id") == "build_outcome"
    assert "always()" in captured.get("if", "")
    assert "job.status" in captured["run"]
    assert (
        index("Publish served tables to S3")
        < index("Capture build outcome")
        < index("Record build metrics")
        < index("Ping healthchecks.io")
    )


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
def test_the_ping_reports_the_captured_outcome_not_the_job_status():
    ping = steps()[index("Ping healthchecks.io")]
    assert ping["env"]["JOB_STATUS"] == "${{ steps.build_outcome.outputs.status }}"
    assert "job.status" not in yaml.safe_dump(ping)


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
def test_the_metrics_step_runs_always_and_is_allowed_to_fail_the_job():
    metrics = steps()[index("Record build metrics")]
    assert "always()" in metrics.get("if", "")
    assert not metrics.get("continue-on-error", False)
    assert "steps.build_outcome.outputs.status" in yaml.safe_dump(metrics)


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
def test_the_scheduled_dbt_build_runs_through_the_timing_wrapper():
    build = steps()[index("Build and test against live S3")]
    assert "scripts/timed_build.sh" in build["run"]
    assert "dbt build" in build["run"]


def run_timed(tmp_path: Path, code: int, time_bin: str | None) -> tuple[int, Path]:
    out = tmp_path / "metrics"
    env = {"PATH": "/usr/bin:/bin"}
    if time_bin:
        env["TIME_BIN"] = time_bin
    result = subprocess.run(
        ["bash", str(TIMED_BUILD), str(out), "sh", "-c", f"exit {code}"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    return result.returncode, out


def stub_time(tmp_path: Path) -> str:
    """Stands in for GNU time where it is absent: writes the log, runs the rest."""
    stub = tmp_path / "time"
    stub.write_text('#!/bin/sh\nshift; log=$2; shift 2\necho stub > "$log"\nexec "$@"\n')
    stub.chmod(0o755)
    return str(stub)


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
@pytest.mark.parametrize("code", [0, 1, 2])
def test_the_timing_wrapper_exits_with_and_records_the_wrapped_exit_code(tmp_path, code):
    returncode, out = run_timed(tmp_path, code, stub_time(tmp_path))
    assert returncode == code
    assert (out / "dbt_exit_code").read_text().strip() == str(code)


GNU_TIME = Path("/usr/bin/time")
has_gnu_time = GNU_TIME.exists() and subprocess.run(
    [str(GNU_TIME), "-v", "true"], capture_output=True
).returncode == 0


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
@pytest.mark.skipif(not has_gnu_time, reason="GNU time is on the CI runner, not macOS")
@pytest.mark.parametrize("code", [0, 1, 2])
def test_gnu_time_preserves_the_wrapped_exit_code_and_reports_peak_rss(tmp_path, code):
    returncode, out = run_timed(tmp_path, code, None)
    assert returncode == code
    assert (out / "dbt_exit_code").read_text().strip() == str(code)
    assert "Maximum resident set size" in (out / "time_v.log").read_text()


@pytest.mark.integration
@pytest.mark.covers("#191 AC7")
def test_the_wrapper_does_not_keep_a_previous_commands_run_results(tmp_path):
    (tmp_path / "target").mkdir()
    (tmp_path / "target/run_results.json").write_text('{"stale": true}')
    _, out = run_timed(tmp_path, 0, stub_time(tmp_path))
    assert not (out / "run_results.json").exists()
