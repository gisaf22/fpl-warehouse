"""Staging reads compacted element-summary days from parquet and the rest from raw (#194).

The element-summary source is the compaction manifest's days read from
`compacted/`, union all by name the raw tail (every capture day the manifest
does not list), union all by name the 2025-26 history-port captures (#78 W8, W10).
A staging pre-hook derives the tail from the manifest. Compacted days must be
read: an unreadable manifest or a listed day without its parquet fails the build
(D1). `staging_read_mode: raw` forces the all-raw read, only on a manual dispatch.

The parse tests read the source's rendered `external_location` from the manifest,
as test_capture_cutoff.py does. The build tests build staging from the fixture
trees (tests/fixtures/raw, tests/fixtures/history, tests/fixtures/compacted) into
a temporary database through a copy of the `fixtures` profile, so
`.local/fixtures.duckdb` is untouched. A variant compacted tree is a copy of
tests/fixtures/compacted under tmp_path with one change.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest
import yaml

from test_capture_cutoff import GLOB, UNCUT

REPO = Path(__file__).resolve().parents[2]
COMPACTED = REPO / "tests/fixtures/compacted"
DAYS = COMPACTED / "fpl/element-summary"

COMPACTED_READ = "query(getvariable('element_summary_read'))"
STAGED = ("stg_player_history_capture", "stg_player_fixture")


def dbt(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["dbt", "--no-use-colors", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def element_summary_location(
    tmp_path: Path, target: str, dbt_vars: dict | None = None, event: str | None = None
) -> subprocess.CompletedProcess | str:
    args = ["parse", "--target", target, "--target-path", str(tmp_path)]
    if dbt_vars:
        args += ["--vars", json.dumps(dbt_vars)]
    result = dbt(*args, env={"GITHUB_EVENT_NAME": event} if event is not None else None)
    if result.returncode != 0:
        return result
    sources = json.loads((tmp_path / "manifest.json").read_text())["sources"]
    return next(s["meta"]["external_location"] for s in sources.values() if s["name"] == "element_summary")


def build(
    tmp_path: Path, name: str, dbt_vars: dict | None = None, event: str | None = None
) -> tuple[subprocess.CompletedProcess, Path]:
    """Seed, then build staging's element-summary models and their parents."""
    work = tmp_path / name
    work.mkdir()
    db = work / "build.duckdb"
    profiles = yaml.safe_load((REPO / "profiles.yml").read_text())
    profiles["fpl_warehouse"]["outputs"]["fixtures"]["path"] = str(db)
    (work / "profiles.yml").write_text(yaml.safe_dump(profiles))
    common = [
        "--target", "fixtures",
        "--profiles-dir", str(work),
        "--target-path", str(work / "target"),
        "--log-path", str(work / "logs"),
    ]
    env = {"GITHUB_EVENT_NAME": event} if event is not None else None
    seeded = dbt("seed", *common, env=env)
    assert seeded.returncode == 0, seeded.stdout + seeded.stderr
    args = ["run", "--select", "+stg_player_fixture", *common]
    if dbt_vars:
        args += ["--vars", json.dumps(dbt_vars)]
    return dbt(*args, env=env), db


def built(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stdout + result.stderr


def typed_rows(db: Path, table: str) -> list[tuple]:
    """Every column with its type, but stg_player_history_capture's raw `history`.

    That list keeps the types the source read inferred (docs/compacted.md: the
    schema follows the source). A production day's parquet infers them over the
    whole day, so a trimmed fixture day can be wider than the same payloads read
    alone (`bps` 17.0, not 17: #78 W8's residual risk). stg_player_fixture casts
    every field of it, and is compared typed.
    """
    con = duckdb.connect(str(db), read_only=True)
    columns = [c for (c,) in con.sql(
        f"select column_name from information_schema.columns "
        f"where table_name = '{table}' and column_name <> 'history' order by ordinal_position"
    ).fetchall()]
    select = ", ".join(f"{c}::varchar, typeof({c})" for c in columns)
    return sorted(con.sql(f"select {select} from {table}").fetchall(), key=repr)


def staged_keys(db: Path) -> set[str]:
    con = duckdb.connect(str(db), read_only=True)
    return {k for (k,) in con.sql("select capture_key from stg_player_history_capture").fetchall()}


def day_of(capture_key: str) -> str:
    return capture_key.split("/")[-3]


def compacted_copy(tmp_path: Path) -> Path:
    root = tmp_path / "compacted"
    shutil.copytree(COMPACTED, root)
    return root


def corrupt_root(tmp_path: Path) -> Path:
    """A compacted tree whose every manifest is unreadable."""
    root = compacted_copy(tmp_path)
    for manifest in (root / "fpl/element-summary/_manifest").glob("*.json"):
        manifest.write_text("not json {")
    return root


@pytest.fixture(scope="module")
def all_raw(tmp_path_factory) -> Path:
    """Today's read: the override on a manual dispatch, with compacted/ unreadable."""
    tmp = tmp_path_factory.mktemp("all_raw")
    result, db = build(
        tmp, "build",
        {"staging_read_mode": "raw", "compacted_root": str(corrupt_root(tmp))},
        event="workflow_dispatch",
    )
    built(result)
    return db


@pytest.fixture(scope="module")
def compacted_build(tmp_path_factory) -> tuple[subprocess.CompletedProcess, Path]:
    result, db = build(tmp_path_factory.mktemp("compacted"), "build")
    built(result)
    return result, db


# --- the rendered source -----------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("target", ["fixtures", "dev"])
def test_the_element_summary_source_reads_the_pre_hooks_compacted_union(tmp_path, target):
    location = element_summary_location(tmp_path, target)

    assert location == COMPACTED_READ


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("target", ["fixtures", "dev"])
def test_a_cutoff_reads_raw_and_history_and_no_parquet(tmp_path, target):
    location = element_summary_location(tmp_path, target, {"capture_cutoff": "2026-09-15"})

    assert "getvariable('capture_cutoff_files_element_summary')" in location
    assert "parquet" not in location
    assert "element_summary_read" not in location


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("target", ["fixtures", "dev"])
def test_the_raw_override_on_a_manual_dispatch_renders_todays_globs(tmp_path, target):
    location = element_summary_location(
        tmp_path, target, {"staging_read_mode": "raw"}, event="workflow_dispatch"
    )

    assert GLOB.findall(location) == UNCUT[target]["element_summary"]
    assert "parquet" not in location


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("event", ["schedule", "push", "pull_request"])
def test_the_raw_override_is_refused_off_a_manual_dispatch(tmp_path, event):
    result = element_summary_location(tmp_path, "fixtures", {"staging_read_mode": "raw"}, event=event)

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode != 0
    assert "staging_read_mode" in result.stdout + result.stderr
    assert "workflow_dispatch" in result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_the_raw_override_is_allowed_on_a_local_run(tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "GITHUB_EVENT_NAME"}
    result = subprocess.run(
        ["dbt", "--no-use-colors", "parse", "--target", "fixtures", "--target-path", str(tmp_path),
         "--vars", json.dumps({"staging_read_mode": "raw"})],
        cwd=REPO, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    sources = json.loads((tmp_path / "manifest.json").read_text())["sources"]
    location = next(s["meta"]["external_location"] for s in sources.values() if s["name"] == "element_summary")

    assert GLOB.findall(location) == UNCUT["fixtures"]["element_summary"]


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("mode", ["compacted", "RAW", "json"])
def test_an_unknown_read_mode_fails_the_parse_naming_the_var(tmp_path, mode):
    result = element_summary_location(
        tmp_path, "fixtures", {"staging_read_mode": mode}, event="workflow_dispatch"
    )

    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode != 0
    assert "staging_read_mode" in result.stdout + result.stderr


# --- what a build stages -----------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("table", STAGED)
def test_the_compacted_read_stages_exactly_what_the_all_raw_read_stages(
    compacted_build, all_raw, table
):
    _, db = compacted_build

    assert typed_rows(db, table) == typed_rows(all_raw, table)


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_the_fixture_build_stages_every_kind_of_day(compacted_build):
    _, db = compacted_build
    days = {day_of(k) for k in staged_keys(db) if k.startswith("raw/")}

    # Not vacuous: a compacted day, the gap between two compacted days (its
    # parquet has no manifest), the raw tail, and the history-port captures.
    assert (DAYS / "_manifest/date=2026-08-29.json").exists()
    assert not (DAYS / "_manifest/date=2026-08-31.json").exists()
    assert (DAYS / "date=2026-08-31/part.parquet").exists()
    assert {"2026-08-29", "2026-08-31", "2026-09-06", "2026-09-14"} <= days
    assert any(k.startswith("history/2025-26/") for k in staged_keys(db))


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_a_fixture_build_reads_no_s3_object(compacted_build):
    """The compacted read's listings and reads stay inside the fixture trees.

    The parquet's `filename` values are production s3:// URIs by design, so
    this reads the statements the build ran, not the staged filenames.
    """
    result, _ = compacted_build
    log = (Path(result.args[result.args.index("--log-path") + 1]) / "dbt.log").read_text()
    statements = [
        line for line in log.splitlines()
        if any(f in line for f in ("glob(", "read_text(", "read_parquet(", "read_json("))
    ]

    assert statements
    assert not [s for s in statements if "s3://" in s]


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_a_manifest_day_is_read_from_its_parquet_only(tmp_path):
    root = compacted_copy(tmp_path)
    parquet = root / "fpl/element-summary/date=2026-08-29/part.parquet"
    con = duckdb.connect()
    dropped = con.sql(
        f"select filename from read_parquet('{parquet}', hive_partitioning = false) "
        f"order by filename limit 1"
    ).fetchone()[0]
    con.execute(
        f"copy (select * from read_parquet('{parquet}', hive_partitioning = false) "
        f"where filename <> '{dropped}') to '{tmp_path}/kept.parquet' (format parquet)"
    )
    shutil.move(tmp_path / "kept.parquet", parquet)

    result, db = build(tmp_path, "build", {"compacted_root": str(root)})
    built(result)
    keys = staged_keys(db)
    dropped_key = "raw/" + dropped.split("/raw/", 1)[1]

    # Its payload is still in tests/fixtures/raw; a reader of both would stage it.
    assert dropped_key not in keys
    assert {k for k in keys if day_of(k) == "2026-08-29"}


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
@pytest.mark.parametrize("table", STAGED)
def test_an_empty_manifest_reads_every_day_from_raw(tmp_path, all_raw, table):
    empty = tmp_path / "empty"
    empty.mkdir()

    result, db = build(tmp_path, "build", {"compacted_root": str(empty)})
    built(result)

    assert typed_rows(db, table) == typed_rows(all_raw, table)


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_a_cutoff_build_never_reads_compacted(tmp_path):
    cutoff = "2026-09-06"
    result, db = build(
        tmp_path, "build", {"capture_cutoff": cutoff, "compacted_root": str(corrupt_root(tmp_path))}
    )
    built(result)
    days = {day_of(k) for k in staged_keys(db) if k.startswith("raw/")}

    assert "2026-08-29" in days
    assert all(d < cutoff for d in days)


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_an_unreadable_manifest_fails_the_build_naming_it(tmp_path):
    root = compacted_copy(tmp_path)
    manifest = root / "fpl/element-summary/_manifest/date=2026-08-29.json"
    manifest.write_text("not json {")

    result, _ = build(tmp_path, "build", {"compacted_root": str(root)})
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "unreadable" in output
    assert "date=2026-08-29.json" in output
    assert "staging_read_mode" in output


@pytest.mark.integration
@pytest.mark.covers("#194 AC1")
def test_a_listed_day_without_its_parquet_fails_the_build_naming_it(tmp_path):
    root = compacted_copy(tmp_path)
    (root / "fpl/element-summary/date=2026-09-02/part.parquet").unlink()

    result, _ = build(tmp_path, "build", {"compacted_root": str(root)})
    output = result.stdout + result.stderr

    assert result.returncode != 0
    assert "2026-09-02" in output
    assert "part.parquet" in output
    assert "missing" in output
    assert "staging_read_mode" in output


@pytest.mark.integration
@pytest.mark.covers("#194 AC2")
def test_a_filename_in_both_parquet_and_the_raw_tail_fails_the_build(tmp_path):
    root = compacted_copy(tmp_path)
    parquet = root / "fpl/element-summary/date=2026-08-29/part.parquet"
    tail_file = sorted(
        (REPO / "tests/fixtures/raw").glob("fpl/element-summary/*/2026-09-06/*/payload.json")
    )[0]
    overlap = "s3://fpl-data-safari/raw/" + str(tail_file.relative_to(REPO / "tests/fixtures/raw"))
    con = duckdb.connect()
    con.execute(
        f"copy (select * from read_parquet('{parquet}', hive_partitioning = false) "
        f"union all by name select * replace ('{overlap}' as filename) "
        f"from read_json('{tail_file}', union_by_name = true, filename = true)) "
        f"to '{tmp_path}/overlap.parquet' (format parquet)"
    )
    shutil.move(tmp_path / "overlap.parquet", parquet)

    result, db = build(tmp_path, "build", {"compacted_root": str(root)})
    built(result)
    work = db.parent
    tested = dbt(
        "test", "--select", "stg_player_history_capture", "--indirect-selection", "cautious",
        "--target", "fixtures", "--profiles-dir", str(work),
        "--target-path", str(work / "target"), "--log-path", str(work / "logs"),
    )
    output = tested.stdout + tested.stderr

    assert tested.returncode != 0
    assert "FAIL" in output and "unique_stg_player_history_capture_capture_key" in output
