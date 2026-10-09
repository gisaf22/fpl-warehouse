"""The served diff compares two builds' served parquet, per table and per season.

The comparison is the `served_diff` dbt run-operation (macros/served_diff.sql),
which loads both sides into one DuckDB and compares them with audit_helper.
Each side is a directory holding the six served tables as parquet and a
build.json with the build's seconds and the newest run_id it read, as
`served_diff_export` writes them. No S3 and no built warehouse: the parquet is
written here, and dbt runs under the credential-free `served_diff` target, with
a database of the test's own.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parents[2]

# Each table's key columns, then one value column. The macro reads the keys.
ROWS = {
    "fct_player_fixture": (
        "season, fpl_id, fixture_id, total_points",
        [("2025-26", 1, 10, 2), ("2025-26", 2, 11, 6), ("2026-27", 1, 12, 1)],
    ),
    "fct_player_gameweek": (
        "season, fpl_id, gameweek, total_points",
        [("2025-26", 1, 1, 2), ("2026-27", 1, 1, 1)],
    ),
    "dim_team": (
        "season, team_fpl_id, team_name",
        [("2025-26", 1, "Arsenal"), ("2026-27", 1, "Arsenal")],
    ),
    "dim_player": (
        "season, fpl_id, web_name",
        [("2025-26", 1, "Raya"), ("2026-27", 1, "Raya")],
    ),
    "dim_fixture": (
        "season, fixture_id, gameweek",
        [("2025-26", 10, 1), ("2026-27", 12, 1)],
    ),
    "dim_player_status_history": (
        "season, fpl_id, valid_from, status",
        [
            ("2025-26", 1, "2026-05-26 03:46:26", "a"),
            ("2026-27", 1, "2026-08-29 19:11:09", "a"),
            ("2026-27", 1, "2026-08-31 20:36:09", "d"),
        ],
    ),
}


def write_side(path, rows=ROWS, run_id="20261004T070000Z-aaaaaa", seconds=400):
    path.mkdir()
    connection = duckdb.connect()
    for table, (columns, values) in rows.items():
        literal = ", ".join(
            "(" + ", ".join(repr(v) for v in row) + ")" for row in values
        )
        connection.execute(
            f"COPY (SELECT * FROM (VALUES {literal}) t({columns})) "
            f"TO '{path / table}.parquet' (FORMAT PARQUET)"
        )
    (path / "build.json").write_text(
        json.dumps({"seconds": seconds, "newest_run_id": run_id})
    )
    return path


def served_diff(tmp_path, before, after) -> subprocess.CompletedProcess:
    args = json.dumps({"before": str(before), "after": str(after)})
    return subprocess.run(
        ["dbt", "-q", "--no-use-colors", "run-operation", "served_diff"]
        + ["--target", "served_diff", "--args", args],
        cwd=REPO,
        env={**os.environ, "DBT_SERVED_DIFF_PATH": str(tmp_path / "diff.duckdb")},
        capture_output=True,
        text=True,
    )


def with_rows(table, rows):
    return {**ROWS, table: (ROWS[table][0], rows)}


@pytest.mark.integration
@pytest.mark.covers("#102 AC2")
def test_a_row_missing_from_the_head_build_is_named_by_table_season_and_row(
    tmp_path,
):
    before = write_side(tmp_path / "before")
    rows = ROWS["fct_player_fixture"][1]
    after = write_side(
        tmp_path / "after", rows=with_rows("fct_player_fixture", rows[1:])
    )

    result = served_diff(tmp_path, before, after)

    assert result.returncode == 1
    assert "| fct_player_fixture | 2025-26 | 2 | 1 | 1 | 0 |" in result.stdout
    assert "#### `fct_player_fixture` 2025-26" in result.stdout
    assert "only before: `(2025-26, 1, 10, 2)`" in result.stdout
    assert "| fct_player_fixture | 2026-27 | 1 | 1 | 0 | 0 |" in result.stdout


@pytest.mark.integration
@pytest.mark.covers("#102 AC2")
def test_a_row_only_in_the_head_build_is_reported_too(tmp_path):
    before = write_side(tmp_path / "before")
    rows = ROWS["dim_team"][1] + [("2026-27", 2, "Aston Villa")]
    after = write_side(tmp_path / "after", rows=with_rows("dim_team", rows))

    result = served_diff(tmp_path, before, after)

    assert result.returncode == 1
    assert "| dim_team | 2026-27 | 1 | 2 | 0 | 1 |" in result.stdout
    assert "only after: `(2026-27, 2, Aston Villa)`" in result.stdout


@pytest.mark.integration
@pytest.mark.covers("#102 AC2")
def test_a_changed_value_is_reported_on_both_sides_with_its_column(tmp_path):
    before = write_side(tmp_path / "before")
    rows = [("2025-26", 1, "Raya"), ("2026-27", 1, "Kepa")]
    after = write_side(tmp_path / "after", rows=with_rows("dim_player", rows))

    result = served_diff(tmp_path, before, after)

    assert result.returncode == 1
    assert "| dim_player | 2026-27 | 1 | 1 | 1 | 1 |" in result.stdout
    assert "only before: `(2026-27, 1, Raya)`" in result.stdout
    assert "only after: `(2026-27, 1, Kepa)`" in result.stdout
    assert "`dim_player` columns with differing values on matching keys: web_name" in (
        result.stdout
    )


@pytest.mark.integration
@pytest.mark.covers("#102 AC3")
def test_builds_that_read_different_newest_runs_are_inconclusive_and_fail(tmp_path):
    before = write_side(tmp_path / "before", run_id="20261004T070000Z-aaaaaa")
    after = write_side(tmp_path / "after", run_id="20261004T190000Z-bbbbbb")

    result = served_diff(tmp_path, before, after)

    assert result.returncode == 1
    assert "**Inconclusive:**" in result.stdout
    assert "| table | season |" not in result.stdout
