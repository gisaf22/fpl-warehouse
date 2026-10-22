"""Settled entry-picks gameweeks compact into one parquet per gameweek (#216 D8).

A gameweek is compacted once ingest's settlement marker for it exists
(`raw/fpl/_settlement/entry-picks/<gw>/marker.json`, D2); before that it is
not settled, staging hides it (D4), and nothing is written. Each compacted
gameweek is

    <dest>/fpl/entry-picks/season=<S>/gameweek=<G>/part.parquet
    <dest>/fpl/entry-picks/_manifest/season=<S>/gameweek=<G>.json

The parquet is the JSON read of the gameweek's payload files, `filename`
kept, as for element-summary (docs/compacted.md). The manifest is written
last, only after the files reconcile with the capture index, so a gameweek
without one is not compacted. A gameweek with a manifest is never rewritten:
its picks cannot change once settled. Invalid captures under `_invalid/` are
not payloads and never enter the parquet. The production destination is
written only by a scheduled run, the element-summary writer's gate.

The tree here is synthetic and built in each test; the real samples are in
tests/fixtures/raw (tests/fixtures/build_manager_fixtures.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pytest

from compact_element_summary import DestinationRefused

SEASON = "2026-27"
RUN = "20261021T173314Z-d6b07d"
DAY = "2026-10-21"


def picks(entry_id: int, gameweek: int) -> dict:
    return {
        "active_chip": None,
        "automatic_subs": [],
        "entry_history": {"event": gameweek, "points": 50, "event_transfers_cost": 0},
        "picks": [
            {"element": entry_id % 600 + slot, "position": slot, "multiplier": 1,
             "is_captain": slot == 1, "is_vice_captain": slot == 2, "element_type": 1}
            for slot in range(1, 16)
        ],
    }


def build_tree(
    raw_root: Path,
    captures: dict[int, list[int]],
    marked: set[int],
    *,
    unindexed: set[tuple[int, int]] = frozenset(),
    not_found: set[tuple[int, int]] = frozenset(),
) -> None:
    """`captures` maps gameweek -> entry ids with a payload; `marked` the markers."""
    index = []
    for gameweek, entries in captures.items():
        for entry_id in entries:
            rel = f"fpl/entry-picks/{SEASON}/{gameweek}/{entry_id}/{DAY}/{RUN}/payload.json"
            body = json.dumps(picks(entry_id, gameweek)).encode()
            (raw_root / rel).parent.mkdir(parents=True, exist_ok=True)
            (raw_root / rel).write_bytes(body)
            if (gameweek, entry_id) in unindexed:
                continue
            index.append(capture(rel, body, gameweek, entry_id, usable=True))
    for gameweek, entry_id in not_found:
        rel = (f"fpl/_invalid/not_found/entry-picks/{SEASON}/{gameweek}/{entry_id}/"
               f"{DAY}/{RUN}/response.body")
        body = b'{"detail":"Not found."}'
        (raw_root / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw_root / rel).write_bytes(body)
        index.append(capture(rel, body, gameweek, entry_id, usable=False))
    manifest = {
        "run_id": RUN, "extraction_date": DAY, "status": "SUCCESS",
        "raw_contract_version": "2.8.0", "captures": index,
    }
    path = raw_root / f"fpl/_manifests/{DAY}/{RUN}/manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest))
    for gameweek in marked:
        marker = raw_root / f"fpl/_settlement/entry-picks/{gameweek}/marker.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            "endpoint": "entry-picks", "event": gameweek, "run_id": RUN,
            "recorded_at": "2026-10-21T17:40:00Z",
            "entries": len(captures.get(gameweek, [])) + sum(
                1 for g, _ in not_found if g == gameweek),
        }))


def capture(rel: str, body: bytes, gameweek: int, entry_id: int, *, usable: bool) -> dict:
    entry = {
        "key": f"raw/{rel}",
        "endpoint": f"entry-picks/{SEASON}/{gameweek}/{entry_id}",
        "received_at": "2026-10-21T17:35:00Z",
        "content_sha256": hashlib.sha256(body).hexdigest(),
        "content_length": len(body),
        "http_status": 200 if usable else 404,
        "shape_ok": usable,
        "usable": usable,
        "season": SEASON,
    }
    if not usable:
        entry.update({"class": "not_found", "expected": True})
    return entry


def parquet(dest: Path, gameweek: int) -> Path:
    return dest / f"fpl/entry-picks/season={SEASON}/gameweek={gameweek}/part.parquet"


def manifest(dest: Path, gameweek: int) -> Path:
    return dest / f"fpl/entry-picks/_manifest/season={SEASON}/gameweek={gameweek}.json"


@pytest.fixture
def roots(tmp_path):
    return tmp_path / "raw", tmp_path / "compacted"


@pytest.fixture
def compact_entry_picks():
    # Imported per test, so a missing writer fails each test, not collection.
    import compact_entry_picks

    return compact_entry_picks


@pytest.mark.integration
@pytest.mark.covers("#216 AC15")
def test_a_marked_gameweeks_parquet_equals_the_json_read_of_its_payloads(roots, compact_entry_picks):
    raw, dest = roots
    build_tree(raw, {3: [8450051, 10187394]}, marked={3})

    compact_entry_picks.compact_settled_gameweeks(str(raw), str(dest))

    files = sorted(str(p) for p in raw.glob("fpl/entry-picks/*/3/*/*/*/payload.json"))
    expected = duckdb.sql(
        f"select * from read_json({files}, union_by_name = true, filename = true) "
        "order by filename"
    ).fetchall()
    actual = duckdb.sql(
        f"select * from read_parquet('{parquet(dest, 3)}', hive_partitioning = false) "
        "order by filename"
    ).fetchall()
    assert actual == expected
    record = json.loads(manifest(dest, 3).read_text())
    assert record["payload_files"] == record["parquet_rows"] == 2


@pytest.mark.integration
@pytest.mark.covers("#216 AC15")
def test_a_gameweek_without_a_marker_is_not_compacted(roots, compact_entry_picks):
    raw, dest = roots
    build_tree(raw, {3: [8450051], 4: [8450051]}, marked={3})

    compact_entry_picks.compact_settled_gameweeks(str(raw), str(dest))

    assert manifest(dest, 3).exists()
    assert not parquet(dest, 4).exists()
    assert not manifest(dest, 4).exists()


@pytest.mark.integration
@pytest.mark.covers("#216 AC15")
def test_a_compacted_gameweek_is_never_rewritten(roots, compact_entry_picks):
    raw, dest = roots
    build_tree(raw, {3: [8450051]}, marked={3})
    compact_entry_picks.compact_settled_gameweeks(str(raw), str(dest))
    written = manifest(dest, 3).read_text()
    stamp = parquet(dest, 3).stat().st_mtime_ns

    compact_entry_picks.compact_settled_gameweeks(str(raw), str(dest))

    assert manifest(dest, 3).read_text() == written
    assert parquet(dest, 3).stat().st_mtime_ns == stamp


@pytest.mark.integration
@pytest.mark.covers("#216 AC15")
def test_a_payload_missing_from_the_index_leaves_the_gameweek_uncompacted(roots, compact_entry_picks):
    raw, dest = roots
    build_tree(raw, {3: [8450051, 10187394]}, marked={3}, unindexed={(3, 10187394)})

    results = compact_entry_picks.compact_settled_gameweeks(str(raw), str(dest))

    assert not manifest(dest, 3).exists()
    assert any(not r.ok and "10187394" in r.reason for r in results)


@pytest.mark.integration
@pytest.mark.covers("#216 AC15")
def test_invalid_captures_never_enter_the_parquet(roots, compact_entry_picks):
    raw, dest = roots
    # 10187394 had not joined in gameweek 1: ingest stored a pre-join 404.
    build_tree(raw, {1: [8450051]}, marked={1}, not_found={(1, 10187394)})

    compact_entry_picks.compact_settled_gameweeks(str(raw), str(dest))

    names = duckdb.sql(
        f"select filename from read_parquet('{parquet(dest, 1)}', hive_partitioning = false)"
    ).fetchall()
    assert len(names) == 1
    assert "/_invalid/" not in names[0][0]
    assert json.loads(manifest(dest, 1).read_text())["payload_files"] == 1


@pytest.mark.unit
@pytest.mark.covers("#216 AC15")
@pytest.mark.parametrize("event", [None, "workflow_dispatch", "pull_request", "push"])
def test_the_production_destination_is_refused_unless_scheduled(roots, compact_entry_picks, event):
    raw, _ = roots
    build_tree(raw, {3: [8450051]}, marked={3})

    with pytest.raises(DestinationRefused, match="schedule"):
        compact_entry_picks.compact_settled_gameweeks(
            str(raw), "s3://fpl-data-safari/compacted", event_name=event
        )
