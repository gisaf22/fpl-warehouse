"""Report what a live build actually produced, into the job summary.

Called by .github/workflows/ci.yml's live-tests job immediately after
`dbt run`. Split out of the workflow rather than inlined as a heredoc so it is
lintable by ruff and readable in a diff, matching scripts/publish_served.py.

WHY THIS EXISTS
---------------
The runner's DuckDB dies with the job and nothing exports it, so a CI build's
rows cannot be diffed after the fact the way a local one can. Until now the
only CI-side evidence that a build was correct was "59 tests passed", which is
strong but says nothing about shape — a build reading half the raw tree can
still satisfy every test in the project, because every test is relative to what
was read.

This prints the shape: row count per model, and the per-season breakdown of
each model that carries a season. That makes the first real two-season dispatch
self-evidencing — you can see 2025-26 appear, and see how many rows it brought
— instead of inferring it from a green check.

It reports; it does not assert. There is deliberately no floor and no
threshold here: publish_served.py owns the one guard that protects published
data, and dbt's tests own correctness. A number that looks wrong is for a human
to judge, and a build is not failed by this script.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

# The live build's database, as profiles.yml's `dev` target writes it.
# Overridable so the script can be pointed at a fixture build locally — the
# only way to exercise the multi-season output before a history tree exists
# live. CI never sets it. It must be the database's own path, not a copy
# renamed: DuckDB derives the catalog name from the filename and the
# intermediate models are views that qualify their refs with it, so a renamed
# copy resolves those views against the wrong catalog.
DATABASE = Path(os.environ.get("FPL_WAREHOUSE_DB", ".local/warehouse.duckdb"))

# Every model the DAG builds, in dependency order rather than alphabetically,
# so the summary reads the way the build ran.
MODELS = (
    "stg_player",
    "stg_player_fixture",
    "stg_gameweek",
    "stg_event_status",
    "int_player_gameweek_spine",
    "int_round_ratification",
    "fct_player_fixture",
    "fct_player_gameweek",
)


def season_column(con: duckdb.DuckDBPyConnection, model: str) -> bool:
    """Whether `model` carries a season column.

    Queried rather than hardcoded: every model carries season today, and a
    future one that does not should drop out of the per-season table quietly
    rather than fail the step.
    """
    cols = con.sql(
        "select column_name from duckdb_columns "
        "where table_name = ? and schema_name = 'main'",
        params=[model],
    ).fetchall()
    return ("season",) in cols


def main() -> int:
    if not DATABASE.exists():
        print(f"::warning::{DATABASE} does not exist — nothing to summarise")
        return 0

    con = duckdb.connect(str(DATABASE), read_only=True)

    totals: dict[str, int] = {}
    per_season: dict[str, list[tuple[str, int]]] = {}

    for model in MODELS:
        try:
            totals[model] = con.sql(f"select count(*) from main.{model}").fetchone()[0]
        except duckdb.Error as exc:
            # A model missing from the database is worth saying out loud, but it
            # is dbt's job to fail the build over it, not this script's.
            print(f"::warning::could not read main.{model}: {exc}")
            continue

        if season_column(con, model):
            per_season[model] = con.sql(
                f"select season, count(*) from main.{model} "
                "group by season order by season"
            ).fetchall()

    seasons = sorted({s for rows in per_season.values() for s, _ in rows})

    lines = ["### Live build shape", "", "| model | rows |", "| --- | ---: |"]
    lines += [f"| `{m}` | {n:,} |" for m, n in totals.items()]

    if seasons:
        lines += [
            "",
            f"**Seasons present: {', '.join(seasons)}**",
            "",
            "| model | " + " | ".join(seasons) + " |",
            "| --- |" + " ---: |" * len(seasons),
        ]
        for model, rows in per_season.items():
            counts = dict(rows)
            cells = " | ".join(f"{counts.get(s, 0):,}" for s in seasons)
            lines += [f"| `{model}` | {cells} |"]

    # A single season is the normal case and not worth a callout; more than one
    # means a history tree was read, which is the thing worth seeing at a glance.
    if len(seasons) > 1:
        lines += ["", f"> Multi-season build — {len(seasons)} seasons read."]

    report = "\n".join(lines)
    print(report)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
