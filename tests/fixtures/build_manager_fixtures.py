#!/usr/bin/env python
"""Add the manager-picks captures (#216) to tests/fixtures/raw/.

A companion to build_fixtures.py, which it does not touch: that tree's
element-summary, bootstrap-static, fixtures and event-status captures are
unchanged. Run it after build_fixtures.py, with an AWS session; it only reads
the bucket.

WHAT IT HOLDS
-------------
Two real managers of the 2026-27 panel, by id only (the payloads carry no
names):

    10187394  random cohort. Joined in gameweek 3: their first picks capture
              is gameweek 3 (the join week, #216 D6 as amended by O1), and
              ingest stored a pre-join 404 (an expected `not_found` capture
              under `_invalid/`) for gameweeks 1 and 2. Gameweeks 3 and 4 each have automatic subs
              (gameweek 4: 498 out, 41 in) and gameweek 4 a transfer cost of 8.
              Chip-free in both. Its gameweek 4 is the reconciliation's real
              sample: the 15 picks' multiplier x points sum to 56, which is
              `entry_history.points`; the cost is not taken out of it
              (measured 2026-10-22 over every one of 13,090 captures).
    8450051   self cohort. Joined in gameweek 1, captured for gameweeks 1-4.

Plus 10187394's gameweek 5 picks capture, with no gameweek 5 marker in the
tree: a captured gameweek whose settlement marker is absent, which the models
must hide (#216 D4).

Objects, all verbatim from S3 except where EDITED says otherwise:

    raw/fpl/entry-picks/2026-27/{gw}/{entry}/{date}/{run_id}/payload.json
    raw/fpl/_invalid/not_found/entry-picks/2026-27/{gw}/{entry}/{date}/{run_id}/
        response.body and metadata.json
    raw/fpl/_settlement/entry-picks/{gw}/marker.json, gameweeks 1-4
    raw/fpl/_panels/2026-27/manager-panel.json
    raw/fpl/_manifests/{date}/{run_id}/manifest.json for the two runs that
        wrote them: 20261021T055756Z-5b39a4 and 20261021T173314Z-d6b07d

No entry-history: the warehouse does not read it (#216 D6 as amended by O1).

EDITED
------
- Each run manifest's `captures[]` keeps only this tree's keys, so the capture
  index lists exactly what the tree holds. Its `objects` counts, keyed by
  endpoint identity (one per manager and gameweek), keep this tree's managers
  and every other family. Every other field, status and origin included, is
  the run's own.
- The panel's `entries` keeps the two managers, and `kept` (the random
  cohort's count) is set to 1 to match. `seed`, `drawn` and the rest are the
  real panel's.
- Each marker's `entries` is set to 2, the panel managers this tree holds; the
  real markers say 1,998. A marker vouches for every kept manager, so with a
  trimmed panel the real count would describe managers the tree does not have.
  This is the one synthetic value.

Payloads are written as their exact bytes, so each capture's content_sha256 in
its manifest describes the fixture file too.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BUCKET = "fpl-data-safari"
SEASON = "2026-27"
OUT_ROOT = Path(__file__).parent / "raw"

LATE_JOINER = 10187394
SELF_COHORT = 8450051
MANAGERS = (LATE_JOINER, SELF_COHORT)
MARKED_GAMEWEEKS = (1, 2, 3, 4)
UNMARKED_GAMEWEEK = 5
MANAGER_FAMILIES = ("entry-picks", "entry-history")  # every manager endpoint, trimmed alike

PICKS_RUNS = (("2026-10-21", "20261021T055756Z-5b39a4"), ("2026-10-21", "20261021T173314Z-d6b07d"))


def s3_bytes(key: str) -> bytes:
    proc = subprocess.run(
        ["aws", "s3", "cp", f"s3://{BUCKET}/{key}", "-"], capture_output=True
    )
    if proc.returncode != 0:
        sys.exit(f"failed to read s3://{BUCKET}/{key}\n{proc.stderr.decode().strip()}")
    return proc.stdout


def s3_list(prefix: str) -> list[str]:
    proc = subprocess.run(
        ["aws", "s3api", "list-objects-v2", "--bucket", BUCKET, "--prefix", prefix,
         "--query", "Contents[].Key", "--output", "json"],
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.exit(f"failed to list s3://{BUCKET}/{prefix}\n{proc.stderr.decode().strip()}")
    return json.loads(proc.stdout) or []


def write_bytes(key: str, body: bytes) -> None:
    path = OUT_ROOT / key.removeprefix("raw/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    print(f"  {path.relative_to(Path(__file__).parent)}  {len(body) / 1024:.1f} KiB")


def write_json(key: str, payload: dict) -> None:
    write_bytes(key, (json.dumps(payload, indent=1, sort_keys=True) + "\n").encode())


def picks_weeks(entry: int) -> tuple[int, ...]:
    if entry == LATE_JOINER:
        return (3, 4, UNMARKED_GAMEWEEK)
    return MARKED_GAMEWEEKS


def capture_keys() -> list[str]:
    """Every payload, invalid body and sidecar this tree copies."""
    keys = []
    for entry in MANAGERS:
        for gw in picks_weeks(entry):
            keys += s3_list(f"raw/fpl/entry-picks/{SEASON}/{gw}/{entry}/")
    for gw in (1, 2):
        keys += s3_list(f"raw/fpl/_invalid/not_found/entry-picks/{SEASON}/{gw}/{LATE_JOINER}/")
    # The tree holds payloads and invalid bodies, plus each invalid body's
    # sidecar; payload sidecars are never read, as elsewhere in the tree.
    return [k for k in keys if k.endswith(("payload.json", "response.body"))
            or "/_invalid/" in k]


def main() -> None:
    keys = capture_keys()
    for key in keys:
        write_bytes(key, s3_bytes(key))

    indexed = {k for k in keys if not k.endswith("metadata.json")}
    for date, run_id in PICKS_RUNS:
        key = f"raw/fpl/_manifests/{date}/{run_id}/manifest.json"
        manifest = json.loads(s3_bytes(key))
        manifest["captures"] = [c for c in manifest["captures"] if c["key"] in indexed]
        endpoints = {c["endpoint"] for c in manifest["captures"]}
        manifest["objects"] = {
            endpoint: counts
            for endpoint, counts in manifest["objects"].items()
            if endpoint in endpoints or endpoint.split("/")[0] not in MANAGER_FAMILIES
        }
        write_json(key, manifest)

    for gw in MARKED_GAMEWEEKS:
        key = f"raw/fpl/_settlement/entry-picks/{gw}/marker.json"
        marker = json.loads(s3_bytes(key))
        marker["entries"] = len(MANAGERS)
        write_json(key, marker)

    key = f"raw/fpl/_panels/{SEASON}/manager-panel.json"
    panel = json.loads(s3_bytes(key))
    panel["entries"] = [e for e in panel["entries"] if e["entry_id"] in MANAGERS]
    panel["kept"] = sum(1 for e in panel["entries"] if e["cohort"] == "random")
    write_json(key, panel)


if __name__ == "__main__":
    main()
