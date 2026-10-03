"""The run-origin derivation marks a run `ci` only when one ingest log on main names it.

`derive` is the pure core of scripts/derive_run_origin.py: given the runs to
classify, the ingest repo's Actions runs and a way to read each one's log, it
returns one seed row per run. These tests feed it fakes; nothing calls GitHub.
"""

from __future__ import annotations

import pytest

from derive_run_origin import ActionsRun, derive

LIVE = "Scheduled Ingestion — Live"
DAILY = "Scheduled Ingestion — Daily"


def actions(run_id: int, name: str, started: str, branch: str = "main") -> ActionsRun:
    return ActionsRun(id=run_id, workflow=name, head_branch=branch, started_at=started)


def logs(**by_id: str):
    """A log reader over {"<actions id>": text}; an unknown id has an empty log."""
    return lambda actions_id: by_id.get(str(actions_id), "")


def only(rows: list[dict]) -> dict:
    assert len(rows) == 1
    return rows[0]


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
def test_a_run_named_in_exactly_one_main_ingest_log_is_ci_with_that_run():
    run = "20260831T191154Z-d94896"
    rows = derive(
        [run],
        history_runs=set(),
        actions_runs=[actions(1, DAILY, "2026-08-31T19:11:44Z")],
        log_of=logs(**{"1": f"Captured fixtures -> fpl/fixtures/2026-08-31/{run}/payload.json"}),
    )

    assert only(rows) == {
        "run_id": run,
        "origin_kind": "ci",
        "github_run_id": "1",
        "workflow": DAILY,
        "ref": "refs/heads/main",
    }


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
def test_overlapping_workflows_resolve_to_the_one_whose_log_names_the_run():
    run = "20260831T191154Z-d94896"
    rows = derive(
        [run],
        history_runs=set(),
        actions_runs=[
            actions(1, DAILY, "2026-08-31T19:11:22Z"),
            actions(2, LIVE, "2026-08-31T19:10:26Z"),
        ],
        log_of=logs(**{"1": f"... {run} ...", "2": "... 20260831T191101Z-43d320 ..."}),
    )

    assert only(rows)["github_run_id"] == "1"


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
def test_a_run_coinciding_with_a_run_that_skipped_ingestion_is_local():
    # 07eb06: began 15s after a Live run that logged only "ingestion skipped".
    run = "20260902T163935Z-07eb06"
    rows = derive(
        [run],
        history_runs=set(),
        actions_runs=[actions(33656247218, LIVE, "2026-09-02T16:39:20Z")],
        log_of=logs(**{"33656247218": "No match currently live; ingestion skipped."}),
    )

    assert only(rows) == {
        "run_id": run,
        "origin_kind": "local",
        "github_run_id": None,
        "workflow": None,
        "ref": None,
    }


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
@pytest.mark.parametrize(
    "candidate",
    [
        actions(1, DAILY, "2026-08-31T19:11:44Z", branch="feat/x"),
        actions(1, "CI", "2026-08-31T19:11:44Z"),
        actions(1, DAILY, "2026-08-31T19:05:00Z"),  # started over 300s before
        actions(1, DAILY, "2026-08-31T19:12:00Z"),  # started after the run
    ],
    ids=["other branch", "not an ingest workflow", "too early", "after the run"],
)
def test_a_log_that_names_the_run_does_not_count_outside_main_ingest_and_the_window(
    candidate,
):
    run = "20260831T191154Z-d94896"
    rows = derive(
        [run], history_runs=set(), actions_runs=[candidate], log_of=logs(**{"1": run})
    )

    assert only(rows)["origin_kind"] == "local"


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
def test_a_run_named_in_two_logs_is_not_ci():
    run = "20260831T191154Z-d94896"
    rows = derive(
        [run],
        history_runs=set(),
        actions_runs=[
            actions(1, DAILY, "2026-08-31T19:11:22Z"),
            actions(2, LIVE, "2026-08-31T19:10:26Z"),
        ],
        log_of=logs(**{"1": run, "2": run}),
    )

    assert only(rows)["origin_kind"] == "local"


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
def test_the_history_port_is_history_port_without_reading_any_log():
    run = "20260526T034626Z-2a6b73"

    def no_logs(_):
        raise AssertionError("the history port must not be matched against logs")

    rows = derive([run], history_runs={run}, actions_runs=[], log_of=no_logs)

    assert only(rows) == {
        "run_id": run,
        "origin_kind": "history_port",
        "github_run_id": None,
        "workflow": None,
        "ref": None,
    }


@pytest.mark.unit
@pytest.mark.covers("#96 AC1")
def test_rows_come_back_sorted_by_run_id_one_per_run():
    runs = ["20260902T163935Z-07eb06", "20260526T034626Z-2a6b73"]
    rows = derive(
        runs,
        history_runs={"20260526T034626Z-2a6b73"},
        actions_runs=[],
        log_of=logs(),
    )

    assert [r["run_id"] for r in rows] == sorted(runs)
