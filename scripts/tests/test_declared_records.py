"""Staging can read only the source fields declared in sources.yml.

`declared_records` (macros/declared_records.sql) selects the declared columns
at one record path of an fpl_raw payload source. A query over it that names an
undeclared field must fail the build, naming that field. Each test runs an
inline query with `dbt show` under the credential-free `fixtures` target, which
reads the checked-in capture under tests/fixtures/raw: no S3, and no prior
build, since the macro reads the source alone.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

READ = "with r as ({{ declared_records('event_status', '$.status[*]') }}) "


def show(query: str) -> subprocess.CompletedProcess:
    # The fixtures target's database file lives under the gitignored .local/.
    (REPO / ".local").mkdir(exist_ok=True)
    return subprocess.run(
        ["dbt", "--no-use-colors", "show", "--target", "fixtures"]
        + ["--inline", query, "--limit", "5", "--output", "json"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_reading_an_undeclared_field_fails_naming_the_field():
    result = show(READ + "select r.leagues from r")

    assert result.returncode != 0
    assert "leagues" in result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_every_declared_field_is_read_under_its_key():
    result = show(
        READ + 'select r.capture_key, r."event", r."date", r.points, r.bonus_added from r'
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for key in ("capture_key", "event", "date", "points", "bonus_added"):
        assert f'"{key}"' in result.stdout


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_an_unsupported_record_path_fails_compilation_naming_the_path():
    result = show(
        "with r as ({{ declared_records('event_status', '$.status[*].nested[*]') }}) "
        "select * from r"
    )

    assert result.returncode != 0
    assert "$.status[*].nested[*]" in result.stdout + result.stderr


TOP_LEVEL = "with r as ({{ declared_records('fixtures', '$[*]') }}) "


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_reading_an_undeclared_field_at_the_top_level_path_fails_naming_the_field():
    # `code` is in every fixtures payload but is not declared in sources.yml.
    result = show(TOP_LEVEL + "select r.code from r")

    assert result.returncode != 0
    assert "code" in result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_every_declared_field_at_the_top_level_path_is_read_under_its_key():
    keys = ("capture_key", "id", "event", "kickoff_time", "team_h", "team_a",
            "team_h_score", "team_a_score", "finished", "team_h_difficulty",
            "team_a_difficulty")
    result = show(TOP_LEVEL + "select " + ", ".join(f'r."{k}"' for k in keys) + " from r")

    assert result.returncode == 0, result.stdout + result.stderr
    for key in keys:
        assert f'"{key}"' in result.stdout


def passes_through(resource_type: str, graph: dict) -> subprocess.CompletedProcess:
    (REPO / ".local").mkdir(exist_ok=True)
    args = json.dumps({"resource_type": resource_type, "graph": graph})
    return subprocess.run(
        ["dbt", "--no-use-colors", "run-operation", "--target", "fixtures"]
        + ["declared_records_passes_through", "--args", args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_an_empty_graph_in_a_unit_test_passes_the_mocked_columns_through():
    result = passes_through("unit_test", {})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "passes through" in result.stdout


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
@pytest.mark.parametrize("resource_type", ["model", "test", "sql_operation"])
def test_an_empty_graph_outside_a_unit_test_fails_naming_the_macro(resource_type):
    result = passes_through(resource_type, {})

    assert result.returncode != 0
    assert "declared_records" in result.stdout + result.stderr


@pytest.mark.integration
@pytest.mark.covers("#115 AC1")
def test_a_full_graph_outside_a_unit_test_reads_the_declarations():
    result = passes_through("model", {"sources": {"x": {}}})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "reads declarations" in result.stdout
