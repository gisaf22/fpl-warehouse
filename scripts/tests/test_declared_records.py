"""Staging can read only the source fields declared in sources.yml.

`declared_records` (macros/declared_records.sql) selects the declared columns
at one record path of an fpl_raw payload source. A query over it that names an
undeclared field must fail the build, naming that field. Each test runs an
inline query with `dbt show` under the credential-free `fixtures` target, which
reads the checked-in capture under tests/fixtures/raw: no S3, and no prior
build, since the macro reads the source alone.
"""

from __future__ import annotations

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
