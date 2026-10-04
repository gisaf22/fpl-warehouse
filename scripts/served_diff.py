"""Compare the served tables of two builds against live S3 (#102).

Called by .github/workflows/served_diff.yml. Two subcommands:

- ``export OUT_DIR --seconds N`` runs after a ``dbt build`` and writes the five
  served tables to OUT_DIR as parquet, plus build.json with the build's
  wall-clock seconds and the newest run_id its staging read. It publishes
  nothing.
- ``diff BEFORE AFTER`` compares two exported directories, per table and per
  season, both ways with EXCEPT ALL. It writes a markdown report to stdout and
  exits 1 on any difference, a missing table, or an inconclusive comparison:
  two builds whose newest run_ids differ read different raw trees, so a
  difference between them is not attributable to the code.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from publish_served import DATABASE, TABLES

# Every staging model carrying the capture's run_id. The newest across them is
# the newest raw run the build read.
RUN_ID_MODELS = (
    "stg_player_fixture",
    "stg_player",
    "stg_team",
    "stg_position",
    "stg_gameweek",
    "stg_fixture",
    "stg_gameweek_status",
)

# Differing rows written to the report per table and season and direction.
# The full sets are in the uploaded artifact's parquet; the report is a summary.
SHOWN_ROWS = 20


@dataclass
class Difference:
    table: str
    season: str
    only_before: list[tuple] = field(default_factory=list)
    only_after: list[tuple] = field(default_factory=list)


@dataclass
class Report:
    before: dict
    after: dict
    inconclusive: str | None = None
    missing: list[str] = field(default_factory=list)
    counts: dict[str, dict[str, tuple[int, int]]] = field(default_factory=dict)
    differences: list[Difference] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return bool(self.inconclusive or self.missing or self.differences)

    def markdown(self) -> str:
        lines = [
            "### Served diff",
            "",
            "| | before | after |",
            "|---|---|---|",
            f"| build seconds | {self.before.get('seconds')} | {self.after.get('seconds')} |",
            f"| newest run_id | `{self.before.get('newest_run_id')}` "
            f"| `{self.after.get('newest_run_id')}` |",
            "",
        ]
        if self.inconclusive:
            lines.append(f"**Inconclusive:** {self.inconclusive}")
            return "\n".join(lines) + "\n"
        for table in self.missing:
            lines.append(f"**Missing:** `{table}` is absent from one side.")
        lines += [
            "| table | season | before rows | after rows | only before | only after |",
            "|---|---|---|---|---|---|",
        ]
        by_key = {(d.table, d.season): d for d in self.differences}
        for table, seasons in self.counts.items():
            for season, (n_before, n_after) in seasons.items():
                d = by_key.get((table, season), Difference(table, season))
                lines.append(
                    f"| {table} | {season} | {n_before} | {n_after} "
                    f"| {len(d.only_before)} | {len(d.only_after)} |"
                )
        for d in self.differences:
            lines += ["", f"#### `{d.table}` {d.season}"]
            for label, rows in (
                ("only before", d.only_before),
                ("only after", d.only_after),
            ):
                for row in rows[:SHOWN_ROWS]:
                    lines.append(f"- {label}: `{row}`")
                if len(rows) > SHOWN_ROWS:
                    lines.append(f"- {label}: … {len(rows) - SHOWN_ROWS} more")
        lines += ["", f"**Result:** {'differs' if self.failed else 'identical'}"]
        return "\n".join(lines) + "\n"


def compare(before: Path, after: Path) -> Report:
    meta_before = json.loads((before / "build.json").read_text())
    meta_after = json.loads((after / "build.json").read_text())
    report = Report(meta_before, meta_after)

    if meta_before.get("newest_run_id") != meta_after.get("newest_run_id"):
        report.inconclusive = (
            "the two builds read different newest run_ids, so an ingest run "
            "landed between them. Re-dispatch."
        )
        return report

    connection = duckdb.connect()
    for table in TABLES:
        a, b = before / f"{table}.parquet", after / f"{table}.parquet"
        if not (a.exists() and b.exists()):
            report.missing.append(table)
            continue
        rel_a, rel_b = f"read_parquet('{a}')", f"read_parquet('{b}')"
        seasons = [
            s
            for (s,) in connection.execute(
                f"SELECT season FROM {rel_a} UNION SELECT season FROM {rel_b} ORDER BY 1"
            ).fetchall()
        ]
        report.counts[table] = {}
        for season in seasons:
            side_a = f"(SELECT * FROM {rel_a} WHERE season = $season)"
            side_b = f"(SELECT * FROM {rel_b} WHERE season = $season)"
            params = {"season": season}

            def rows(query: str) -> list[tuple]:
                return connection.execute(query, params).fetchall()

            report.counts[table][season] = (
                rows(f"SELECT count(*) FROM {side_a}")[0][0],
                rows(f"SELECT count(*) FROM {side_b}")[0][0],
            )
            only_before = rows(f"{side_a} EXCEPT ALL {side_b} ORDER BY ALL")
            only_after = rows(f"{side_b} EXCEPT ALL {side_a} ORDER BY ALL")
            if only_before or only_after:
                report.differences.append(
                    Difference(table, season, only_before, only_after)
                )
    return report


def export(out_dir: Path, seconds: int) -> int:
    if not DATABASE.exists():
        print(f"::error::no database at {DATABASE} — did `dbt build` run?")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(DATABASE), read_only=True)
    for table in TABLES:
        connection.execute(
            f"COPY main.{table} TO '{out_dir / table}.parquet' (FORMAT PARQUET)"
        )
    newest = connection.execute(
        "SELECT max(run_id) FROM ("
        + " UNION ALL ".join(
            f"SELECT max(run_id) AS run_id FROM main.{m}" for m in RUN_ID_MODELS
        )
        + ")"
    ).fetchone()[0]
    (out_dir / "build.json").write_text(
        json.dumps({"seconds": seconds, "newest_run_id": newest})
    )
    print(f"exported {len(TABLES)} tables to {out_dir}; newest run_id {newest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p_export = sub.add_parser("export")
    p_export.add_argument("out_dir", type=Path)
    p_export.add_argument("--seconds", type=int, required=True)
    p_diff = sub.add_parser("diff")
    p_diff.add_argument("before", type=Path)
    p_diff.add_argument("after", type=Path)
    args = parser.parse_args(argv)

    if args.command == "export":
        return export(args.out_dir, args.seconds)

    report = compare(args.before, args.after)
    print(report.markdown())
    if report.inconclusive:
        print(f"::error::served diff inconclusive: {report.inconclusive}")
    elif report.failed:
        print("::error::served output differs between the two builds")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main())
