"""Compact settled entry-picks gameweeks into one parquet per gameweek (#216 D8).

A gameweek is settled once fpl-ingest's marker for it exists,
`<raw_root>/fpl/_settlement/entry-picks/<gw>/marker.json` (#216 D2). Each
settled, not yet compacted gameweek's payload files,
`<raw_root>/fpl/entry-picks/<season>/<gw>/*/*/*/payload.json`, become

    <dest_root>/fpl/entry-picks/season=<S>/gameweek=<G>/part.parquet
    <dest_root>/fpl/entry-picks/_manifest/season=<S>/gameweek=<G>.json

The parquet is `select * from read_json(<files>, union_by_name = true,
filename = true)`, as for element-summary (docs/compacted.md). The marker's key
carries no season, so its season is the one season of its run's entry-picks
captures for that gameweek (#216 D14). Invalid captures under `_invalid/` are
not payloads and never match the payload glob.

Per gameweek, as compact_element_summary.compact_day: write the parquet, check
payload files = parquet rows = distinct filename, check the files equal the
index keys of their runs with matching sha256, then write the manifest last.
A failed check fails that gameweek only. A gameweek with a manifest is never
rewritten: its picks cannot change once settled. The production destination is
written only by a scheduled run, the element-summary writer's gate.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

from compact_element_summary import (
    DestinationRefused,
    _connect,
    _git_sha,
    _glob,
    _index,
    _key,
    _read_json,
    _sha256_all,
    check_destination,
    write_manifest,
    write_parquet,
)

ENDPOINT = "entry-picks"
MANIFEST_FIELDS = (
    "season",
    "gameweek",
    "payload_files",
    "parquet_rows",
    "distinct_filenames",
    "run_ids",
    "compacted_at",
    "git_sha",
)


@dataclass
class GameweekResult:
    season: str | None
    gameweek: int
    ok: bool
    reason: str = ""


def parquet_path(dest_root: str, season: str, gameweek: int) -> str:
    return f"{dest_root.rstrip('/')}/fpl/{ENDPOINT}/season={season}/gameweek={gameweek}/part.parquet"


def manifest_path(dest_root: str, season: str, gameweek: int) -> str:
    return f"{dest_root.rstrip('/')}/fpl/{ENDPOINT}/_manifest/season={season}/gameweek={gameweek}.json"


def _run_manifest(con, raw_root: str, run_id: str) -> dict | None:
    found = _glob(con, f"{raw_root}/fpl/_manifests/*/{run_id}/manifest.json")
    return _read_json(con, found[0]) if found else None


def marker_season(con, raw_root: str, gameweek: int, run_id: str) -> tuple[str | None, str]:
    """The one season of the marker run's entry-picks captures for the gameweek."""
    manifest = _run_manifest(con, raw_root, run_id)
    index = _index(con, raw_root, run_id, manifest) if manifest else None
    if index is None:
        return None, f"marker run {run_id} has no finalized index"
    seasons = {
        c["season"]
        for c in index
        if c["endpoint"].split("/")[0] == ENDPOINT and c["endpoint"].split("/")[2] == str(gameweek)
    }
    if len(seasons) != 1:
        return None, f"marker run {run_id} indexes seasons {sorted(seasons)} for gameweek {gameweek}"
    return seasons.pop(), ""


def compact_gameweek(
    season: str, gameweek: int, raw_root: str, dest_root: str
) -> GameweekResult:
    raw_root = raw_root.rstrip("/")
    con = _connect(raw_root, dest_root)
    files = _glob(con, f"{raw_root}/fpl/{ENDPOINT}/{season}/{gameweek}/*/*/*/payload.json")
    if not files:
        return GameweekResult(season, gameweek, False, "no payload files")

    run_ids = sorted({_key(raw_root, f).split("/")[7] for f in files})  # raw/fpl/entry-picks/<S>/<G>/<entry>/<day>/<run_id>/payload.json
    expected = {}
    for run_id in run_ids:
        manifest = _run_manifest(con, raw_root, run_id)
        index = _index(con, raw_root, run_id, manifest) if manifest else None
        if index is None:
            return GameweekResult(season, gameweek, False, f"run {run_id} has no finalized index")
        prefix = f"raw/fpl/{ENDPOINT}/{season}/{gameweek}/"
        expected.update({c["key"]: c["content_sha256"] for c in index if c["key"].startswith(prefix)})

    parquet = parquet_path(dest_root, season, gameweek)
    write_parquet(files, parquet)
    rows, distinct = con.execute(
        "select count(*), count(distinct filename) from read_parquet(?, hive_partitioning = false)",
        [parquet],
    ).fetchone()
    if not len(files) == rows == distinct:
        return GameweekResult(
            season, gameweek, False,
            f"{len(files)} payload files, {rows} parquet rows, {distinct} distinct filenames",
        )

    actual = {_key(raw_root, f): sha for f, sha in _sha256_all(files).items()}
    if actual.keys() != expected.keys():
        return GameweekResult(
            season, gameweek, False,
            f"listed but not indexed {sorted(actual.keys() - expected.keys())}; "
            f"indexed but not listed {sorted(expected.keys() - actual.keys())}",
        )
    mismatched = sorted(k for k in actual if actual[k] != expected[k])
    if mismatched:
        return GameweekResult(season, gameweek, False, f"sha256 differs from the index for {mismatched}")

    write_manifest(
        {
            "season": season,
            "gameweek": gameweek,
            "payload_files": len(files),
            "parquet_rows": rows,
            "distinct_filenames": distinct,
            "run_ids": run_ids,
            "compacted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_sha": _git_sha(),
        },
        manifest_path(dest_root, season, gameweek),
    )
    return GameweekResult(season, gameweek, True)


def compact_settled_gameweeks(
    raw_root: str, dest_root: str, event_name: str | None = None
) -> list[GameweekResult]:
    """Compact every marked gameweek that has no compaction manifest yet."""
    if event_name is None:
        event_name = os.environ.get("GITHUB_EVENT_NAME")
    check_destination(dest_root, event_name)
    raw_root = raw_root.rstrip("/")
    con = _connect(raw_root, dest_root)
    compacted = set(_glob(con, f"{dest_root.rstrip('/')}/fpl/{ENDPOINT}/_manifest/*/*.json"))
    results = []
    for marker_file in _glob(con, f"{raw_root}/fpl/_settlement/{ENDPOINT}/*/marker.json"):
        marker = _read_json(con, marker_file)
        gameweek = int(marker["event"])
        season, reason = marker_season(con, raw_root, gameweek, marker["run_id"])
        if season is None:
            results.append(GameweekResult(None, gameweek, False, reason))
            continue
        if manifest_path(dest_root, season, gameweek) in compacted:
            continue
        results.append(compact_gameweek(season, gameweek, raw_root, dest_root))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-root", required=True, help="e.g. s3://fpl-data-safari/raw")
    parser.add_argument("--dest-root", required=True, help="e.g. s3://fpl-data-safari/compacted")
    args = parser.parse_args()
    try:
        results = compact_settled_gameweeks(args.raw_root, args.dest_root)
    except DestinationRefused as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2
    for r in results:
        print(f"entry-picks {r.season} gameweek {r.gameweek}: {'compacted' if r.ok else 'FAILED ' + r.reason}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
