"""served_diff compares two builds' served parquet, per table and per season.

Each side is a directory holding the five served tables as parquet and a
build.json with the build's wall-clock seconds and the newest run_id it read,
as written by `served_diff.py export`. No S3 and no built warehouse: the
parquet is written here.
"""

from __future__ import annotations

import json

import duckdb
import pytest

import served_diff

ROWS = {
    "fct_player_fixture": [("2025-26", 1, 10), ("2025-26", 2, 11), ("2026-27", 1, 12)],
    "fct_player_gameweek": [("2025-26", 1, 1), ("2026-27", 1, 1)],
    "dim_team": [("2025-26", 1, 0), ("2026-27", 1, 0)],
    "dim_player": [("2025-26", 1, 0), ("2026-27", 1, 0)],
    "dim_fixture": [("2025-26", 10, 0), ("2026-27", 12, 0)],
}


def write_side(path, rows=ROWS, run_id="20261004T070000Z-aaaaaa", seconds=400):
    path.mkdir()
    connection = duckdb.connect()
    for table, values in rows.items():
        literal = ", ".join(f"('{s}', {a}, {b})" for s, a, b in values)
        connection.execute(
            f"COPY (SELECT * FROM (VALUES {literal}) t(season, fpl_id, n)) "
            f"TO '{path / table}.parquet' (FORMAT PARQUET)"
        )
    (path / "build.json").write_text(
        json.dumps({"seconds": seconds, "newest_run_id": run_id})
    )
    return path


@pytest.mark.unit
@pytest.mark.covers("#102 AC2")
def test_a_row_missing_from_the_head_build_is_named_by_table_season_and_row(tmp_path):
    before = write_side(tmp_path / "before")
    dropped = {**ROWS, "fct_player_fixture": ROWS["fct_player_fixture"][1:]}
    after = write_side(tmp_path / "after", rows=dropped)

    report = served_diff.compare(before, after)

    assert report.inconclusive is None
    assert [(d.table, d.season) for d in report.differences] == [
        ("fct_player_fixture", "2025-26")
    ]
    (difference,) = report.differences
    assert difference.only_before == [("2025-26", 1, 10)]
    assert difference.only_after == []
    assert "fct_player_fixture" in report.markdown()
    assert "2025-26" in report.markdown()


@pytest.mark.unit
@pytest.mark.covers("#102 AC2")
def test_a_row_only_in_the_head_build_is_reported_too(tmp_path):
    before = write_side(tmp_path / "before")
    added = {**ROWS, "dim_team": ROWS["dim_team"] + [("2026-27", 2, 0)]}
    after = write_side(tmp_path / "after", rows=added)

    report = served_diff.compare(before, after)

    (difference,) = report.differences
    assert (difference.table, difference.season) == ("dim_team", "2026-27")
    assert difference.only_after == [("2026-27", 2, 0)]


@pytest.mark.unit
@pytest.mark.covers("#102 AC2")
def test_the_command_fails_when_the_builds_differ(tmp_path):
    before = write_side(tmp_path / "before")
    dropped = {**ROWS, "dim_fixture": ROWS["dim_fixture"][:1]}
    after = write_side(tmp_path / "after", rows=dropped)

    assert served_diff.main(["diff", str(before), str(after)]) == 1


@pytest.mark.unit
@pytest.mark.covers("#102 AC3")
def test_builds_that_read_different_newest_runs_are_inconclusive(tmp_path):
    before = write_side(tmp_path / "before", run_id="20261004T070000Z-aaaaaa")
    after = write_side(tmp_path / "after", run_id="20261004T190000Z-bbbbbb")

    report = served_diff.compare(before, after)

    assert report.inconclusive is not None
    assert report.differences == []
    assert "inconclusive" in report.markdown().lower()


@pytest.mark.unit
@pytest.mark.covers("#102 AC3")
def test_the_command_fails_when_the_diff_is_inconclusive(tmp_path):
    before = write_side(tmp_path / "before", run_id="20261004T070000Z-aaaaaa")
    after = write_side(tmp_path / "after", run_id="20261004T190000Z-bbbbbb")

    assert served_diff.main(["diff", str(before), str(after)]) == 1
