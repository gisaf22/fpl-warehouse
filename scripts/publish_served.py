"""Export the two served fact tables to parquet and publish them to S3.

Called by .github/workflows/scheduled_build.yml after a successful
`dbt build`. Split out of the workflow rather than inlined as a heredoc so it
is lintable by ruff and readable in a diff.

Mechanism, deliberately: DuckDB does the local export only (COPY to a file),
boto3 does the upload. DuckDB's httpfs could write s3:// directly, but the
upload path in this account is already boto3 in fpl-ingest's
``S3Backend`` — same credential resolution, same client construction, same
failure surface — and having one S3 write mechanism across both repos is
worth more than saving a process boundary here.

Credentials are never handled here, matching S3Backend's docstring: boto3
resolves them from the standard chain, which in CI is the OIDC-federated role
established by aws-actions/configure-aws-credentials earlier in the job.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import duckdb

DATABASE = Path(".local/warehouse.duckdb")
OUT_DIR = Path(".local/served")
BUCKET = "fpl-data-safari"
PREFIX = "served/"

TABLES = ("fct_player_fixture", "fct_player_gameweek")

# Minimum plausible row count per served table.
#
# Not a tuned figure — it is a floor whose only job is to catch a build that
# produced an empty or catastrophically truncated table and would otherwise
# overwrite good published data with it. The live build measured 1,890 and
# 1,962 rows on 2026-09-07, at which point only a few gameweeks had been
# played; both tables grow monotonically as the season accumulates, so 500 sits
# well below anything a real build can return while still being far above zero.
# dbt's own tests are what assert correctness; this guards the publish.
ROW_FLOOR = 500


def main() -> int:
    if not DATABASE.exists():
        print(f"::error::no database at {DATABASE} — did `dbt build` run?")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # read_only: this process must not be able to mutate the built warehouse.
    connection = duckdb.connect(str(DATABASE), read_only=True)

    counts: dict[str, int] = {}
    paths: dict[str, Path] = {}

    for table in TABLES:
        path = OUT_DIR / f"{table}.parquet"
        connection.execute(
            f"COPY main.{table} TO '{path}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )

        # Counted from the written file, not from the source table: the point of
        # the check is that the artefact about to be uploaded is non-empty, and
        # only reading it back proves the COPY actually landed those rows.
        count = connection.execute(
            "SELECT count(*) FROM read_parquet(?)", [str(path)]
        ).fetchone()[0]

        counts[table] = count
        paths[table] = path

    failed = {table: n for table, n in counts.items() if n < ROW_FLOOR}
    if failed:
        for table, n in failed.items():
            print(
                f"::error::{table} exported {n} rows, below the floor of "
                f"{ROW_FLOOR} — refusing to publish over the existing served "
                f"data. Inspect the build before re-running."
            )
        return 1

    # Same construction as fpl-ingest's S3Backend._default_client.
    client = boto3.client("s3")

    for table, path in paths.items():
        key = f"{PREFIX}{table}.parquet"
        client.put_object(Bucket=BUCKET, Key=key, Body=path.read_bytes())
        print(f"published s3://{BUCKET}/{key} ({counts[table]} rows)")

    # Overwritten in place on every run, like the objects it describes. It is a
    # pointer to what is currently published, not a history of publishes.
    manifest = {
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "row_counts": counts,
    }
    manifest_key = f"{PREFIX}_manifest.json"
    client.put_object(
        Bucket=BUCKET,
        Key=manifest_key,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )
    print(f"published s3://{BUCKET}/{manifest_key}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = [f"- `{table}`: {counts[table]} rows" for table in TABLES]
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Published to served/\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
