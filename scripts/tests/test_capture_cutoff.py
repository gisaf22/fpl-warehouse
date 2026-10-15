"""The test-only `capture_cutoff` var narrows the payload reads to earlier captures.

#183's memory experiments rebuild the warehouse as it stood at an earlier date.
DuckDB reads every file a glob matches, even one a `filename` filter excludes,
so the cutoff must narrow the globs themselves (#190 D1): each payload source's
date directory renders as a list of patterns covering only dates before the
cutoff. Only the four payload sources are cut, never the capture index (D2).

The parse tests read each source's rendered `external_location` from the
manifest, as test_history_root_default.py does; parsing opens no connection.
The build test builds staging from the fixture tree into a temporary database,
through a copy of the `fixtures` profile, so `.local/fixtures.duckdb` is
untouched.
"""

from __future__ import annotations

import datetime as dt
import fnmatch
import json
import re
import subprocess
from pathlib import Path

import duckdb
import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]

PAYLOAD_SOURCES = ("element_summary", "bootstrap_static", "fixtures", "event_status")
PAYLOAD_ENDPOINTS = ("element-summary", "bootstrap-static", "fixtures", "event-status")

UNCUT = {
    "fixtures": {
        "element_summary": [
            "tests/fixtures/raw/fpl/element-summary/*/*/*/payload.json",
            "tests/fixtures/history/*/fpl/element-summary/*/*/*/payload.json",
        ],
        "bootstrap_static": [
            "tests/fixtures/raw/fpl/bootstrap-static/*/*/payload.json",
            "tests/fixtures/history/*/fpl/bootstrap-static/*/*/payload.json",
        ],
        "fixtures": [
            "tests/fixtures/raw/fpl/fixtures/*/*/payload.json",
            "tests/fixtures/history/*/fpl/fixtures/*/*/payload.json",
        ],
        "event_status": ["tests/fixtures/raw/fpl/event-status/*/*/payload.json"],
    },
    "dev": {
        "element_summary": [
            "s3://fpl-data-safari/raw/fpl/element-summary/*/*/*/payload.json",
            "s3://fpl-data-safari/history/*/fpl/element-summary/*/*/*/payload.json",
        ],
        "bootstrap_static": [
            "s3://fpl-data-safari/raw/fpl/bootstrap-static/*/*/payload.json",
            "s3://fpl-data-safari/history/*/fpl/bootstrap-static/*/*/payload.json",
        ],
        "fixtures": [
            "s3://fpl-data-safari/raw/fpl/fixtures/*/*/payload.json",
            "s3://fpl-data-safari/history/*/fpl/fixtures/*/*/payload.json",
        ],
        "event_status": ["s3://fpl-data-safari/raw/fpl/event-status/*/*/payload.json"],
    },
}

GLOB = re.compile(r"'([^']*payload\.json)'")

# Every day of three years around the live season, and the fixture tree's
# ported-history date.
DATES = [
    (dt.date(2025, 1, 1) + dt.timedelta(days=n)).isoformat() for n in range(3 * 366)
] + ["2019-12-31", "2026-05-26", "2031-01-01"]


def parse(target_path: Path, target: str, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["dbt", "--no-use-colors", "parse", "--target", target]
        + ["--target-path", str(target_path), *extra],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def payload_globs(target_path: Path, target: str, *extra: str) -> dict[str, list[str]]:
    result = parse(target_path, target, *extra)
    assert result.returncode == 0, result.stdout + result.stderr
    sources = json.loads((target_path / "manifest.json").read_text())["sources"]
    by_name = {s["name"]: s["meta"].get("external_location", "") for s in sources.values()}
    return {name: GLOB.findall(by_name[name]) for name in PAYLOAD_SOURCES}


def template(glob: str) -> str:
    """The glob with its date directory, third from last, blanked."""
    parts = glob.split("/")
    parts[-3] = "{date}"
    return "/".join(parts)


@pytest.mark.integration
@pytest.mark.covers("#190 AC1")
@pytest.mark.parametrize("target", ["fixtures", "dev"])
@pytest.mark.parametrize("unset", [(), ("--vars", '{capture_cutoff: ""}')], ids=["absent", "empty"])
def test_without_a_cutoff_every_payload_source_renders_its_globs_unchanged(
    tmp_path, target, unset
):
    assert payload_globs(tmp_path, target, *unset) == UNCUT[target]


@pytest.mark.integration
@pytest.mark.covers("#190 AC1")
@pytest.mark.parametrize("target", ["fixtures", "dev"])
@pytest.mark.parametrize(
    "cutoff", ["2026-09-06", "2026-09-15", "2026-10-01", "2026-01-01", "2030-12-31"]
)
def test_a_cutoff_renders_only_dates_before_it_on_every_tree_of_every_payload_source(
    tmp_path, target, cutoff
):
    rendered = payload_globs(tmp_path, target, "--vars", f"{{capture_cutoff: '{cutoff}'}}")

    for name in PAYLOAD_SOURCES:
        # Same trees, same paths: only the date directory differs.
        expected_templates = {template(g) for g in UNCUT[target][name]}
        assert {template(g) for g in rendered[name]} == expected_templates, name
        for tmpl in expected_templates:
            patterns = [g.split("/")[-3] for g in rendered[name] if template(g) == tmpl]
            assert "*" not in patterns, (name, tmpl)
            for date in DATES:
                read = any(fnmatch.fnmatchcase(date, p) for p in patterns)
                assert read == (date < cutoff), (name, tmpl, date, patterns)


@pytest.mark.integration
@pytest.mark.covers("#190 AC3")
@pytest.mark.parametrize("cutoff", ["2026-9-15", "20260915", "2026-09-15T00:00", "latest"])
def test_a_cutoff_not_in_date_form_fails_the_parse_naming_the_var(tmp_path, cutoff):
    result = parse(tmp_path, "fixtures", "--vars", f"{{capture_cutoff: '{cutoff}'}}")

    assert result.returncode != 0
    assert "capture_cutoff" in result.stdout + result.stderr


def date_of(capture_key: str) -> str:
    return capture_key.split("/")[-3]


def endpoint_of(capture_key: str) -> str:
    parts = capture_key.split("/")
    return parts[parts.index("fpl") + 1]


@pytest.mark.integration
@pytest.mark.covers("#190 AC1")
def test_a_fixture_build_with_a_cutoff_stages_only_captures_dated_before_it(tmp_path):
    cutoff = "2026-09-06"
    profiles = yaml.safe_load((REPO / "profiles.yml").read_text())
    profiles["fpl_warehouse"]["outputs"]["fixtures"]["path"] = str(tmp_path / "cutoff.duckdb")
    (tmp_path / "profiles.yml").write_text(yaml.safe_dump(profiles))
    common = [
        "--target", "fixtures",
        "--profiles-dir", str(tmp_path),
        "--target-path", str(tmp_path / "target"),
        "--log-path", str(tmp_path / "logs"),
    ]
    for command in (
        ["seed"],
        ["run", "--select", "+path:models/staging",
         "--vars", f"{{capture_cutoff: '{cutoff}'}}"],
    ):
        result = subprocess.run(
            ["dbt", "--no-use-colors", *command, *common],
            cwd=REPO, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    con = duckdb.connect(str(tmp_path / "cutoff.duckdb"), read_only=True)
    tables = [
        row[0]
        for row in con.sql(
            "select table_name from information_schema.columns "
            "where column_name = 'capture_key' and table_name like 'stg_%'"
        ).fetchall()
    ]
    staged = {
        key
        for table in tables
        for (key,) in con.sql(f"select distinct capture_key from {table}").fetchall()
    }
    admitted = {key for (key,) in con.sql("select capture_key from int_admitted_capture").fetchall()}

    assert {"stg_player_history_capture", "stg_player", "stg_fixture", "stg_gameweek_status"} <= set(tables)
    for endpoint in PAYLOAD_ENDPOINTS:
        before = {k for k in staged if endpoint_of(k) == endpoint}
        later = {k for k in admitted if endpoint_of(k) == endpoint and date_of(k) >= cutoff}
        assert before, f"{endpoint}: nothing staged before {cutoff}"
        assert all(date_of(k) < cutoff for k in before), endpoint
        # Not vacuous: the index still admits later captures, and none was read.
        assert later, f"{endpoint}: the fixture tree has no capture on or after {cutoff}"
        assert not later & staged, endpoint
