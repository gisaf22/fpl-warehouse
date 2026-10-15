"""Record one build's passive metrics (#191): job summary always, S3 on a schedule.

Every build writes one metrics record to its job summary. A scheduled build
also writes it to s3://fpl-data-safari/metrics/build/<run_id>.json, and a
failed write fails the job (the workflow keeps the healthchecks.io ping on the
build's own outcome; see scheduled_build.yml). `model_seconds` per model is the
primary metric and `build_seconds` the trend: the W1 baseline for #78.

Called from scheduled_build.yml and ci.yml's live-tests job with `if: always()`.
Inputs come from scripts/timed_build.sh's output directory: time_v.log,
dbt_exit_code (absent if dbt never returned) and run_results.json. Each may be
missing, because the run may have stopped before dbt; the record then carries
nulls and an empty `models`, never a guess. The schema and field definitions
are in CLAUDE.md, "Build metrics".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from summarize_experiment import time_log

BUCKET = "fpl-data-safari"
PREFIX = "metrics/build"
DATABASE = os.environ.get("FPL_WAREHOUSE_DB", ".local/warehouse.duckdb")

FIELDS = (
    "run_id", "git_sha", "built_at", "trigger", "status", "exit_code",
    "build_seconds", "capture_count", "peak_rss_mib", "runner_total_mem_mib",
    "cpu_count", "models",
)
MODEL_FIELDS = ("name", "model_seconds", "status")
JOB_STATUSES = ("success", "failure", "cancelled")


def models_from_run_results(run_results: dict) -> list[dict]:
    """One entry per model node, with dbt's execution_time and status."""
    return [
        {
            "name": result["unique_id"].split(".")[-1],
            "model_seconds": result["execution_time"],
            "status": result["status"],
        }
        for result in run_results.get("results", [])
        if result["unique_id"].startswith("model.")
    ]


def job_outcome(job_status: str, dbt_exit: str) -> tuple[str, int | None]:
    """The job's result, and dbt's exit code or None if dbt never returned."""
    if job_status not in JOB_STATUSES:
        raise ValueError(f"unknown job status {job_status!r}; expected one of {JOB_STATUSES}")
    dbt_exit = dbt_exit.strip()
    return job_status, int(dbt_exit) if dbt_exit else None


def writes_to_s3(event_name: str) -> bool:
    """Only a scheduled build writes the S3 record; any other trigger, the summary only."""
    return event_name == "schedule"


def schema_problems(record: dict) -> list[str]:
    """One message per missing or extra field, in the record or a model entry."""
    problems = [f"missing field {f}" for f in FIELDS if f not in record]
    problems += [f"extra field {f}" for f in record if f not in FIELDS]
    for i, model in enumerate(record.get("models") or []):
        problems += [f"models[{i}] missing field {f}" for f in MODEL_FIELDS if f not in model]
        problems += [f"models[{i}] extra field {f}" for f in model if f not in MODEL_FIELDS]
    return problems


def capture_count() -> int | None:
    """Distinct element-summary captures staged, or None if the table was never built."""
    if not Path(DATABASE).exists():
        return None
    try:
        con = duckdb.connect(DATABASE, read_only=True)
        (count,) = con.sql(
            "select count(distinct capture_key) from stg_player_history_capture"
        ).fetchone()
        return count
    except duckdb.Error:
        return None


def runner_total_mem_mib() -> float | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return None


def build_record(out: Path, job_status: str) -> dict:
    exit_file = out / "dbt_exit_code"
    status, exit_code = job_outcome(
        job_status, exit_file.read_text() if exit_file.exists() else ""
    )
    peak_rss_gib, seconds = time_log(out / "time_v.log")
    results = out / "run_results.json"
    return {
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "git_sha": os.environ.get("GITHUB_SHA", ""),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "trigger": os.environ.get("GITHUB_EVENT_NAME", ""),
        "status": status,
        "exit_code": exit_code,
        "build_seconds": seconds,
        "capture_count": capture_count(),
        "peak_rss_mib": None if peak_rss_gib is None else round(peak_rss_gib * 1024, 1),
        "runner_total_mem_mib": runner_total_mem_mib(),
        "cpu_count": os.cpu_count(),
        "models": models_from_run_results(json.loads(results.read_text())) if results.exists() else [],
    }


def summary(record: dict, written_to: str | None) -> str:
    lines = ["### Build metrics (#191)", "", "| Field | Value |", "|---|---|"]
    lines += [f"| `{f}` | {record[f]} |" for f in FIELDS if f != "models"]
    target = f"{written_to} (this step fails if the write fails)" if written_to else "not written (not a scheduled build)"
    lines += ["", f"S3 record: {target}", ""]
    lines += ["| Model | `model_seconds` | Status |", "|---|---|---|"]
    for model in sorted(record["models"], key=lambda m: -m["model_seconds"]):
        lines.append(f"| {model['name']} | {model['model_seconds']:.1f} | {model['status']} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="timed_build.sh's directory")
    parser.add_argument("--job-status", required=True)
    parser.add_argument("--summary", type=Path, required=True, help="the job summary file")
    args = parser.parse_args()

    record = build_record(args.out, args.job_status)
    problems = schema_problems(record)
    if problems:
        for problem in problems:
            print(f"::error::build metrics record: {problem}")
        return 1

    key = f"{PREFIX}/{record['run_id']}.json" if writes_to_s3(record["trigger"]) else None
    # The summary is written first, so it survives a failed upload.
    with args.summary.open("a") as f:
        f.write(summary(record, f"s3://{BUCKET}/{key}" if key else None))
    if key:
        import boto3

        boto3.client("s3").put_object(
            Bucket=BUCKET, Key=key, Body=json.dumps(record, indent=2).encode(),
            ContentType="application/json",
        )
        print(f"wrote s3://{BUCKET}/{key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
