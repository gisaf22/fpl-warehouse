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
import yaml

DATABASE = Path(".local/warehouse.duckdb")
OUT_DIR = Path(".local/served")
BUCKET = "fpl-data-safari"
PREFIX = "served/"

TABLES = ("fct_player_fixture", "fct_player_gameweek")

PROJECT_FILE = Path("dbt_project.yml")

# How far below its computed expectation a season's slice of a table may fall
# before the publish is refused, as a fraction.
#
# Per table, because the two tables stand in different relationships to the
# same expectation (players x rounds — see expected_rows below):
#
#   fct_player_gameweek IS that grain. It is built by LEFT JOIN off
#   int_player_gameweek_spine, which is the same players-crossed-with-rounds
#   product computed from the same staging tables, so a correct build matches
#   the expectation exactly — measured 31,958 / 31,958 and 2,668 / 2,668 on
#   2026-09-21. The 2% is not room for legitimate variance, of which there is
#   none; it is there so a publish guard is not an exact-equality assertion.
#
#   fct_player_fixture is a different grain — one row per fixture a player
#   actually has history for, not per round — and it sits below the
#   expectation by however much the season blanked. Measured 2026-09-21:
#   2025-26 returned 29,747 against an expected 31,958, 6.9% low, which is
#   2,211 player-rounds in which that player's club did not play. 15% is
#   roughly 2x that observed worst case. It is deliberately loose: this is a
#   guard against a season vanishing, not a data-quality test, and dbt's own
#   suite owns correctness.
#
# Double gameweeks push in the other direction, adding rows above the
# expectation. Nothing here caps the upside — a table larger than expected is
# not the failure this guards against.
TOLERANCE = {
    "fct_player_fixture": 0.15,
    "fct_player_gameweek": 0.02,
}


def live_season() -> str:
    """The season var from dbt_project.yml — the one season still accumulating.

    Read from the project file rather than duplicated here, because the same
    value already drives sources.yml's live globs and fct_player_fixture's
    round-1 fallback, and a second copy would drift the moment the season rolls
    over. PyYAML arrives transitively with dbt-core; this script only ever runs
    in an environment where dbt has just built the database it reads.
    """
    project = yaml.safe_load(PROJECT_FILE.read_text())
    return project["vars"]["season"]


def expected_rows(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Rows each season should contribute, computed from that build's staging.

    This replaces a static floor of 500 rows, which was sized in 2026-09 when
    one part-played season held ~3,200 rows. Against a two-season build it is
    three orders of magnitude below anything real — a build that silently
    dropped all of 2025-26 would clear it comfortably and overwrite good
    published data with a single-season table.

    The expectation for a season is its own player count times its own round
    count, both read from that season's captures only:

      players  distinct fpl_id across every bootstrap-static capture of the
               season, matching int_player_gameweek_spine's union — a
               mid-season departure is part of the season's history whether or
               not they are still in `elements`.

      rounds   for a CLOSED season, every round on its calendar: the season is
               over, so all of them count. For the LIVE season, only the rounds
               its latest capture reports `finished`. That distinction is the
               whole reason this is not one uniform rule — the live calendar
               publishes all 38 rounds from day one, so counting them all would
               have expected 667 x 38 = 25,346 rows for 2026-27 on 2026-09-21
               against a real 3,216. For a closed season the two readings
               coincide by definition, and
               tests/fct_test_player_fixture_closed_season_settled.sql fails
               the build unless every round of it is finished and data_checked.

    Deliberately computed from staging rather than from
    int_player_gameweek_spine, which is already exactly this product. The spine
    is fct_player_gameweek's direct parent, so checking that table against it
    would compare a number against itself and pass unconditionally. Recomputing
    from stg_player and stg_gameweek makes it an independent second opinion.

    Returns {season: expected_rows}, empty only if staging holds no seasons at
    all — which main() treats as a failure rather than as nothing to check.
    """
    rows = connection.execute(
        """
        with latest_capture as (
            select season, run_id
            from (
                select
                    season,
                    run_id,
                    row_number() over (
                        partition by season
                        order by extracted_at desc, run_id desc
                    ) as capture_rank
                from (
                    select distinct season, run_id, extracted_at
                    from main.stg_gameweek
                )
            )
            where capture_rank = 1
        ),

        players as (
            select season, count(distinct fpl_id) as players
            from main.stg_player
            group by season
        ),

        rounds as (
            select
                gameweek.season,
                count(*) filter (
                    where gameweek.season <> $live_season or gameweek.finished
                ) as rounds
            from main.stg_gameweek as gameweek
            inner join latest_capture using (season, run_id)
            group by gameweek.season
        )

        select players.season, players.players * rounds.rounds
        from players
        inner join rounds using (season)
        order by players.season
        """,
        {"live_season": live_season()},
    ).fetchall()
    return {season: expected for season, expected in rows}


def main() -> int:
    if not DATABASE.exists():
        print(f"::error::no database at {DATABASE} — did `dbt build` run?")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # read_only: this process must not be able to mutate the built warehouse.
    connection = duckdb.connect(str(DATABASE), read_only=True)

    expected = expected_rows(connection)

    # An empty expectation means staging itself is empty, which the per-season
    # loop below would otherwise wave through with nothing to compare against.
    # The old static floor caught this case by accident; it has to be explicit
    # now that the floor is derived from the same build it guards.
    if not expected:
        print(
            "::error::no seasons found in staging — the build has no data to "
            "publish. Refusing to overwrite the existing served data."
        )
        return 1

    counts: dict[str, int] = {}
    by_season: dict[str, dict[str, int]] = {}
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

        # Per season too, from the same file and for the same reason. This is
        # what the check below compares, and what the manifest carries.
        seasons = connection.execute(
            "SELECT season, count(*) FROM read_parquet(?) "
            "GROUP BY season ORDER BY season",
            [str(path)],
        ).fetchall()

        counts[table] = count
        by_season[table] = {season: n for season, n in seasons}
        paths[table] = path

    # Checked per season, not only against the summed total.
    #
    # The sum alone is not sensitive enough in a two-season build and gets less
    # so as the archive grows. On 2026-09-21 the live season was four rounds in
    # and held 3,216 of fct_player_fixture's 32,963 rows: losing all of 2026-27
    # would have shown up as a 9.3% shortfall on the total, inside the 15%
    # this table needs for blank gameweeks. The same loss is unmissable against
    # that season's own expectation. Every season present in staging must also
    # be present in the served table — a season that vanishes entirely is the
    # failure this exists to catch, and it scores zero rows, not a small
    # shortfall.
    failures: list[str] = []

    for table in TABLES:
        tolerance = TOLERANCE[table]
        for season, season_expected in sorted(expected.items()):
            actual = by_season[table].get(season, 0)
            floor = int(season_expected * (1 - tolerance))
            if actual < floor:
                shortfall = 1 - actual / season_expected if season_expected else 1
                failures.append(
                    f"{table} holds {actual:,} rows for {season}, "
                    f"{shortfall:.1%} below the {season_expected:,} expected "
                    f"from that season's own {tolerance:.0%}-tolerance floor "
                    f"of {floor:,}"
                )

    if failures:
        for failure in failures:
            print(
                f"::error::{failure} — refusing to publish over the existing "
                f"served data. Inspect the build before re-running."
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
    #
    # `row_counts` keeps its existing shape — {table: total} — rather than
    # becoming nested now that a build carries two seasons. A consumer that
    # reads it today reads the same type tomorrow, and the total is still the
    # right number to check a full-file read against. The per-season breakdown
    # is added alongside as `row_counts_by_season`, and `seasons` names what is
    # in the files at all, so a consumer can assert the season it wants is
    # present without parsing the parquet first.
    #
    # `seasons` is deliberately a list rather than a "is this multi-season?"
    # flag: a flag would encode today's two-season state as the thing to branch
    # on, and the count changes again the moment another season is ported.
    manifest = {
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "seasons": sorted(expected),
        "row_counts": counts,
        "row_counts_by_season": by_season,
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
    lines = []
    for table in TABLES:
        breakdown = ", ".join(
            f"{season} {n:,}" for season, n in sorted(by_season[table].items())
        )
        lines.append(f"- `{table}`: {counts[table]:,} rows ({breakdown})")
    lines.append(
        "- expected from staging: "
        + ", ".join(f"{season} {n:,}" for season, n in sorted(expected.items()))
        + f" — total {sum(expected.values()):,}"
    )
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Published to served/\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
