"""Report one live-tests build's memory measurements, into the job summary (#190 AC2).

#183's experiments rebuild the warehouse at a capture cutoff and compare memory
against capture count. Called by ci.yml's live-tests job after `dbt run`, on
every dispatch, with or without a cutoff. It reports and never asserts.

Inputs, all written earlier in the job:
  --time-log      stderr of `/usr/bin/time -v` around `dbt run`
  --samples       scripts/sample_build_memory.sh's CSV (epoch, RSS KiB, spill bytes)
  --settings      `dbt show` JSON holding memory_limit and temp_directory, read
                  through dbt's own connection so the profile's settings apply
  --run-results   dbt's target/run_results.json from the build
  --cutoff        the capture_cutoff the build ran with, or empty

RSS and spill are the primary signals. Build seconds are secondary: a cutoff
run lists each source once from the pre-hook, so its time is not strictly
comparable with an uncut build (#190 D1). Per-model peaks are the highest
sample taken while each model ran. Models overlap at 32 threads, so a peak is
attributed by timeline, not measured per model (#190 D4).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
from pathlib import Path

import duckdb

# The live build's database; overridable, as in summarize_build.py, so the
# script can be run against a fixture build locally. CI never sets it.
DATABASE = os.environ.get("FPL_WAREHOUSE_DB", ".local/warehouse.duckdb")
GIB = 1024**3


def time_log(path: Path) -> tuple[float | None, float | None]:
    """Peak RSS in GiB and wall-clock seconds from `/usr/bin/time -v`."""
    text = path.read_text() if path.exists() else ""
    rss = re.search(r"Maximum resident set size \(kbytes\): (\d+)", text)
    wall = re.search(r"Elapsed \(wall clock\) time .*?: ([\d:.]+)", text)
    seconds = None
    if wall:
        seconds = 0.0
        for part in wall.group(1).split(":"):
            seconds = seconds * 60 + float(part)
    return (int(rss.group(1)) * 1024 / GIB if rss else None), seconds


def samples(path: Path) -> list[tuple[float, int, int]]:
    if not path.exists():
        return []
    with path.open() as f:
        return [(float(t), int(r) * 1024, int(s)) for t, r, s in csv.reader(f)]


def model_windows(path: Path) -> list[tuple[str, float, float]]:
    windows = []
    for result in json.loads(path.read_text()).get("results", []):
        for timing in result.get("timing", []):
            if timing.get("name") == "execute" and timing.get("started_at"):
                start, end = (
                    dt.datetime.fromisoformat(timing[k].replace("Z", "+00:00")).timestamp()
                    for k in ("started_at", "completed_at")
                )
                windows.append((result["unique_id"].split(".")[-1], start, end))
    return windows


def staged_captures(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    tables = [
        name
        for (name,) in con.sql(
            "select table_name from information_schema.columns "
            "where column_name = 'capture_key' and table_name like 'stg_%'"
        ).fetchall()
    ]
    keys = {
        key
        for table in tables
        for (key,) in con.sql(f"select distinct capture_key from {table}").fetchall()
    }
    counts: dict[str, int] = {}
    for key in keys:
        parts = key.split("/")
        endpoint = parts[parts.index("fpl") + 1]
        counts[endpoint] = counts.get(endpoint, 0) + 1
    return dict(sorted(counts.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    for name in ("--time-log", "--samples", "--settings", "--run-results"):
        parser.add_argument(name, type=Path, required=True)
    parser.add_argument("--cutoff", default="")
    args = parser.parse_args()

    peak_rss, seconds = time_log(args.time_log)
    sampled = samples(args.samples)
    settings = {}
    if args.settings.exists():
        rows = json.loads(args.settings.read_text()).get("show", [])
        settings = rows[0] if rows else {}

    con = duckdb.connect(DATABASE, read_only=True)
    captures = staged_captures(con)
    (fixture_rows,) = con.sql("select count(*) from stg_player_fixture").fetchone()

    fmt = lambda v, f: "n/a" if v is None else f.format(v)  # noqa: E731
    print(f"## Build memory experiment — capture cutoff: {args.cutoff or 'none (latest)'}\n")
    print("| Measure | Value |\n|---|---|")
    print(f"| Peak RSS (`time -v`) | {fmt(peak_rss, '{:.2f} GiB')} |")
    sampled_rss = max(r for _, r, _ in sampled) / GIB if sampled else None
    sampled_spill = max(s for _, _, s in sampled) if sampled else None
    print(f"| Peak RSS (sampled, 5s) | {fmt(sampled_rss, '{:.2f} GiB')} |")
    print(f"| Peak spill (sampled, 5s) | {fmt(sampled_spill, '{:,} bytes')} |")
    print(f"| `memory_limit` | {settings.get('memory_limit', 'n/a')} |")
    print(f"| `temp_directory` | {settings.get('temp_directory', 'n/a')} |")
    print(f"| Build seconds (`dbt run`, secondary) | {fmt(seconds, '{:.0f}')} |")
    for endpoint, count in captures.items():
        print(f"| Staged captures: {endpoint} | {count:,} |")
    print(f"| Staged captures: total | {sum(captures.values()):,} |")
    print(f"| `stg_player_fixture` rows | {fixture_rows:,} |")

    print("\n### Per-model peak RSS, attributed by timeline\n")
    print("Models overlap at 32 threads, so each figure is the highest sample taken "
          "while the model ran, not the model's own use.\n")
    print("| Model | Seconds | Peak RSS (GiB) |\n|---|---|---|")
    for model, start, end in sorted(model_windows(args.run_results), key=lambda w: w[1]):
        during = [r for t, r, _ in sampled if start - 5 <= t <= end]
        peak = f"{max(during) / GIB:.2f}" if during else "no sample"
        print(f"| {model} | {end - start:.1f} | {peak} |")


if __name__ == "__main__":
    main()
