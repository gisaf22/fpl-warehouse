"""Record one compaction run (#205 G5): job summary always, S3 on a schedule.

Wraps the compaction step's W13 object (#198 D4, `budget_seconds` since #205)
in one record: `run_id`, `git_sha`, `built_at`, `status` and `compaction`.
Every run writes it to its job summary. A scheduled run with a budget above 0
also writes it to s3://fpl-data-safari/metrics/compaction/<run_id>.json, and a
failed write fails the job: the gate build_metrics.py uses for build records
(#191 AC4), plus "disabled writes nothing" (#205).

Called with `if: always()` from scheduled_compaction.yml, and from ci.yml's
live-tests job after a compaction_dry_run. It reads `compaction.json` from the
step's `--out` directory; if the step never wrote one, the object carries
nulls and no days, never a guess. The schema is in docs/compacted.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from build_metrics import job_outcome, writes_to_s3
from compaction_step import load_config

BUCKET = "fpl-data-safari"
PREFIX = "metrics/compaction"

FIELDS = ("run_id", "git_sha", "built_at", "status", "compaction")
# The W13 object (#198 D4); `n` became `budget_seconds` in #205.
COMPACTION_FIELDS = ("budget_seconds", "seconds", "days_selected", "days", "peak_rss_mib")
COMPACTION_DAY_FIELDS = (
    "capture_day", "ok", "reason", "seconds", "files_read", "rows_written",
)


def s3_key(run_id: str) -> str:
    return f"{PREFIX}/{run_id}.json"


def schema_problems(record: dict) -> list[str]:
    """One message per missing or extra field, in the record, its object or a day."""
    problems = [f"missing field {f}" for f in FIELDS if f not in record]
    problems += [f"extra field {f}" for f in record if f not in FIELDS]
    compaction = record.get("compaction")
    if isinstance(compaction, dict):
        problems += [f"compaction missing field {f}" for f in COMPACTION_FIELDS if f not in compaction]
        problems += [f"compaction extra field {f}" for f in compaction if f not in COMPACTION_FIELDS]
        for i, day in enumerate(compaction.get("days") or []):
            problems += [
                f"compaction days[{i}] missing field {f}" for f in COMPACTION_DAY_FIELDS if f not in day
            ]
            problems += [
                f"compaction days[{i}] extra field {f}" for f in day if f not in COMPACTION_DAY_FIELDS
            ]
    return problems


def compaction_object(out: Path) -> dict:
    """The step's object, or nulls if the step never wrote one (#198 O4)."""
    path = out / "compaction.json"
    if path.exists():
        return json.loads(path.read_text())
    return {
        "budget_seconds": load_config().max_seconds_per_run,
        "seconds": None,
        "days_selected": None,
        "days": [],
        "peak_rss_mib": None,
    }


def build_record(out: Path, job_status: str) -> dict:
    status, _ = job_outcome(job_status, "")
    return {
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "git_sha": os.environ.get("GITHUB_SHA", ""),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "compaction": compaction_object(out),
    }


def summary(record: dict, written_to: str | None) -> str:
    lines = ["### Compaction metrics (#205)", "", "| Field | Value |", "|---|---|"]
    lines += [f"| `{f}` | {record[f]} |" for f in FIELDS if f != "compaction"]
    compaction = record["compaction"]
    lines += [f"| `{f}` | {compaction[f]} |" for f in COMPACTION_FIELDS if f != "days"]
    for day in compaction["days"]:
        lines.append(
            f"| `{day['capture_day']}` | {'ok' if day['ok'] else 'failed: ' + day['reason']}, "
            f"{day['files_read']} files, {day['rows_written']} rows, {day['seconds']}s |"
        )
    target = f"{written_to} (this step fails if the write fails)" if written_to else "not written (not a scheduled run, or the budget is 0)"
    lines += ["", f"S3 record: {target}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True, help="the step's --out directory")
    parser.add_argument("--job-status", required=True)
    parser.add_argument("--summary", type=Path, required=True, help="the job summary file")
    args = parser.parse_args()

    record = build_record(args.out, args.job_status)
    problems = schema_problems(record)
    if problems:
        for problem in problems:
            print(f"::error::compaction metrics record: {problem}")
        return 1

    event = os.environ.get("GITHUB_EVENT_NAME", "")
    # A disabled run (budget 0) writes nothing to production, its record included.
    enabled = (record["compaction"]["budget_seconds"] or 0) > 0
    key = s3_key(record["run_id"]) if writes_to_s3(event) and enabled else None
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
