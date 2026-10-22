"""CI fails when a payload source opts out of the presence test without saying why.

`problems` is the pure core of scripts/check_source_presence_tests.py: given a
parsed dbt manifest, it returns one message per violation, and CI's validate
job fails when the list is non-empty. These tests feed it hand-built manifests.
"""

from __future__ import annotations

import pytest

from check_source_presence_tests import problems

PAYLOAD = ("element_summary", "bootstrap_static", "fixtures", "event_status")


def source_id(table: str) -> str:
    return f"source.fpl_warehouse.fpl_raw.{table}"


SEVERITY = {"removed": "ERROR", "partial": "WARN"}


def presence_test(table: str, mode: str, severity: str | None = None) -> tuple[str, dict]:
    uid = f"test.fpl_warehouse.consumed_keys_present_{table}_{mode}"
    return uid, {
        "resource_type": "test",
        "config": {"severity": severity or SEVERITY[mode]},
        "test_metadata": {"name": "consumed_keys_present", "kwargs": {"mode": mode}},
        "depends_on": {"nodes": [source_id(table)]},
    }


def manifest(
    *,
    without: tuple[str, str] | None = None,
    exempt: object = "absent",
    severity: dict[tuple[str, str], str] | None = None,
) -> dict:
    """Every payload source declared with both tests; run_manifests has none.

    `without` drops one (table, mode) test. `exempt` sets
    fixtures' `stats.identifier` meta.presence_exempt to that value.
    """
    sources = {}
    for table in PAYLOAD + ("run_manifests",):
        sources[source_id(table)] = {
            "resource_type": "source",
            "source_name": "fpl_raw",
            "name": table,
            "columns": {"id": {"name": "id", "meta": {}}},
        }
    if exempt != "absent":
        sources[source_id("fixtures")]["columns"]["stats.identifier"] = {
            "name": "stats.identifier",
            "meta": {"record_path": "$[*].stats[*]", "presence_exempt": exempt},
        }
    nodes = dict(
        presence_test(table, mode, (severity or {}).get((table, mode)))
        for table in PAYLOAD
        for mode in ("removed", "partial")
        if (table, mode) != without
    )
    return {"sources": sources, "nodes": nodes}


@pytest.mark.unit
@pytest.mark.covers("#114 AC4")
def test_every_payload_source_with_both_tests_passes():
    assert problems(manifest()) == []


@pytest.mark.unit
@pytest.mark.covers("#114 AC4")
@pytest.mark.parametrize("mode", ["removed", "partial"])
def test_a_payload_source_missing_either_test_fails_naming_it(mode):
    found = problems(manifest(without=("event_status", mode)))
    assert len(found) == 1
    assert "event_status" in found[0] and mode in found[0]


@pytest.mark.unit
@pytest.mark.covers("#114 AC4")
@pytest.mark.parametrize("reason", ["", "   ", None])
def test_an_exemption_with_an_empty_reason_fails_naming_the_column(reason):
    found = problems(manifest(exempt=reason))
    assert len(found) == 1
    assert "fixtures" in found[0] and "stats.identifier" in found[0]


@pytest.mark.unit
@pytest.mark.covers("#114 AC4")
def test_an_exemption_with_a_reason_passes():
    assert problems(manifest(exempt="FPL omits stats before kickoff")) == []


@pytest.mark.unit
@pytest.mark.covers("#114 AC4")
@pytest.mark.parametrize(("mode", "wrong"), [("removed", "warn"), ("partial", "error")])
def test_a_presence_test_with_the_wrong_severity_fails_naming_it(mode, wrong):
    found = problems(manifest(severity={("bootstrap_static", mode): wrong}))
    assert len(found) == 1
    assert "bootstrap_static" in found[0] and mode in found[0]


@pytest.mark.unit
@pytest.mark.covers("#114 AC4")
def test_no_payload_sources_found_fails():
    assert problems({"sources": {}, "nodes": {}}) != []


# #216 AC21 --------------------------------------------------------------------
# The picks settlement marker and the manager panel file are read with explicit
# columns, like run_manifests: they are not payloads, so they carry no presence
# tests (#216 D2, D10). A new payload source still needs both.


@pytest.mark.unit
@pytest.mark.covers("#216 AC21")
@pytest.mark.parametrize("table", ["entry_picks_settlement", "manager_panel"])
def test_the_marker_and_panel_sources_need_no_presence_tests(table):
    built = manifest()
    built["sources"][source_id(table)] = {
        "resource_type": "source",
        "source_name": "fpl_raw",
        "name": table,
        "columns": {"season": {"name": "season", "meta": {}}},
    }
    assert problems(built) == []


@pytest.mark.unit
@pytest.mark.covers("#216 AC21")
def test_the_entry_picks_payload_source_without_presence_tests_fails():
    built = manifest()
    built["sources"][source_id("entry_picks")] = {
        "resource_type": "source",
        "source_name": "fpl_raw",
        "name": "entry_picks",
        "columns": {"picks.element": {"name": "picks.element", "meta": {}}},
    }
    found = problems(built)
    assert found and all("entry_picks" in line for line in found)
