"""The element-summary compaction writer: given days, write parquet then manifest (#193).

`compact_days` compacts an explicit list of capture days from a raw root to a
destination root. Per day it writes
`<dest>/fpl/element-summary/date=<D>/part.parquet`, reconciles it, and only then
writes `<dest>/fpl/element-summary/_manifest/date=<D>.json`. Day selection and
workflow wiring are #198's. Every test here reads a synthetic tree under tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

import compact_element_summary as writer
from compact_element_summary import (
    MANIFEST_FIELDS,
    DestinationRefused,
    check_destination,
    compact_days,
    manifest_path,
    manifest_problems,
    parquet_path,
    runs_writer,
    workflow_problems,
)
from compaction_tree import Capture, Run, build_tree, history_row

REPO = Path(__file__).resolve().parents[2]
PROD = "s3://fpl-data-safari/compacted"
D1, D2 = "2026-09-20", "2026-09-21"


def payload_files(raw: Path, day: str) -> list[str]:
    return sorted(str(p) for p in raw.glob(f"fpl/element-summary/*/{day}/*/payload.json"))


def two_day_tree(raw: Path) -> None:
    """Day 1: expected_goals all integers, plus a capture with empty history[].
    Day 2: expected_goals has decimals."""
    build_tree(
        raw,
        [
            Run("20260920T190000Z-aaaaaa", D1, [
                Capture(1, [history_row(1, 0), history_row(2, 1)], "2026-09-20T19:00:01Z"),
                Capture(2, [], "2026-09-20T19:00:02Z"),
            ]),
            Run("20260921T190000Z-bbbbbb", D2, [
                Capture(1, [history_row(1, 0.35), history_row(2, 1.2)], "2026-09-21T19:00:01Z"),
                Capture(3, [history_row(3, 0)], "2026-09-21T19:00:02Z"),
            ]),
        ],
    )


def same_relation(con, left: str, right: str) -> None:
    left, right = f"select * from {left}", f"select * from {right}"
    assert con.sql(f"describe {left}").fetchall() == con.sql(f"describe {right}").fetchall()
    assert con.sql(f"select count(*) from ({left})").fetchone()[0] > 0
    for a, b in ((left, right), (right, left)):
        assert con.sql(f"select count(*) from ({a} except all {b})").fetchone()[0] == 0


# --- A2: read equivalence -------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#193 AC2")
@pytest.mark.parametrize("day", [D1, D2])
def test_a_days_parquet_equals_the_json_read_of_its_files(tmp_path, day):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    assert compact_days([day], raw_root=str(raw), dest_root=str(dest))[day].ok
    con = duckdb.connect()
    files = payload_files(raw, day)
    same_relation(
        con,
        f"read_parquet('{parquet_path(str(dest), day)}', hive_partitioning = false)",
        f"read_json({files}, union_by_name = true, filename = true)",
    )


@pytest.mark.unit
@pytest.mark.covers("#193 AC2")
def test_the_empty_history_capture_is_a_row_with_its_filename(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    empty = str(raw / f"fpl/element-summary/2/{D1}/20260920T190000Z-aaaaaa/payload.json")
    rows = duckdb.sql(
        f"select len(history) from read_parquet('{parquet_path(str(dest), D1)}', "
        f"hive_partitioning = false) where filename = '{empty}'"
    ).fetchall()
    assert rows == [(0,)]


@pytest.mark.unit
@pytest.mark.covers("#193 AC2")
def test_both_days_parquet_read_together_equals_the_json_read_of_every_file(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    results = compact_days([D1, D2], raw_root=str(raw), dest_root=str(dest))
    assert results[D1].ok and results[D2].ok
    parquets = [parquet_path(str(dest), D1), parquet_path(str(dest), D2)]
    files = payload_files(raw, D1) + payload_files(raw, D2)
    same_relation(
        duckdb.connect(),
        f"read_parquet({parquets}, union_by_name = true, hive_partitioning = false)",
        f"read_json({files}, union_by_name = true, filename = true)",
    )


@pytest.mark.unit
@pytest.mark.covers("#193 AC2")
def test_the_partition_is_in_the_path_only(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    path = parquet_path(str(dest), D1)
    assert path == f"{dest}/fpl/element-summary/date={D1}/part.parquet"
    columns = {
        r[0] for r in duckdb.sql(f"describe select * from read_parquet('{path}', "
                                 "hive_partitioning = false)").fetchall()
    }
    assert "date" not in columns


# --- A3: per-day write ----------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#193 AC3")
def test_a_run_spanning_midnight_stays_under_its_capture_day(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [
        Run("20260920T235000Z-cccccc", D1, [
            Capture(1, [history_row(1, 0)], "2026-09-20T23:55:00Z"),
            Capture(2, [history_row(1, 0)], "2026-09-21T00:10:00Z"),
        ]),
    ])
    assert compact_days([D1], raw_root=str(raw), dest_root=str(dest))[D1].ok
    count = duckdb.sql(
        f"select count(*) from read_parquet('{parquet_path(str(dest), D1)}', "
        "hive_partitioning = false)"
    ).fetchone()[0]
    assert count == 2
    assert Path(manifest_path(str(dest), D1)).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC3")
def test_a_capture_day_unlike_its_runs_extraction_date_fails_the_day(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [
        Run("20260920T190000Z-dddddd", D1, [Capture(1, [history_row(1, 0)], "x")]),
        # Keyed under D2, but its run manifest says D1.
        Run("20260921T010000Z-eeeeee", D1, [Capture(2, [history_row(1, 0)], "x")],
            capture_day=D2),
    ])
    results = compact_days([D2], raw_root=str(raw), dest_root=str(dest))
    assert not results[D2].ok
    assert "extraction_date" in results[D2].reason
    assert not Path(manifest_path(str(dest), D2)).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC3")
def test_a_crash_before_the_manifest_leaves_no_entry_and_the_next_run_recompacts(
    tmp_path, monkeypatch
):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)

    def crash(*args, **kwargs):
        raise RuntimeError("killed between parquet and manifest")

    with monkeypatch.context() as m:
        m.setattr(writer, "write_manifest", crash)
        with pytest.raises(RuntimeError):
            compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    assert Path(parquet_path(str(dest), D1)).exists()
    assert not Path(manifest_path(str(dest), D1)).exists()

    assert compact_days([D1], raw_root=str(raw), dest_root=str(dest))[D1].ok
    assert Path(manifest_path(str(dest), D1)).exists()


# --- A4: reconciliation ---------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
@pytest.mark.parametrize("index", ["manifest", "catalog"])
def test_a_day_reconciled_against_its_runs_index_is_added_to_the_manifest(tmp_path, index):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [
        Run("20260920T190000Z-ffffff", D1,
            [Capture(1, [history_row(1, 0)], "x"), Capture(2, [], "x")], index=index),
    ])
    assert compact_days([D1], raw_root=str(raw), dest_root=str(dest))[D1].ok
    entry = json.loads(Path(manifest_path(str(dest), D1)).read_text())
    assert manifest_problems(entry) == []
    assert entry["payload_files"] == entry["parquet_rows"] == entry["distinct_filenames"] == 2
    assert entry["capture_day"] == D1
    assert entry["run_ids"] == ["20260920T190000Z-ffffff"]


def valid_manifest() -> dict:
    return {
        "capture_day": D1,
        "payload_files": 2,
        "parquet_rows": 2,
        "distinct_filenames": 2,
        "run_ids": ["20260920T190000Z-ffffff"],
        "compacted_at": "2026-10-15T19:45:00Z",
        "git_sha": "0" * 40,
    }


@pytest.mark.unit
@pytest.mark.covers("#193 AC4")
def test_the_manifest_schema_is_exactly_the_pinned_fields():
    assert MANIFEST_FIELDS == (
        "capture_day", "payload_files", "parquet_rows", "distinct_filenames",
        "run_ids", "compacted_at", "git_sha",
    )
    assert manifest_problems(valid_manifest()) == []


@pytest.mark.unit
@pytest.mark.covers("#193 AC4")
@pytest.mark.parametrize("missing", list(valid_manifest()))
def test_a_manifest_missing_a_field_is_flagged(missing):
    record = valid_manifest()
    del record[missing]
    assert any(missing in p for p in manifest_problems(record))


@pytest.mark.unit
@pytest.mark.covers("#193 AC4")
def test_a_manifest_with_an_extra_field_is_flagged():
    record = valid_manifest() | {"file_count": 2}
    assert any("file_count" in p for p in manifest_problems(record))


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
def test_a_missing_parquet_row_fails_the_day(tmp_path, monkeypatch):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    real_write = writer.write_parquet

    def drop_a_row(files, path):
        real_write(files, path)
        con = duckdb.connect()
        con.sql(f"copy (select * from read_parquet('{path}', hive_partitioning = false) "
                f"limit 1) to '{path}.tmp' (format parquet)")
        Path(f"{path}.tmp").replace(path)

    monkeypatch.setattr(writer, "write_parquet", drop_a_row)
    results = compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    assert not results[D1].ok
    assert not Path(manifest_path(str(dest), D1)).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
@pytest.mark.parametrize("index", ["manifest", "catalog"])
def test_a_listed_payload_file_not_in_the_index_fails_the_day(tmp_path, index):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [
        Run("20260920T190000Z-gggggg", D1,
            [Capture(1, [history_row(1, 0)], "x"), Capture(2, [], "x")],
            index=index, unindexed_fpl_ids={2}),
    ])
    results = compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    assert not results[D1].ok
    assert not Path(manifest_path(str(dest), D1)).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
def test_a_payload_whose_bytes_differ_from_its_index_sha256_fails_the_day(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [Run("20260920T190000Z-hhhhhh", D1, [Capture(1, [], "x")])])
    path = raw / f"fpl/element-summary/1/{D1}/20260920T190000Z-hhhhhh/payload.json"
    path.write_text(json.dumps({"fixtures": [], "history": [], "history_past": [1]}))
    results = compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    assert not results[D1].ok
    assert not Path(manifest_path(str(dest), D1)).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
def test_a_run_with_neither_captures_nor_a_catalog_entry_fails_the_day(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [Run("20260920T190000Z-iiiiii", D1, [Capture(1, [], "x")], index="none")])
    results = compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    assert not results[D1].ok
    assert not Path(manifest_path(str(dest), D1)).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
def test_one_failed_day_does_not_stop_the_others(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    build_tree(raw, [Run("20260922T190000Z-jjjjjj", "2026-09-22",
                         [Capture(1, [], "x")], index="none")])
    results = compact_days([D1, "2026-09-22"], raw_root=str(raw), dest_root=str(dest))
    assert results[D1].ok and not results["2026-09-22"].ok
    assert Path(manifest_path(str(dest), D1)).exists()


# --- A6: the destination gate ---------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#193 AC6")
@pytest.mark.parametrize(
    ("event", "dest", "allowed"),
    [
        ("schedule", PROD, True),
        ("workflow_dispatch", PROD, False),
        (None, PROD, False),
        (None, "/tmp/compacted", True),
    ],
)
def test_only_a_scheduled_run_may_write_to_the_production_prefix(event, dest, allowed):
    if allowed:
        check_destination(dest, event)
    else:
        with pytest.raises(DestinationRefused, match="schedule"):
            check_destination(dest, event)


@pytest.mark.unit
@pytest.mark.covers("#193 AC6")
def test_a_dispatch_calling_the_writer_for_production_is_refused_before_any_write(
    tmp_path, monkeypatch
):
    raw = tmp_path / "raw"
    two_day_tree(raw)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setattr(writer, "write_parquet", lambda *a: pytest.fail("wrote parquet"))
    with pytest.raises(DestinationRefused):
        compact_days([D1], raw_root=str(raw), dest_root=PROD)


@pytest.mark.unit
@pytest.mark.covers("#193 AC6")
@pytest.mark.covers("#198 AC3")
@pytest.mark.covers("#205 AC4")
@pytest.mark.parametrize("workflow", ["ci.yml", "served_diff.yml", "scheduled_build.yml"])
def test_no_other_workflow_runs_the_writer(workflow):
    assert not runs_writer((REPO / ".github" / "workflows" / workflow).read_text())


def repo_workflows() -> dict[str, str]:
    return {
        p.name: p.read_text()
        for p in sorted((REPO / ".github" / "workflows").glob("*.y*ml"))
    }


@pytest.mark.unit
@pytest.mark.covers("#205 AC4")
def test_the_scheduled_compaction_workflow_is_the_only_one_with_a_production_destination():
    workflows = repo_workflows()
    assert [n for n, text in workflows.items() if runs_writer(text)] == [
        "scheduled_compaction.yml"
    ]
    assert workflow_problems(workflows) == []


PRODUCTION_RUN = (
    "uv run python scripts/compaction_step.py"
    " --raw-root s3://fpl-data-safari/raw --dest-root s3://fpl-data-safari/compacted"
)


def workflow_text(on: str, run: str = PRODUCTION_RUN) -> str:
    return f"""
name: synthetic
on:
{on}
jobs:
  compact:
    runs-on: ubuntu-24.04
    steps:
      - name: Compact
        run: {run}
"""


SCHEDULE_ONLY = '  schedule:\n    - cron: "30 1,13 * * *"'


@pytest.mark.unit
@pytest.mark.covers("#205 AC4")
def test_the_scan_passes_the_allowed_workflow_on_a_schedule_alone():
    assert workflow_problems({"scheduled_compaction.yml": workflow_text(SCHEDULE_ONLY)}) == []


@pytest.mark.unit
@pytest.mark.covers("#205 AC4")
@pytest.mark.parametrize("name", ["scheduled_build.yml", "ci.yml", "compaction_v2.yml"])
def test_the_scan_flags_any_other_workflow_with_a_production_destination(name):
    problems = workflow_problems({
        "scheduled_compaction.yml": workflow_text(SCHEDULE_ONLY),
        name: workflow_text(SCHEDULE_ONLY),
    })
    assert len(problems) == 1 and name in problems[0]


@pytest.mark.unit
@pytest.mark.covers("#205 AC4")
@pytest.mark.parametrize("on", [
    SCHEDULE_ONLY + "\n  workflow_dispatch:",
    "  workflow_dispatch:",
    "  push:\n    branches: [main]",
], ids=["schedule-and-dispatch", "dispatch", "push"])
def test_the_scan_flags_the_allowed_workflow_with_any_trigger_but_a_schedule(on):
    problems = workflow_problems({"scheduled_compaction.yml": workflow_text(on)})
    assert len(problems) == 1 and "scheduled_compaction.yml" in problems[0]


@pytest.mark.unit
@pytest.mark.covers("#205 AC4")
def test_the_scan_passes_another_workflow_with_a_local_destination():
    local = workflow_text("  workflow_dispatch:", PRODUCTION_RUN.replace(
        "s3://fpl-data-safari/compacted", ".local/compacted"))
    assert workflow_problems({"ci.yml": local}) == []


def synthetic_workflow(run: str) -> str:
    return f"""
name: synthetic
on: workflow_dispatch
jobs:
  live-tests:
    runs-on: ubuntu-24.04
    steps:
      - name: Compact
        run: {run}
"""


@pytest.mark.unit
@pytest.mark.covers("#193 AC6")
@pytest.mark.covers("#198 AC3")
@pytest.mark.parametrize("run", [
    "uv run python scripts/compact_element_summary.py --day 2026-09-20"
    " --raw-root s3://fpl-data-safari/raw --dest-root s3://fpl-data-safari/compacted",
    "uv run python scripts/compaction_step.py --days 2026-09-20"
    " --raw-root s3://fpl-data-safari/raw --dest-root s3://fpl-data-safari/compacted",
    "uv run python scripts/compaction_step.py --days 2026-09-20"
    " --raw-root s3://fpl-data-safari/raw --dest-root \"$DEST\"",
], ids=["writer-s3", "step-s3", "step-unresolved-destination"])
def test_the_workflow_scan_flags_a_writer_call_without_a_local_destination(run):
    assert runs_writer(synthetic_workflow(run))


@pytest.mark.unit
@pytest.mark.covers("#198 AC3")
def test_the_workflow_scan_passes_a_writer_call_with_a_local_destination():
    assert not runs_writer(synthetic_workflow(
        "uv run python scripts/compaction_step.py --days 2026-09-20"
        " --raw-root s3://fpl-data-safari/raw --dest-root .local/compacted"
    ))


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
def test_a_day_with_no_payload_files_fails_the_day(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    two_day_tree(raw)
    results = compact_days(["2026-09-25"], raw_root=str(raw), dest_root=str(dest))
    assert not results["2026-09-25"].ok
    assert "no payload files" in results["2026-09-25"].reason
    assert not Path(manifest_path(str(dest), "2026-09-25")).exists()


@pytest.mark.integration
@pytest.mark.covers("#193 AC4")
def test_a_run_whose_run_manifest_is_missing_fails_the_day(tmp_path):
    raw, dest = tmp_path / "raw", tmp_path / "compacted"
    build_tree(raw, [Run("20260920T190000Z-kkkkkk", D1, [Capture(1, [], "x")], index="catalog")])
    (raw / f"fpl/_manifests/{D1}/20260920T190000Z-kkkkkk/manifest.json").unlink()
    results = compact_days([D1], raw_root=str(raw), dest_root=str(dest))
    assert not results[D1].ok
    assert "no run manifest" in results[D1].reason
    assert not Path(manifest_path(str(dest), D1)).exists()


# --- #203: the index's real shapes ----------------------------------------------------
#
# fixtures/compaction_real/raw is trimmed from live S3 on 2026-10-15: run
# 20261013T072947Z-8f09c4's manifest (captures[], contract 2.4.0) and run
# 20260829T012315Z-2499d4's manifest and backfill catalog entry, each cut to two
# element-summary captures plus other endpoints' entries, with those captures'
# real payloads. Ingest records the endpoint as `element-summary/<fpl_id>`.

REAL = Path(__file__).resolve().parent / "fixtures" / "compaction_real" / "raw"
REAL_DAYS = {
    "manifest": ("2026-10-13", "20261013T072947Z-8f09c4"),
    "catalog": ("2026-08-29", "20260829T012315Z-2499d4"),
}


def real_tree(tmp_path: Path) -> Path:
    raw = tmp_path / "raw"
    for f in REAL.rglob("*"):
        if f.is_file():
            (raw / f.relative_to(REAL)).parent.mkdir(parents=True, exist_ok=True)
            (raw / f.relative_to(REAL)).write_bytes(f.read_bytes())
    return raw


@pytest.mark.integration
@pytest.mark.covers("#203 AC6")
@pytest.mark.parametrize("index", ["manifest", "catalog"])
def test_a_day_indexed_in_the_real_shape_compacts(tmp_path, index):
    day, run_id = REAL_DAYS[index]
    dest = tmp_path / "compacted"
    result = compact_days([day], raw_root=str(REAL), dest_root=str(dest))[day]
    assert result.ok, result.reason
    entry = json.loads(Path(manifest_path(str(dest), day)).read_text())
    assert entry["payload_files"] == entry["parquet_rows"] == 2
    assert entry["run_ids"] == [run_id]


@pytest.mark.integration
@pytest.mark.covers("#203 AC6")
@pytest.mark.parametrize("index", ["manifest", "catalog"])
def test_a_real_shape_payload_whose_bytes_differ_from_its_index_fails_on_sha256(
    tmp_path, index
):
    day, run_id = REAL_DAYS[index]
    raw, dest = real_tree(tmp_path), tmp_path / "compacted"
    (raw / f"fpl/element-summary/1/{day}/{run_id}/payload.json").write_text(
        json.dumps({"fixtures": [], "history": [], "history_past": []})
    )
    result = compact_days([day], raw_root=str(raw), dest_root=str(dest))[day]
    assert not result.ok
    assert "sha256" in result.reason
    assert not Path(manifest_path(str(dest), day)).exists()


@pytest.mark.integration
@pytest.mark.covers("#203 AC6")
@pytest.mark.parametrize("index", ["manifest", "catalog"])
def test_a_real_shape_listed_file_missing_from_the_index_is_the_one_named(tmp_path, index):
    day, run_id = REAL_DAYS[index]
    raw, dest = real_tree(tmp_path), tmp_path / "compacted"
    extra = f"fpl/element-summary/999/{day}/{run_id}/payload.json"
    (raw / extra).parent.mkdir(parents=True)
    (raw / extra).write_text(json.dumps({"fixtures": [], "history": [], "history_past": []}))
    result = compact_days([day], raw_root=str(raw), dest_root=str(dest))[day]
    assert not result.ok
    assert f"listed but not indexed ['raw/{extra}']; indexed but not listed []" in result.reason
    assert not Path(manifest_path(str(dest), day)).exists()
