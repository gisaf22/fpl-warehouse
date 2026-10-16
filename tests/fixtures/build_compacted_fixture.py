#!/usr/bin/env python
"""Regenerate tests/fixtures/compacted/ — the compacted element-summary tree the
fixture build reads beside tests/fixtures/raw (#194).

Layout and schema are docs/compacted.md's: one `date=<D>/part.parquet` and one
`_manifest/date=<D>.json` per compacted capture day.

DAYS
----
    2026-08-29  compacted: parquet + manifest         (the "day 1" of #194 B1)
    2026-08-31  parquet, no manifest: a failed day    (the gap, "day 2"; read from raw)
    2026-09-02  compacted: parquet + manifest         (the "day 3"; its one capture is
                                                       07eb06's, never admitted)
    2026-09-06, 2026-09-10, 2026-09-14                not compacted: the raw tail

Every payload of a compacted day in tests/fixtures/raw stays there, so a reader that
read both would stage each of that day's captures twice.

SOURCES
-------
--source s3 (the default) trims production objects: it reads each day's production
parquet and manifest from s3://fpl-data-safari/compacted, keeps only the rows whose
capture key is one of the fixture tree's payloads, and keeps the production schema,
types and `filename` URIs as they are. A payload build_fixtures.py edited
(SYNTHETIC: 233's double) differs from its production object once parsed, apart
from the `_fixture_note` key every fixture payload adds; its row is the fixture payload instead, read as the writer reads it and
unioned by name, so the tree stays one capture history. The manifest keeps
production's fields, with its counts and run_ids set to the trimmed rows'.
Prints each source key and whether its row is production's or the fixture's.
Needs an AWS session:

    eval "$(aws configure export-credentials --format env)"
    uv run python tests/fixtures/build_compacted_fixture.py

--source writer compacts the fixture tree's own payloads with the production writer
(scripts/compact_element_summary.write_parquet) and rewrites `filename` to the
s3:// URI production records. Credential-free; its types are inferred over the
fixture's few files rather than a whole production day, which is what --source s3
exists to cover.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import compact_element_summary as writer  # noqa: E402

RAW = REPO / "tests/fixtures/raw"
DEST = REPO / "tests/fixtures/compacted"
PROD = "s3://fpl-data-safari/compacted"
PROD_RAW = "s3://fpl-data-safari/raw"

MANIFEST_DAYS = ("2026-08-29", "2026-09-02")
UNREFERENCED_DAYS = ("2026-08-31",)


def fixture_files(day: str) -> list[str]:
    return sorted(str(p) for p in RAW.glob(f"fpl/element-summary/*/{day}/*/payload.json"))


def prod_uri(local: str) -> str:
    return f"{PROD_RAW}/{Path(local).relative_to(RAW)}"


def payload_of(text: str) -> dict:
    """A payload as parsed, without the note build_fixtures.py adds to each one."""
    body = json.loads(text)
    body.pop("_fixture_note", None)
    return body


def trim_from_s3(day: str, parquet: Path, manifest: Path) -> None:
    files = fixture_files(day)
    wanted = [prod_uri(f) for f in files]
    con = writer._connect(PROD)
    edited = [
        f for f in files
        if payload_of(Path(f).read_text())
        != payload_of(con.execute("select content from read_text(?)", [prod_uri(f)]).fetchone()[0])
    ]
    for f in files:
        print(f"  {writer.parquet_path(PROD, day)} :: {prod_uri(f)} -> "
              f"{'fixture payload (edited)' if f in edited else 'production row'}")
    fixture_rows = (
        "union all by name select * replace (? || regexp_extract(filename, "
        "'(fpl/element-summary/.*)$', 1) as filename) "
        "from read_json(?, union_by_name = true, filename = true) "
        if edited else ""
    )
    con.execute(
        f"copy (select * from read_parquet(?, hive_partitioning = false) "
        f"where filename in (select unnest(?::varchar[])) "
        f"and filename not in (select unnest(?::varchar[])) {fixture_rows}"
        f"order by filename) to '{parquet}' (format parquet)",
        [writer.parquet_path(PROD, day), wanted, [prod_uri(f) for f in edited]]
        + ([PROD_RAW + "/", edited] if edited else []),
    )
    record = json.loads(
        con.execute("select content from read_text(?)", [writer.manifest_path(PROD, day)])
        .fetchone()[0]
    )
    rows, distinct, run_ids = con.execute(
        "select count(*), count(distinct filename), "
        "list(distinct string_split(filename, '/')[-2] order by 1) "
        f"from read_parquet('{parquet}', hive_partitioning = false)"
    ).fetchone()
    if rows != len(wanted):
        raise SystemExit(f"{day}: production parquet holds {rows} of {len(wanted)} fixture files")
    record.update(payload_files=rows, parquet_rows=rows, distinct_filenames=distinct, run_ids=run_ids)
    manifest.write_text(json.dumps(record, indent=2) + "\n")


def compact_locally(day: str, parquet: Path, manifest: Path) -> None:
    files = fixture_files(day)
    with tempfile.TemporaryDirectory() as tmp:
        written = f"{tmp}/part.parquet"
        writer.write_parquet(files, written)
        con = duckdb.connect()
        con.execute(
            f"copy (select * replace ('{PROD_RAW}/' || "
            f"regexp_extract(filename, '(fpl/element-summary/.*)$', 1) as filename) "
            f"from read_parquet('{written}', hive_partitioning = false) order by filename) "
            f"to '{parquet}' (format parquet)"
        )
    manifest.write_text(
        json.dumps(
            {
                "capture_day": day,
                "payload_files": len(files),
                "parquet_rows": len(files),
                "distinct_filenames": len(files),
                "run_ids": sorted({Path(f).parent.name for f in files}),
                "compacted_at": "2026-10-16T02:53:09Z",
                "git_sha": writer._git_sha(),
            },
            indent=2,
        )
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", choices=("s3", "writer"), default="s3")
    args = parser.parse_args()
    build = trim_from_s3 if args.source == "s3" else compact_locally

    base = DEST / "fpl/element-summary"
    if DEST.exists():
        shutil.rmtree(DEST)
    (base / "_manifest").mkdir(parents=True)
    for day in MANIFEST_DAYS + UNREFERENCED_DAYS:
        (base / f"date={day}").mkdir()
        manifest = base / f"_manifest/date={day}.json"
        build(day, base / f"date={day}/part.parquet", manifest)
        if day in UNREFERENCED_DAYS:
            manifest.unlink()
        print(f"{day}: {'manifest' if manifest.exists() else 'no manifest'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
