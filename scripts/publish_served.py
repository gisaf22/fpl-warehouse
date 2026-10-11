"""Export the served fact and dimension tables to parquet and publish them to S3.

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

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
import duckdb
import yaml
from botocore.exceptions import BotoCoreError, ClientError

DATABASE = Path(".local/warehouse.duckdb")
OUT_DIR = Path(".local/served")
BUCKET = "fpl-data-safari"
PREFIX = "served/"
MANIFEST_KEY = f"{PREFIX}_manifest.json"

TABLES = (
    "fct_player_fixture",
    "fct_player_gameweek",
    "dim_team",
    "dim_player",
    "dim_fixture",
    "dim_player_status_history",
    "fct_player_market_snapshot",
)

# Every staging model, as the source of which seasons the build holds. A season
# found in any of them must be served by every table (see staged_seasons).
STAGING = (
    "stg_player",
    "stg_gameweek",
    "stg_team",
    "stg_fixture",
    "stg_player_fixture",
)

# A Premier League season's fixed sizes: 20 clubs, each playing the other 19
# home and away. Measured on 2026-09-28, every bootstrap-static capture of
# both seasons holds exactly 20 teams and every fixtures capture exactly 380
# fixtures. A postponed fixture keeps its id and a null gameweek, so it still
# counts toward 380.
TEAMS_PER_SEASON = 20
FIXTURES_PER_SEASON = 380

PROJECT_FILE = Path("dbt_project.yml")

# How far below its computed expectation a season's slice of a table may fall
# before the publish is refused, as a fraction.
#
# Per table, because the two tables stand in different relationships to the
# same expectation (players x gameweeks — see expected_rows below):
#
#   fct_player_gameweek IS that grain. It is built by LEFT JOIN off
#   int_player_gameweek_spine, which is the same players-crossed-with-gameweeks
#   product computed from the same staging tables, so a correct build matches
#   the expectation exactly — measured 31,958 / 31,958 and 2,668 / 2,668 on
#   2026-09-21. The 2% is not room for legitimate variance, of which there is
#   none; it is there so a publish guard is not an exact-equality assertion.
#
#   fct_player_fixture is a different grain — one row per fixture a player
#   actually has history for, not per gameweek — and it sits below the
#   expectation by however much the season blanked. Measured 2026-09-21:
#   2025-26 returned 29,747 against an expected 31,958, 6.9% low, which is
#   2,211 player-gameweeks in which that player's club did not play. 15% is
#   roughly 2x that observed worst case. It is deliberately loose: this is a
#   guard against a season vanishing, not a data-quality test, and dbt's own
#   suite owns correctness.
#
# Double gameweeks push in the other direction, adding rows above the
# expectation. Nothing here caps the upside — a table larger than expected is
# not the failure this guards against.
#
# The dimensions take no tolerance. Each one's expectation is exact rather
# than an estimate: a season has 20 teams and 380 fixtures, and dim_player
# holds every player staged in the season (int_player_season's set). One row
# short is a lost row, not variance.
#
# dim_player_status_history takes none either, but its expectation is a lower
# bound rather than an exact count: every staged player has at least one row
# (their first capture opens it) and a status change adds one, so a season
# holds at least its distinct players and normally more (#127).
#
# fct_player_market_snapshot takes none, and its expectation is exact: one row
# per player per admitted bootstrap-static capture, which is stg_player's row
# count for the season (#143). The model selects those rows 1:1, so this guards
# the export rather than data lost upstream; the previous-publish comparison
# covers that.
TOLERANCE = {
    "fct_player_fixture": 0.15,
    "fct_player_gameweek": 0.02,
    "dim_team": 0.0,
    "dim_player": 0.0,
    "dim_fixture": 0.0,
    "dim_player_status_history": 0.0,
    "fct_player_market_snapshot": 0.0,
}


def live_season() -> str:
    """The season var from dbt_project.yml — the one season still accumulating.

    Read from the project file rather than duplicated here, because the same
    value already drives sources.yml's live globs and fct_player_fixture's
    gameweek-1 fallback, and a second copy would drift the moment the season rolls
    over. PyYAML arrives transitively with dbt-core; this script only ever runs
    in an environment where dbt has just built the database it reads.
    """
    project = yaml.safe_load(PROJECT_FILE.read_text())
    return project["vars"]["season"]


def contract_version() -> int:
    """The served_contract_version var from dbt_project.yml (#74).

    Bumped by hand on every breaking change to the served contract, in the same
    pull request as the change. Kept beside the models rather than here so the
    bump is reviewed with the schema.yml edit that needs it.
    """
    version = yaml.safe_load(PROJECT_FILE.read_text())["vars"][
        "served_contract_version"
    ]
    if type(version) is not int:
        raise ValueError(f"served_contract_version must be an integer, not {version!r}")
    return version


def staged_seasons(connection: duckdb.DuckDBPyConnection) -> list[str]:
    """Every season any staging model holds.

    The floor checks each of these in every served table, so where this list
    comes from decides which lost seasons the floor can see. Taken from all
    staging models rather than from the ones a table is built from: a season
    whose bootstrap-static captures all came back empty never reaches
    stg_team, stg_player or stg_gameweek, but the fixtures endpoint and
    element-summary history still stage it. A list read from stg_team alone
    would drop that season and never check dim_team for it (#44 AC7).
    """
    union = " union ".join(f"select distinct season from main.{m}" for m in STAGING)
    return [row[0] for row in connection.execute(f"{union} order by 1").fetchall()]


def expected_rows(
    connection: duckdb.DuckDBPyConnection, seasons: list[str]
) -> dict[str, dict[str, int]]:
    """Rows each table should hold per season, computed from that build's staging.

    This replaces a static floor of 500 rows, which was sized in 2026-09 when
    one part-played season held ~3,200 rows. Against a two-season build it is
    three orders of magnitude below anything real — a build that silently
    dropped all of 2025-26 would clear it comfortably and overwrite good
    published data with a single-season table.

    The expectation for a season is its own player count times its own gameweek
    count, both read from that season's captures only:

      players    distinct fpl_id across every bootstrap-static capture of the
                 season, matching int_player_gameweek_spine's union — a
                 mid-season departure is part of the season's history whether
                 or not they are still in `elements`.

      gameweeks  for a CLOSED season, every gameweek on its calendar: the
                 season is over, so all of them count. For the LIVE season,
                 only the gameweeks its latest capture reports `finished`. That
                 distinction is the whole reason this is not one uniform rule —
                 the live calendar publishes all 38 gameweeks from day one, so
                 counting them all would have expected 667 x 38 = 25,346 rows
                 for 2026-27 on 2026-09-21 against a real 3,216. For a closed
                 season the two readings coincide by definition, and
                 tests/fct_test_player_fixture_closed_season_settled.sql fails
                 the build unless every gameweek of it is finished and
                 data_checked.

    Deliberately computed from staging rather than from
    int_player_gameweek_spine, which is already exactly this product. The spine
    is fct_player_gameweek's direct parent, so checking that table against it
    would compare a number against itself and pass unconditionally. Recomputing
    from stg_player and stg_gameweek makes it an independent second opinion.

    That players x gameweeks product is the facts' expectation. The dimensions'
    are simpler: TEAMS_PER_SEASON teams, FIXTURES_PER_SEASON fixtures, and the
    season's staged players, the same distinct fpl_id count as above. That
    count is also dim_player_status_history's floor, at least one row per
    staged player. fct_player_market_snapshot's is the season's stg_player
    rows: one per player per capture.

    Every season in `seasons` gets an entry for every table. A season that
    lacks players or gameweeks expects 0 fact rows, which is right at the start
    of a season, before any gameweek has finished; the fixed dimension counts
    still apply to it, so a season cannot vanish without failing somewhere.

    Returns {table: {season: expected_rows}}.
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
                        order by observed_at desc, run_id desc
                    ) as capture_rank
                from (
                    select distinct season, run_id, observed_at
                    from main.stg_gameweek
                )
            )
            where capture_rank = 1
        ),

        players as (
            select
                season,
                count(distinct fpl_id) as players,
                count(*) as player_captures
            from main.stg_player
            group by season
        ),

        gameweeks as (
            select
                calendar.season,
                count(*) filter (
                    where calendar.season <> $live_season or calendar.finished
                ) as gameweeks
            from main.stg_gameweek as calendar
            inner join latest_capture using (season, run_id)
            group by calendar.season
        )

        select
            season,
            players.players,
            gameweeks.gameweeks,
            players.player_captures
        from players
        full outer join gameweeks using (season)
        """,
        {"live_season": live_season()},
    ).fetchall()
    players = {season: n or 0 for season, n, _, _ in rows}
    gameweeks = {season: n or 0 for season, _, n, _ in rows}
    player_captures = {season: n or 0 for season, _, _, n in rows}

    per_season = {
        "fct_player_fixture": lambda s: players.get(s, 0) * gameweeks.get(s, 0),
        "fct_player_gameweek": lambda s: players.get(s, 0) * gameweeks.get(s, 0),
        "dim_team": lambda _s: TEAMS_PER_SEASON,
        "dim_player": lambda s: players.get(s, 0),
        "dim_fixture": lambda _s: FIXTURES_PER_SEASON,
        "dim_player_status_history": lambda s: players.get(s, 0),
        "fct_player_market_snapshot": lambda s: player_captures.get(s, 0),
    }
    return {
        table: {season: per_season[table](season) for season in seasons}
        for table in TABLES
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--restate",
        action="append",
        default=[],
        metavar="SEASON",
        help="let SEASON publish fewer rows than the previous publish held; "
        "repeat for several. Recorded in the manifest's restated_seasons.",
    )
    parser.add_argument(
        "--without-baseline",
        action="store_true",
        help="publish even if the previous manifest is missing or unreadable. "
        "Recorded in the manifest's published_without_baseline.",
    )
    return parser.parse_args()


def previous_manifest(client) -> tuple[dict | None, str | None]:
    """The previous publish's manifest, or why it can't be used as a baseline.

    Returns (manifest, None) or (None, problem). Only the per-season counts are
    required: a manifest written before restated_seasons,
    published_without_baseline, contract_version or columns existed is a valid
    baseline.
    """
    location = f"s3://{BUCKET}/{MANIFEST_KEY}"
    try:
        body = client.get_object(Bucket=BUCKET, Key=MANIFEST_KEY)["Body"].read()
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "unknown")
        return None, f"previous manifest {location} could not be read ({code}: {error})"
    except BotoCoreError as error:
        return None, f"previous manifest {location} could not be read ({error})"

    try:
        previous = json.loads(body)
        previous["row_counts_by_season"] = {
            table: {season: int(n) for season, n in seasons.items()}
            for table, seasons in previous["row_counts_by_season"].items()
        }
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return None, (
            f"previous manifest {location} has no usable row_counts_by_season "
            f"({type(error).__name__}: {error})"
        )
    return previous, None


def contract_failures(
    previous: dict, version: int, columns: dict[str, list[list[str]]]
) -> list[str]:
    """Why this publish breaks the served contract without a version bump (#74).

    The version may never go down. At the same version, every table the
    previous manifest listed must keep its columns as a prefix of its new ones:
    a column appended last, or a table not listed before, is additive and
    passes; a column dropped, renamed, retyped or moved is breaking and needs a
    higher version. A previous manifest without the fields predates #74 and
    skips the check it cannot make.

    It sees shape only. A change in what an existing column's values mean (the
    is_ratified case of 2026-09-15) passes here and must be bumped by review.
    """
    before = previous.get("contract_version")
    if before is None:
        return []
    if version < before:
        return [
            f"contract_version {version} is below the previous publish's "
            f"{before}; the served contract version never goes down"
        ]
    if version > before:
        return []

    failures = []
    for table, old in sorted((previous.get("columns") or {}).items()):
        new = columns.get(table)
        if new is None:
            failures.append(
                f"{table} was served at contract_version {version} and is no "
                f"longer published; removing a served table is breaking"
            )
        elif [list(c) for c in old] != new[: len(old)]:
            failures.append(
                f"{table}'s columns changed from {old} to {new} at contract_version "
                f"{version}; dropping, renaming, retyping or moving a served "
                f"column is breaking — bump served_contract_version in "
                f"dbt_project.yml"
            )
    return failures


def main() -> int:
    args = parse_args()
    restated = sorted(set(args.restate))

    if not DATABASE.exists():
        print(f"::error::no database at {DATABASE} — did `dbt build` run?")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # read_only: this process must not be able to mutate the built warehouse.
    connection = duckdb.connect(str(DATABASE), read_only=True)

    seasons = staged_seasons(connection)

    # No seasons means staging itself is empty, which the per-season loop
    # below would otherwise wave through with nothing to compare against. The
    # old static floor caught this case by accident; it has to be explicit now
    # that the floor is derived from the same build it guards.
    if not seasons:
        print(
            "::error::no seasons found in staging — the build has no data to "
            "publish. Refusing to overwrite the existing served data."
        )
        return 1

    expected = expected_rows(connection, seasons)
    version = contract_version()

    counts: dict[str, int] = {}
    columns: dict[str, list[list[str]]] = {}
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
        # Named apart from `seasons`, the staged season list the manifest
        # publishes: reusing that name here overwrote it with the last table's
        # (season, count) rows (#76).
        table_seasons = connection.execute(
            "SELECT season, count(*) FROM read_parquet(?) "
            "GROUP BY season ORDER BY season",
            [str(path)],
        ).fetchall()

        # The shape actually uploaded, for the manifest and the contract check.
        columns[table] = [
            [name, column_type]
            for name, column_type, *_ in connection.execute(
                "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
            ).fetchall()
        ]

        counts[table] = count
        by_season[table] = {season: n for season, n in table_seasons}
        paths[table] = path

    # Checked per season, not only against the summed total.
    #
    # The sum alone is not sensitive enough in a two-season build and gets less
    # so as the archive grows. On 2026-09-21 the live season was four rounds in
    # and held 3,216 of fct_player_fixture's 32,963 rows: losing all of 2026-27
    # would have shown up as a 9.3% shortfall on the total, inside the 15%
    # this table needs for blank gameweeks. The same loss is unmissable against
    # that season's own expectation. Every season present in staging must also
    # be present in every served table — a season that vanishes entirely is the
    # failure this exists to catch, and it scores zero rows, not a small
    # shortfall.
    failures: list[str] = []

    for table in TABLES:
        tolerance = TOLERANCE[table]
        for season, season_expected in sorted(expected[table].items()):
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

    # Checked against the previous publish too, because the floor above cannot
    # see a loss that happened upstream of staging. The floor's expectation is
    # computed from this build's staging, so when rows vanish before staging —
    # a raw tree that went unreadable, a key layout that changed — the
    # expectation shrinks with them and the floor still passes. A season that
    # left staging entirely is not in `expected` at all and is never checked
    # there. The previous manifest is the only record of what was served, so
    # every season it lists is held to its count, in each table, and may not
    # go down unless the run names it with --restate.
    #
    # Strict, not a tolerance: a legitimate shrink is rare (FPL retracting a
    # history row on a day no new fixture is played can drop one
    # fct_player_fixture row) and a rerun with --restate covers it, whereas any
    # tolerance is a loss this check would wave through.
    #
    # A season absent from the previous manifest has no previous count and is
    # held only to the floor above, so a newly ported season can be published.

    # Same construction as fpl-ingest's S3Backend._default_client.
    client = boto3.client("s3")

    previous_publish, baseline_problem = previous_manifest(client)
    previous = previous_publish and previous_publish["row_counts_by_season"]
    without_baseline = False
    if baseline_problem:
        if args.without_baseline:
            without_baseline = True
            print(
                f"::warning::{baseline_problem} — publishing without a baseline "
                f"because --without-baseline was given; nothing checks that "
                f"this publish holds as much as the last one."
            )
        else:
            failures.append(
                f"{baseline_problem}. Without it there is no proof that no "
                f"season shrank; rerun with --without-baseline if that is "
                f"intended"
            )
    elif args.without_baseline:
        print(
            "--without-baseline was given but the previous manifest is "
            "readable; checking against it anyway."
        )

    for table in TABLES:
        for season, before in sorted((previous or {}).get(table, {}).items()):
            now = by_season[table].get(season, 0)
            if now >= before:
                continue
            if season in restated:
                print(
                    f"::warning::restating {season} (--restate): {table} "
                    f"goes from {before:,} to {now:,} rows"
                )
                continue
            failures.append(
                f"{table} holds {now:,} rows for {season}, below the "
                f"{before:,} in the previous publish; rerun with --restate "
                f"{season} if that is intended"
            )

    if previous_publish:
        failures.extend(contract_failures(previous_publish, version, columns))

    if failures:
        for failure in failures:
            print(
                f"::error::{failure} — refusing to publish over the existing "
                f"served data. Inspect the build before re-running."
            )
        return 1

    if restated:
        print(f"restated seasons (--restate): {', '.join(restated)}")

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
    #
    # `restated_seasons` and `published_without_baseline` record the overrides
    # this publish ran under, so a shrink that was allowed stays visible to a
    # consumer and to the next run's reader. Both are always written, empty
    # and false on a normal run. The next publish reads only
    # `row_counts_by_season` from here, so a manifest without them is still a
    # valid baseline.
    #
    # `contract_version` and `columns` (#74) let a consumer check the contract
    # it reads, and give the next publish the shape to compare against.
    manifest = {
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": os.environ.get("GITHUB_SHA", "unknown"),
        "seasons": seasons,
        "row_counts": counts,
        "row_counts_by_season": by_season,
        "restated_seasons": restated,
        "published_without_baseline": without_baseline,
        "contract_version": version,
        "columns": columns,
    }
    client.put_object(
        Bucket=BUCKET,
        Key=MANIFEST_KEY,
        Body=json.dumps(manifest, indent=2).encode(),
        ContentType="application/json",
    )
    print(f"published s3://{BUCKET}/{MANIFEST_KEY}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    lines = []
    for table in TABLES:
        breakdown = ", ".join(
            f"{season} {n:,}" for season, n in sorted(by_season[table].items())
        )
        lines.append(f"- `{table}`: {counts[table]:,} rows ({breakdown})")
    for table in TABLES:
        lines.append(
            f"- `{table}` expected from staging: "
            + ", ".join(
                f"{season} {n:,}" for season, n in sorted(expected[table].items())
            )
            + f" — total {sum(expected[table].values()):,}"
        )
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("### Published to served/\n" + "\n".join(lines) + "\n")
    print("\n".join(lines))

    return 0


if __name__ == "__main__":
    sys.exit(main())
