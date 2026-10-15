"""Builds a synthetic raw element-summary tree for the compaction writer's tests (#193).

The layout mirrors ingest's: payloads at
`<raw_root>/fpl/element-summary/<fpl_id>/<capture day>/<run_id>/payload.json`, run
manifests at `<raw_root>/fpl/_manifests/<extraction_date>/<run_id>/manifest.json`, and
the backfill catalog at `<raw_root>/fpl/_catalog/backfill/<run_id>.json`. A capture's
key is `raw/` plus its path below `raw_root`, as in the capture index.

Each run is indexed by its manifest's `captures[]` (contract 2.1.0+), by a catalog
entry (older runs), or by neither, the precedence of base_capture_index.sql.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Capture:
    fpl_id: int
    history: list[dict]
    received_at: str


@dataclass
class Run:
    run_id: str
    extraction_date: str
    captures: list[Capture]
    # The date segment of each payload's key; defaults to extraction_date.
    capture_day: str | None = None
    status: str = "SUCCESS"
    index: str = "manifest"  # "manifest", "catalog" or "none"
    # Keys listed in the index with no payload file, or files left out of it.
    unindexed_fpl_ids: set[int] = field(default_factory=set)


def payload(history: list[dict]) -> dict:
    return {"fixtures": [], "history": history, "history_past": []}


def build_tree(raw_root: Path, runs: list[Run]) -> None:
    for run in runs:
        day = run.capture_day or run.extraction_date
        entries = []
        for capture in run.captures:
            rel = f"fpl/element-summary/{capture.fpl_id}/{day}/{run.run_id}/payload.json"
            path = raw_root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            body = json.dumps(payload(capture.history)).encode()
            path.write_bytes(body)
            if capture.fpl_id in run.unindexed_fpl_ids:
                continue
            entries.append(
                {
                    "content_length": len(body),
                    "content_sha256": hashlib.sha256(body).hexdigest(),
                    "endpoint": "element-summary",
                    "http_status": 200,
                    "key": f"raw/{rel}",
                    "received_at": capture.received_at,
                    "season": "2026-27",
                    "shape_ok": True,
                    "usable": True,
                }
            )
        # As ingest records it: one entry per object written, by endpoint/id.
        objects = {
            f"element-summary/{c.fpl_id}": {"attempted": 1, "failed": 0, "written": 1}
            for c in run.captures
        }
        manifest = {
            "run_id": run.run_id,
            "extraction_date": run.extraction_date,
            "status": run.status,
            "objects": objects,
        }
        if run.index == "manifest":
            manifest["raw_contract_version"] = "2.1.0"
            manifest["captures"] = entries
        manifest_path = (
            raw_root / "fpl" / "_manifests" / run.extraction_date / run.run_id / "manifest.json"
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest))
        if run.index == "catalog":
            catalog = raw_root / "fpl" / "_catalog" / "backfill" / f"{run.run_id}.json"
            catalog.parent.mkdir(parents=True, exist_ok=True)
            catalog.write_text(
                json.dumps({"run_id": run.run_id, "scope": "live", "captures": entries})
            )


def history_row(fixture: int, expected_goals) -> dict:
    return {"element": 1, "fixture": fixture, "round": 1, "total_points": 2,
            "expected_goals": expected_goals}
