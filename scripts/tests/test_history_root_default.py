"""A `dev` build reads the ported history tree unless told otherwise.

The three multi-season sources (element-summary, bootstrap-static, fixtures)
glob the live tree and, when `history_root` is set, every season under it.
Each test parses the project under the `dev` target and reads the rendered
`external_location` of each source from the manifest. Parsing opens no
connection, so no AWS session is needed, as in CI's `validate` job.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]

HISTORY = "s3://fpl-data-safari/history"
MULTI_SEASON_SOURCES = ("element_summary", "bootstrap_static", "fixtures")

NON_DEV_TARGETS = sorted(
    set(yaml.safe_load((REPO / "profiles.yml").read_text())["fpl_warehouse"]["outputs"])
    - {"dev"}
)


def all_locations(target_path: Path, target: str, *extra: str) -> dict[str, str]:
    result = subprocess.run(
        ["dbt", "--no-use-colors", "parse", "--target", target]
        + ["--target-path", str(target_path), *extra],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    sources = json.loads((target_path / "manifest.json").read_text())["sources"]
    return {
        source["name"]: source["meta"]["external_location"]
        for source in sources.values()
        if "external_location" in source["meta"]
    }


def rendered_locations(target_path: Path, *extra: str) -> dict[str, str]:
    locations = all_locations(target_path, "dev", *extra)
    return {name: locations[name] for name in MULTI_SEASON_SOURCES}


@pytest.mark.integration
@pytest.mark.covers("#180 AC1")
def test_a_dev_parse_without_the_var_reads_live_and_history(tmp_path):
    for name, location in rendered_locations(tmp_path).items():
        assert "s3://fpl-data-safari/raw/fpl/" in location, name
        assert f"'{HISTORY}/*/fpl/" in location, name


@pytest.mark.integration
@pytest.mark.covers("#180 AC2")
def test_an_empty_history_root_reads_the_live_tree_alone(tmp_path):
    locations = rendered_locations(tmp_path, "--vars", '{history_root: ""}')

    for name, location in locations.items():
        assert "s3://fpl-data-safari/raw/fpl/" in location, name
        assert "history" not in location, name


@pytest.mark.integration
@pytest.mark.covers("#180 AC2")
def test_another_history_root_replaces_the_default(tmp_path):
    other = "s3://example-bucket/other-history"
    locations = rendered_locations(tmp_path, "--vars", f"{{history_root: '{other}'}}")

    for name, location in locations.items():
        assert f"'{other}/*/fpl/" in location, name
        assert HISTORY not in location, name


@pytest.mark.integration
@pytest.mark.covers("#180 AC4")
@pytest.mark.parametrize("target", NON_DEV_TARGETS)
def test_no_other_target_reads_an_s3_history_tree(tmp_path, target):
    locations = all_locations(tmp_path, target)

    assert locations
    for name, location in locations.items():
        assert not re.search(r"s3://[^']*history", location), (target, name)


@pytest.mark.integration
@pytest.mark.covers("#180 AC4")
def test_the_fixtures_target_reads_only_the_local_tree(tmp_path):
    locations = all_locations(tmp_path, "fixtures")

    assert locations
    for name, location in locations.items():
        assert "s3://" not in location, name
