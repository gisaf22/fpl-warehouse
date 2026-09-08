#!/usr/bin/env python
"""Regenerate tests/fixtures/raw/ — the checked-in raw capture the unit and
integration tiers build against.

WHY THIS EXISTS
---------------
`raw_root` defaults to s3://fpl-data-safari/raw, so every dbt model build read
the live bucket — ~26k objects, ~8 minutes, and an AWS session. That made the
`unit` and `integration` tiers neither fast nor hermetic: a PR check could not
run them without credentials, and CI had no route to the bucket. This tree is
the fixture the fast tiers build against instead. `--target fixtures` points
`raw_root` here (see profiles.yml), and nothing in that path touches S3.

The tree mirrors fpl-ingest's real key layout exactly, because the staging
models parse capture identity out of the object key itself:

    raw/fpl/element-summary/{fpl_id}/{extraction_date}/{run_id}/payload.json
    raw/fpl/bootstrap-static/{extraction_date}/{run_id}/payload.json

CAPTURES
--------
Three real runs, chosen so the fixture spans a settlement transition and a
mid-season transfer rather than a single moment:

    R1  2026-08-29 19:11  20260829T191108Z-b12d19   round 2 still provisional
    R2  2026-08-31 20:36  20260831T203609Z-227b9b   round 2 scores in, ICT not
    R3  2026-09-06 19:10  20260906T191056Z-6d5820   fully ratified; latest

Three captures of the same key is the point. A single-capture fixture passes
every dedup assertion in the integration tier vacuously — there is nothing to
collapse — which is the failure mode CLAUDE.md warns about under "Making the
fast tiers a real PR check".

WHAT EACH PLAYER COVERS
-----------------------
426, 427  Normal case. Both played rounds 1 and 2. Their round-2 key carries a
          provisional capture in R1 (NULL scores, ICT "0.0") and a ratified one
          in R3, so fct_test_player_fixture_ratified_preferred has a real
          provisional row to reject rather than passing on an empty set. R2
          catches the partial settlement FPL actually publishes: scores are in
          (5-2) and points are final (23) while the whole ICT family still
          reads "0.0" — the corruption class the dedup rule exists to prevent.

166       Ghost transfer — the retracted-row case, identified in Phase 2 and
          documented in CLAUDE.md under "Retracted history rows". This player
          transferred mid-season, and FPL published then withdrew a round-2 row
          for their former club's fixture:

              R1  fixture 16 (round 2), provisional
              R2  fixture 16 (round 2), RATIFIED — scores 4-3
              R3  fixture 16 absent; fixture 20 in its place

          The ratified R2 capture is why this fixture is worth checking in.
          Staging accumulates every capture, so fixture 16 survives there
          forever, and the ratified-preference rule cannot drop it — the ghost
          is itself ratified. Only the "present in the player's latest capture"
          rule removes it. Without this fixture,
          fct_test_player_fixture_no_retracted_rows has nothing to catch.

611       Blank gameweek. Present in bootstrap-static `elements` in all three
          captures — so the spine gives them a row for every finished round —
          but their element-summary carries no round-1 history row at all.
          fct_player_gameweek must therefore show round 1 with fixture_count 0
          rather than dropping the row, which is the original bug the whole
          rebuild exists to fix. Exercises
          fct_test_player_gameweek_blank_round_is_zero.

233       Double gameweek — SYNTHETIC, the only edited data in this tree. No
          real double gameweek has occurred this season (verified in Phase 2;
          live fixture_count never exceeds 1), so one is constructed here the
          same way Phase 2 verified DGW handling: this player's real round-2
          history row is duplicated with a different `fixture` id and
          `kickoff_time`, every other field left exactly as captured. See
          SYNTHETIC_DGW below for the two changed values.

          Gives fct_player_gameweek a fixture_count of 2, so
          fct_test_player_gameweek_grain_uniqueness (a double is one row, not
          two) and fct_test_player_gameweek_fixture_count_matches assert
          something at 2+ instead of only ever seeing 0 and 1.

TRIMMING
--------
element-summary payloads are checked in whole: every history row of every
captured object, ~16-21 KB each. The only content changes are player 233's
synthetic row and the `_fixture_note` key added to every file. They are
re-serialised pretty-printed and key-sorted rather than stored byte-for-byte,
so a regeneration produces a readable diff instead of one reflowed line; the
values themselves are exactly as captured.

bootstrap-static is trimmed, because the real object is 1.65 MB and 99% of it
is unread. `elements` is filtered to the five players above and `events` kept
whole (all 38, so the round calendar the spine is built from is real). Every
other top-level key is dropped; the staging models read only these two. The
element and event objects themselves are verbatim.

`_fixture_note` is a top-level key added to every payload saying what that file
covers. JSON has no comment syntax, and the models select named fields out of
`history` / `elements` / `events`, so an extra top-level key is inert —
`union_by_name` surfaces it as a column nothing references.

REGENERATING
------------
Needs an AWS session, unlike the fixtures themselves:

    eval "$(aws configure export-credentials --format env)"
    python tests/fixtures/build_fixtures.py

Rewrites the tree in place. Re-run it only to add a case or refresh a capture;
the point of checking the tree in is that ordinary test runs never need S3.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BUCKET = "fpl-data-safari"
RAW_PREFIX = "raw/fpl"
OUT_ROOT = Path(__file__).parent / "raw" / "fpl"

# (run_id, extraction_date) — see CAPTURES above.
RUNS = [
    ("20260829T191108Z-b12d19", "2026-08-29"),
    ("20260831T203609Z-227b9b", "2026-08-31"),
    ("20260906T191056Z-6d5820", "2026-09-06"),
]

# fpl_id -> the note stamped into that player's payloads.
PLAYERS = {
    166: "Ghost transfer. Round-2 fixture 16 is published provisionally in the "
         "first capture, RATIFIED in the second, and absent from the third — "
         "FPL retracted it after the player changed clubs, replacing it with "
         "fixture 20. Dedup cannot drop it (it is ratified); only the "
         "latest-capture rule can. Feeds "
         "fct_test_player_fixture_no_retracted_rows.",
    233: "SYNTHETIC double gameweek. The round-2 history row is duplicated "
         "with a different fixture id and kickoff time; all other fields are "
         "as captured. No real double gameweek exists in the live data yet, so "
         "this is the only way fixture_count 2 gets asserted. Feeds "
         "fct_test_player_gameweek_grain_uniqueness and "
         "fct_test_player_gameweek_fixture_count_matches.",
    426: "Normal case, rounds 1 and 2. Round 2 is captured provisionally "
         "(NULL scores, ICT \"0.0\"), then part-settled (scores and points "
         "final, ICT still \"0.0\"), then fully ratified. Feeds "
         "fct_test_player_fixture_ratified_preferred.",
    427: "Normal case, rounds 1 and 2 — second player, same settlement "
         "sequence as 426, so dedup is asserted over more than one key.",
    611: "Blank gameweek. In bootstrap-static `elements` for every capture, so "
         "the spine gives them a row in both finished rounds, but their "
         "history carries no round-1 fixture. fct_player_gameweek must show "
         "round 1 with fixture_count 0, not drop the row. Feeds "
         "fct_test_player_gameweek_blank_round_is_zero.",
}

# The synthetic double gameweek, stated in one place so the edit is auditable.
# Player 233's real round-2 row (fixture 12) is copied per capture and these two
# fields replaced; the kickoff sits between round 2's deadline (2026-08-28
# 17:30) and round 3's (2026-09-04 17:30), which is where a rearranged second
# round-2 fixture would really fall. `fixture` 999 is outside the real 1-380
# range for a season, so a synthetic row can never be mistaken for a captured
# one — grep 999 to find it.
SYNTHETIC_DGW = {
    "fpl_id": 233,
    "round": 2,
    "source_fixture": 12,
    "fixture": 999,
    "kickoff_time": "2026-09-01T19:00:00Z",
}


def s3_get(key: str) -> dict:
    """Fetch one object and parse it. Fails loudly — a partial tree is worse
    than none, because the gap shows up as a mysterious test failure later."""
    proc = subprocess.run(
        ["aws", "s3", "cp", f"s3://{BUCKET}/{key}", "-"],
        capture_output=True,
    )
    if proc.returncode != 0:
        sys.exit(
            f"failed to read s3://{BUCKET}/{key}\n"
            f"{proc.stderr.decode().strip()}\n"
            'Run: eval "$(aws configure export-credentials --format env)"'
        )
    return json.loads(proc.stdout)


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"  {path.relative_to(OUT_ROOT.parent.parent)}  "
          f"{path.stat().st_size / 1024:.1f} KiB")


def add_synthetic_dgw(payload: dict) -> dict:
    """Duplicate player 233's real round-2 row under a new fixture id."""
    source = [
        h for h in payload["history"]
        if h["fixture"] == SYNTHETIC_DGW["source_fixture"]
    ]
    if not source:
        sys.exit(
            f"player {SYNTHETIC_DGW['fpl_id']} has no fixture "
            f"{SYNTHETIC_DGW['source_fixture']} row to duplicate — the "
            "synthetic double gameweek would be silently missing"
        )
    dgw = dict(source[0])
    dgw["fixture"] = SYNTHETIC_DGW["fixture"]
    dgw["kickoff_time"] = SYNTHETIC_DGW["kickoff_time"]
    payload["history"] = payload["history"] + [dgw]
    return payload


def main() -> None:
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    for run_id, date in RUNS:
        print(f"{date} {run_id}")

        boot = s3_get(f"{RAW_PREFIX}/bootstrap-static/{date}/{run_id}/payload.json")
        write(
            OUT_ROOT / "bootstrap-static" / date / run_id / "payload.json",
            {
                "_fixture_note": (
                    "Trimmed bootstrap-static capture. `elements` is filtered "
                    f"to players {sorted(PLAYERS)} and `events` kept whole (all "
                    "38 rounds, so the spine's calendar is real). Every other "
                    "top-level key is dropped — stg_player reads `elements` "
                    "and stg_gameweek reads `events`, nothing else. The "
                    "element and event objects themselves are verbatim."
                ),
                "elements": [e for e in boot["elements"] if e["id"] in PLAYERS],
                "events": boot["events"],
            },
        )

        for fpl_id, note in PLAYERS.items():
            payload = s3_get(
                f"{RAW_PREFIX}/element-summary/{fpl_id}/{date}/{run_id}/payload.json"
            )
            if fpl_id == SYNTHETIC_DGW["fpl_id"]:
                payload = add_synthetic_dgw(payload)
            payload["_fixture_note"] = note
            write(
                OUT_ROOT / "element-summary" / str(fpl_id) / date / run_id
                / "payload.json",
                payload,
            )


if __name__ == "__main__":
    main()
