"""Time DuckDB's glob expansion over the raw tree, with no object reads.

Called by ci.yml's live-tests job. It exists to settle one number that the
incremental/compaction scoping could not: how much of stg_player_fixture's
~600s build is S3 LIST rather than the ~50k object GETs.

`glob()` issues the listing and returns key names — it opens no payload — so
the timings here are LIST-only and directly subtractable from the model's
build time.

Three globs, because the shape of the answer matters as much as the number:

  1. `*` over the player level        — one prefix listing, the floor.
  2. `*/*/*/payload.json`             — the glob staging actually uses.
  3. `**`                             — every key under the prefix, payloads
                                        and their metadata.json sidecars.

If (2) is close to (1), DuckDB is doing a single paginated recursive listing
and matching client-side, which puts LIST at a few percent of the build and
makes a manifest-driven read worthless as a speedup. If (2) scales with the
number of player prefixes instead, it is walking the tree level by level —
~7k calls rather than ~100 — and LIST is a large share of the build, which
would make the manifest the cheapest available win. (3) says how much of the
listing is sidecars the model never reads.

Credentials are never handled here: the S3 secret uses DuckDB's `env` chain,
which in CI is the OIDC-federated role configured earlier in the job.
"""

from __future__ import annotations

import os
import sys
import time

import duckdb

RAW_ROOT = os.environ.get("RAW_ROOT", "s3://fpl-data-safari/raw")
THREADS = os.environ.get("DBT_DUCKDB_THREADS", "32")

GLOBS = (
    ("player prefixes only", "fpl/element-summary/*"),
    ("staging's glob", "fpl/element-summary/*/*/*/payload.json"),
    ("every key under prefix", "fpl/element-summary/**"),
)


def main() -> int:
    connection = duckdb.connect()
    connection.execute("INSTALL httpfs")
    connection.execute("LOAD httpfs")
    connection.execute(f"SET threads = '{THREADS}'")
    connection.execute(
        "CREATE SECRET (TYPE s3, PROVIDER credential_chain, "
        "CHAIN 'env', REGION 'us-east-1')"
    )

    print(f"raw_root={RAW_ROOT}  threads={THREADS}\n")
    print(f"{'glob':<24} {'keys':>10} {'seconds':>9}")
    print("-" * 45)

    results = {}
    for label, pattern in GLOBS:
        started = time.monotonic()
        keys = connection.execute(
            "SELECT count(*) FROM glob(?)", [f"{RAW_ROOT}/{pattern}"]
        ).fetchone()[0]
        elapsed = time.monotonic() - started
        results[label] = (keys, elapsed)
        print(f"{label:<24} {keys:>10,} {elapsed:>9.2f}")

    payload_keys, payload_secs = results["staging's glob"]
    all_keys, _ = results["every key under prefix"]
    if payload_keys:
        print(
            f"\nLIST-only cost of the staging glob: {payload_secs:.1f}s "
            f"over {payload_keys:,} payload keys "
            f"({all_keys:,} total keys under the prefix, "
            f"{all_keys / payload_keys:.1f}x)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
