"""Derive where each pre-2.2.0 ingest run came from, and write seeds/seed_run_origin.csv.

Manifests record their run's origin only from raw contract 2.2.0
(gisaf22/fpl-ingest#75). For every older run the authoritative record is
fpl-ingest's GitHub Actions history, and #87 decision D2 fixes the rule:

    a run is `ci` only if exactly one ingest workflow run on main, started at
    most WINDOW_SECONDS before the run_id's own start instant, logged that
    run_id. Anything else is `local`. The ported history season is
    `history_port` (#87 D3).

Timing alone is not enough. Run 20260902T163935Z-07eb06, a laptop run, began
15s after a scheduled Live run started; that run logged "ingestion skipped"
and wrote nothing. Only a log that names the run_id proves the run was CI.

Actions logs expire after 90 days, so the result is frozen as a dbt seed rather
than derived on every build, and the set of pre-2.2.0 runs is closed: the seed
never needs another row. Run once, locally, with a dev build of stg_run and
base_capture_index in .local/warehouse.duckdb and `gh` authenticated:

    uv run python scripts/derive_run_origin.py
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

INGEST_REPO = "gisaf22/fpl-ingest"
# Every ingest workflow that has ever written raw captures: "Scheduled
# Ingestion", later split into "— Live", "— Daily" and "— Pre-deadline". The
# CI and capture-index backfill workflows write no runs.
INGEST_WORKFLOW_PREFIX = "Scheduled Ingestion"
BRANCH = "main"
# Measured 2026-10-03: every matched run_id starts 9-67s after its Actions run.
WINDOW_SECONDS = 300

DATABASE = Path(".local/warehouse.duckdb")
SEED = Path("seeds/seed_run_origin.csv")
FIELDS = ("run_id", "origin_kind", "github_run_id", "workflow", "ref")


@dataclass(frozen=True)
class ActionsRun:
    id: int
    workflow: str
    head_branch: str
    started_at: str


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _run_start(run_id: str) -> datetime:
    return datetime.strptime(run_id[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def derive(
    run_ids: Iterable[str],
    *,
    history_runs: set[str],
    actions_runs: list[ActionsRun],
    log_of: Callable[[int], str],
) -> list[dict]:
    """One seed row per run, sorted by run_id."""
    ingest = [
        a
        for a in actions_runs
        if a.workflow.startswith(INGEST_WORKFLOW_PREFIX) and a.head_branch == BRANCH
    ]
    rows = []
    for run_id in sorted(set(run_ids)):
        row = dict.fromkeys(FIELDS)
        row["run_id"] = run_id
        if run_id in history_runs:
            row["origin_kind"] = "history_port"
        else:
            start = _run_start(run_id)
            named = [
                a
                for a in ingest
                if 0
                <= (start - _instant(a.started_at)).total_seconds()
                <= WINDOW_SECONDS
                and run_id in log_of(a.id)
            ]
            if len(named) == 1:
                row.update(
                    origin_kind="ci",
                    github_run_id=str(named[0].id),
                    workflow=named[0].workflow,
                    ref=f"refs/heads/{BRANCH}",
                )
            else:
                row["origin_kind"] = "local"
        rows.append(row)
    return rows


def _gh(*args: str) -> str:
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def _actions_runs() -> list[ActionsRun]:
    lines = _gh(
        "api",
        "--paginate",
        f"repos/{INGEST_REPO}/actions/runs?per_page=100",
        "--jq",
        ".workflow_runs[] | [.id, .name, .head_branch, .run_started_at] | @json",
    ).splitlines()
    return [ActionsRun(*json.loads(line)) for line in lines if line]


def _log_reader() -> Callable[[int], str]:
    cache: dict[int, str] = {}

    def log_of(actions_id: int) -> str:
        if actions_id not in cache:
            cache[actions_id] = _gh(
                "run", "view", str(actions_id), "-R", INGEST_REPO, "--log"
            )
        return cache[actions_id]

    return log_of


def _runs_to_classify() -> tuple[list[str], set[str]]:
    """Pre-2.2.0 runs in the index, and which of them are history-scoped."""
    import duckdb

    with duckdb.connect(str(DATABASE), read_only=True) as connection:
        rows = connection.execute(
            """
            select distinct index.run_id, index.scope = 'history'
            from main.base_capture_index as index
            left join main.stg_run as runs on runs.run_id = index.run_id
            where runs.origin_kind is null
            """
        ).fetchall()
    return [r for r, _ in rows], {r for r, history in rows if history}


def main() -> int:
    if not DATABASE.exists():
        print(
            f"no database at {DATABASE}: run `dbt build --select stg_run "
            "base_capture_index` against dev first"
        )
        return 1
    run_ids, history_runs = _runs_to_classify()
    rows = derive(
        run_ids,
        history_runs=history_runs,
        actions_runs=_actions_runs(),
        log_of=_log_reader(),
    )
    SEED.parent.mkdir(exist_ok=True)
    with SEED.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["origin_kind"]] = counts.get(row["origin_kind"], 0) + 1
    print(f"wrote {SEED}: {len(rows)} runs, {counts}")
    for row in rows:
        if row["origin_kind"] != "ci":
            print(f"  {row['origin_kind']}: {row['run_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
