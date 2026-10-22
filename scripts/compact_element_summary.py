"""Compact element-summary capture days into one parquet per day (#193).

Given an explicit list of capture days, each day D's payload files under
`<raw_root>/fpl/element-summary/*/<D>/*/payload.json` become
`<dest_root>/fpl/element-summary/date=<D>/part.parquet`, then
`<dest_root>/fpl/element-summary/_manifest/date=<D>.json` (#78 W9). Which days to
compact, and running it in a workflow, are #198's.

The parquet is `select * from read_json(<D's files>, union_by_name = true,
filename = true)`, unchanged (#78 W8): `filename` keeps each file's full original
URI, and D is in the path only. The schema is whatever that read returns; it is
an internal contract, documented in docs/compacted.md.

Per day, in order (#78 W11):

1. Capture day: every file's run manifest must state extraction_date = D.
2. Write the parquet. Recompacting a day overwrites it; nothing is ever deleted.
3. Reconcile: listed payload files = parquet rows = distinct filename, and the
   listed files = the index keys of D's runs, sha256 matching. A run's index is
   its finalized manifest's captures[] when present, otherwise its backfill
   catalog entry: base_capture_index's precedence, read from raw because this
   runs outside dbt.
4. Write the compaction manifest, last, so a manifest never names a missing or
   unreconciled parquet.

A failed check fails that day only: no manifest is written, its parquet is
left unreferenced and overwritten next time, and the other days go on. An
unexpected exception propagates; it stands for a killed job.

A destination under s3://fpl-data-safari/compacted/ is written only by a
scheduled run (GITHUB_EVENT_NAME == schedule). #198 reuses this gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

PROD_PREFIX = "s3://fpl-data-safari/compacted/"
ENDPOINT = "element-summary"
# Ingest records the endpoint as element-summary/<fpl_id>, so a capture is
# element-summary by its key, never by endpoint equality (#203).
KEY_PREFIX = f"raw/fpl/{ENDPOINT}/"
# Concurrent GETs for sha256 verification; DuckDB's read_blob was serial (#203 F1).
SHA_WORKERS = 32
# Both run the writer: this module directly, and the compaction step (#198).
WRITER_SCRIPTS = ("compact_element_summary", "compaction_step", "compact_entry_picks")
MANIFEST_FIELDS = (
    "capture_day",
    "payload_files",
    "parquet_rows",
    "distinct_filenames",
    "run_ids",
    "compacted_at",
    "git_sha",
)


class DestinationRefused(Exception):
    """A write to the production prefix from anything but a scheduled run."""


@dataclass
class DayResult:
    ok: bool
    reason: str = ""
    files_read: int = 0
    rows_written: int = 0


def check_destination(dest_root: str, event_name: str | None) -> None:
    if not (dest_root.rstrip("/") + "/").startswith(PROD_PREFIX):
        return
    if event_name != "schedule":
        raise DestinationRefused(
            f"refusing to write to {dest_root}: only a scheduled run "
            f"(GITHUB_EVENT_NAME == schedule) writes under {PROD_PREFIX}; "
            f"GITHUB_EVENT_NAME is {event_name!r}"
        )


def _local_destination(run: str) -> bool:
    """Whether a command passes a literal, non-S3 `--dest-root`."""
    args = shlex.split(run.replace("\\\n", " "))
    if "--dest-root" not in args or args.index("--dest-root") + 1 >= len(args):
        return False
    dest = args[args.index("--dest-root") + 1]
    return not dest.startswith("s3://") and "$" not in dest


def runs_writer(workflow_text: str) -> bool:
    """Whether any step of a workflow runs the writer without a local destination.

    A destination the scan cannot read as a literal path (a variable) counts as
    not local: the scan fails closed (#198 D3).
    """
    workflow = yaml.safe_load(workflow_text) or {}
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            command = f"{step.get('run', '')} {step.get('uses', '')}"
            if any(s in command for s in WRITER_SCRIPTS) and not _local_destination(command):
                return True
    return False


# The one workflow that may run the writer against the production prefix
# (#205 G4, W16), and only on its schedule: #193 A6 refuses any other trigger.
PRODUCTION_WORKFLOW = "scheduled_compaction.yml"


def workflow_problems(workflows: dict[str, str]) -> list[str]:
    """One message per workflow, by file name, that breaks the production rule."""
    problems = []
    for name, text in sorted(workflows.items()):
        if not runs_writer(text):
            continue
        if name != PRODUCTION_WORKFLOW:
            problems.append(
                f"{name} runs the compaction writer without a local destination; "
                f"only {PRODUCTION_WORKFLOW} may"
            )
            continue
        triggers = (yaml.safe_load(text) or {}).get(True)  # PyYAML reads `on` as True
        if not isinstance(triggers, dict) or set(triggers) != {"schedule"}:
            problems.append(f"{name} may only be triggered by its schedule")
    return problems


def manifest_problems(record: dict) -> list[str]:
    missing = [f"missing field: {f}" for f in MANIFEST_FIELDS if f not in record]
    extra = [f"extra field: {f}" for f in record if f not in MANIFEST_FIELDS]
    return missing + extra


def parquet_path(dest_root: str, day: str) -> str:
    return f"{dest_root.rstrip('/')}/fpl/{ENDPOINT}/date={day}/part.parquet"


def manifest_path(dest_root: str, day: str) -> str:
    return f"{dest_root.rstrip('/')}/fpl/{ENDPOINT}/_manifest/date={day}.json"


def _is_s3(path: str) -> bool:
    return path.startswith("s3://")


def _connect(*roots: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    if any(_is_s3(r) for r in roots):
        con.sql("create secret (type s3, provider credential_chain, chain 'env')")
    return con


def _put(local: str, dest: str) -> None:
    if _is_s3(dest):
        import boto3

        bucket, key = dest.removeprefix("s3://").split("/", 1)
        boto3.client("s3").upload_file(local, bucket, key)
    else:
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(local).replace(dest)


def write_parquet(files: list[str], path: str) -> None:
    con = _connect(path, *files)
    with tempfile.TemporaryDirectory() as tmp:
        local = f"{tmp}/part.parquet"
        con.execute(
            "copy (select * from read_json(?, union_by_name = true, filename = true)) "
            f"to '{local}' (format parquet)",
            [files],
        )
        _put(local, path)


def write_manifest(record: dict, path: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        local = f"{tmp}/manifest.json"
        Path(local).write_text(json.dumps(record, indent=2) + "\n")
        _put(local, path)


def _key(raw_root: str, path: str) -> str:
    """A raw file's capture key: `raw/` plus its path below raw_root."""
    return "raw/" + path[len(raw_root.rstrip("/")) + 1 :]


def _run_id(raw_root: str, path: str) -> str:
    # raw/fpl/element-summary/<fpl_id>/<day>/<run_id>/payload.json
    return _key(raw_root, path).split("/")[5]


def _read_json(con, path: str) -> dict | None:
    rows = con.execute("select content from read_text(?)", [path]).fetchall()
    return json.loads(rows[0][0]) if rows else None


def _glob(con, pattern: str) -> list[str]:
    return sorted(r[0] for r in con.execute("select file from glob(?)", [pattern]).fetchall())


def _index(con, raw_root: str, run_id: str, manifest: dict) -> list[dict] | None:
    """The run's index: finalized manifest captures[], else its catalog entry."""
    if manifest.get("status") != "IN_PROGRESS" and manifest.get("captures") is not None:
        return manifest["captures"]
    catalog = _glob(con, f"{raw_root.rstrip('/')}/fpl/_catalog/backfill/{run_id}.json")
    return _read_json(con, catalog[0])["captures"] if catalog else None


def list_payloads(raw_root: str) -> dict[str, list[str]]:
    """Every element-summary payload file, by capture day: one listing (#203)."""
    raw_root = raw_root.rstrip("/")
    con = _connect(raw_root)
    by_day: dict[str, list[str]] = {}
    for f in _glob(con, f"{raw_root}/fpl/{ENDPOINT}/*/*/*/payload.json"):
        by_day.setdefault(_key(raw_root, f).split("/")[4], []).append(f)
    return by_day


def _sha256_all(files: list[str]) -> dict[str, str]:
    """Each file's sha256, read concurrently."""
    if any(_is_s3(f) for f in files):
        import boto3

        client = boto3.client("s3")

        def read(f: str) -> bytes:
            bucket, key = f.removeprefix("s3://").split("/", 1)
            return client.get_object(Bucket=bucket, Key=key)["Body"].read()
    else:
        def read(f: str) -> bytes:
            return Path(f).read_bytes()

    with ThreadPoolExecutor(SHA_WORKERS) as pool:
        digests = pool.map(lambda f: hashlib.sha256(read(f)).hexdigest(), files)
        return dict(zip(files, digests))


def _git_sha() -> str:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


def compact_day(
    day: str, raw_root: str, dest_root: str, files: list[str] | None = None
) -> DayResult:
    """`files` is the day's payload files from `list_payloads`; listed here if None."""
    raw_root = raw_root.rstrip("/")
    con = _connect(raw_root, dest_root)
    if files is None:
        files = _glob(con, f"{raw_root}/fpl/{ENDPOINT}/*/{day}/*/payload.json")
    if not files:
        return DayResult(False, f"{day}: no payload files")
    read = len(files)

    manifests = {}
    for run_id in sorted({_run_id(raw_root, f) for f in files}):
        found = _glob(con, f"{raw_root}/fpl/_manifests/*/{run_id}/manifest.json")
        if not found:
            return DayResult(False, f"{day}: run {run_id} has no run manifest", read)
        manifests[run_id] = _read_json(con, found[0])
        stated = manifests[run_id].get("extraction_date")
        if stated != day:
            return DayResult(
                False, f"{day}: run {run_id}'s manifest states extraction_date {stated}", read
            )

    parquet = parquet_path(dest_root, day)
    write_parquet(files, parquet)

    rows, distinct = con.execute(
        "select count(*), count(distinct filename) "
        "from read_parquet(?, hive_partitioning = false)",
        [parquet],
    ).fetchone()
    if not len(files) == rows == distinct:
        return DayResult(
            False,
            f"{day}: {len(files)} payload files, {rows} parquet rows, "
            f"{distinct} distinct filenames",
            read,
            rows,
        )

    expected = {}
    for run_id, manifest in manifests.items():
        index = _index(con, raw_root, run_id, manifest)
        if index is None:
            return DayResult(
                False, f"{day}: run {run_id} has neither captures[] nor a catalog entry",
                read,
                rows,
            )
        for capture in index:
            key = capture["key"]
            if key.startswith(KEY_PREFIX) and key.split("/")[4] == day:
                expected[capture["key"]] = capture["content_sha256"]

    actual = {_key(raw_root, f): sha for f, sha in _sha256_all(files).items()}
    if actual.keys() != expected.keys():
        unindexed = sorted(actual.keys() - expected.keys())
        unlisted = sorted(expected.keys() - actual.keys())
        return DayResult(
            False,
            f"{day}: listed but not indexed {unindexed}; indexed but not listed {unlisted}",
            read,
            rows,
        )
    mismatched = sorted(k for k in actual if actual[k] != expected[k])
    if mismatched:
        return DayResult(
            False, f"{day}: sha256 differs from the index for {mismatched}", read, rows
        )

    write_manifest(
        {
            "capture_day": day,
            "payload_files": len(files),
            "parquet_rows": rows,
            "distinct_filenames": distinct,
            "run_ids": sorted(manifests),
            "compacted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_sha": _git_sha(),
        },
        manifest_path(dest_root, day),
    )
    return DayResult(True, "", read, rows)


def compact_days(
    days: list[str],
    raw_root: str,
    dest_root: str,
    event_name: str | None = None,
    listing: dict[str, list[str]] | None = None,
) -> dict[str, DayResult]:
    """`listing` is `list_payloads(raw_root)`, passed by a caller that lists once."""
    if event_name is None:
        event_name = os.environ.get("GITHUB_EVENT_NAME")
    check_destination(dest_root, event_name)
    if listing is None:
        listing = list_payloads(raw_root)
    return {
        day: compact_day(day, raw_root, dest_root, listing.get(day, [])) for day in days
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--day", action="append", required=True, help="YYYY-MM-DD; repeat")
    parser.add_argument("--raw-root", required=True, help="e.g. s3://fpl-data-safari/raw")
    parser.add_argument("--dest-root", required=True, help="e.g. s3://fpl-data-safari/compacted")
    args = parser.parse_args()
    try:
        results = compact_days(args.day, args.raw_root, args.dest_root)
    except DestinationRefused as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    for day, result in results.items():
        print(f"{day}: {'compacted' if result.ok else 'FAILED ' + result.reason}")
    return 0 if all(r.ok for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
