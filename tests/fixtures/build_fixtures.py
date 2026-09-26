#!/usr/bin/env python
"""Regenerate tests/fixtures/raw/ — the checked-in raw capture the unit and
integration tiers build against.

WHY THIS EXISTS
---------------
`raw_root` defaults to s3://fpl-data-safari/raw, so every dbt model build read
the live bucket — ~74k objects, 7-16 minutes, and an AWS session. That made the
`unit` and `integration` tiers neither fast nor hermetic: a PR check could not
run them without credentials, and CI had no route to the bucket. This tree is
the fixture the fast tiers build against instead. `--target fixtures` points
`raw_root` here (see profiles.yml), and nothing in that path touches S3.

The tree mirrors fpl-ingest's real key layout exactly, because the staging
models parse capture identity out of the object key itself:

    raw/fpl/element-summary/{fpl_id}/{extraction_date}/{run_id}/payload.json
    raw/fpl/bootstrap-static/{extraction_date}/{run_id}/payload.json
    raw/fpl/event-status/{extraction_date}/{run_id}/payload.json
    raw/fpl/fixtures/{extraction_date}/{run_id}/payload.json

CAPTURES
--------
Four real runs, chosen so the fixture spans a settlement transition, a
mid-season transfer and a departure rather than a single moment:

    R1  2026-08-29 19:11  20260829T191108Z-b12d19   round 2 still provisional
    R2  2026-08-31 20:36  20260831T203609Z-227b9b   round 2 scores in, ICT not
    R3  2026-09-06 19:10  20260906T191056Z-6d5820   fully ratified
    R4  2026-09-14 21:12  20260914T211204Z-a730c3   rounds 3-4 played; latest

Note the naming: R1..R4 are *captures* (runs), not gameweek rounds. The
calendar they carry is a separate axis — R4's `events` report rounds 1-4
finished, after the synthetic flip described under SYNTHETIC_FINISHED.

Several captures of the same key is the point. A single-capture fixture passes
every dedup assertion in the integration tier vacuously — there is nothing to
collapse — which is the failure mode CLAUDE.md warns about under "Making the
fast tiers a real PR check".

EVENT-STATUS CAPTURES
---------------------
event-status is captured on its own axis, NOT on the four runs above, and
EVENT_STATUS_RUNS below is deliberately a different list. Two reasons:

  1. The endpoint serves only the *current* round's match dates — a finished
     round rolls out of the window completely. So whether a round is ever seen
     ratified depends entirely on which dates were captured, and the four runs
     above happen to land only on in-progress days. Built from those alone, the
     fixture would report every round unratified and the ratified path would
     never be exercised.

  2. The endpoint is a different key layout with no player fan-out, so there is
     nothing tying its captures to the element-summary runs.

The five captures below are all real and unedited, chosen to give the fixture
one round in each state the served layer must handle:

    round 1  absent from every capture  -> the pre-history fallback
    round 2  seen ratified  (09-02)     -> ratified via the source
    round 3  seen ratified  (09-08)     -> ratified via the source
    round 4  provisional only (09-14)   -> the disagreement case

Round 4 is the regression test for the fix, and it is real rather than
synthetic. In R4's element-summary capture every round-4 history row already
carries a final scoreline, so the retired inference (`both scores non-NULL`)
called round 4 ratified. event-status on the same day reports `points: "p"`
and `bonus_added: false` — the round was played but bonus points had not been
applied. A fixture tree without the 09-14 event-status capture would let the
old and new logic agree everywhere and prove nothing.

The 08-29 and 09-06 captures are included so a round is present in the
provisional state *before* the capture that ratifies it, which is what makes
the "ever observed ratified" rollup in int_round_ratification non-vacuous:
with only the ratified captures, bool_or would have nothing to override.

R4 exists so the departed player (4, below) has finished rounds *after* their
departure. With R1-R3 alone the only finished rounds were 1 and 2, both of
which that player actually played, so the fixture could prove they stay in the
spine but never that their post-departure rounds read fixture_count = 0.

HISTORY SEASON
--------------
A second tree sits beside the live one:

    history/{season}/fpl/bootstrap-static/{date}/{run_id}/payload.json
    history/{season}/fpl/element-summary/{fpl_id}/{date}/{run_id}/payload.json
    history/{season}/fpl/fixtures/{date}/{run_id}/payload.json

It holds 2025-26, ported from the pre-S3 archive by
scripts/rekey_history_season.py and trimmed here the same way the live tree is.
Its purpose is to make the fast tiers multi-season, so the season partitioning
in every dedup, retraction check and spine step is exercised on a PR instead of
only against live S3 after the fact.

One capture, not four: that season really was captured once, by a single run
whose id (20260526T034626Z-2a6b73) the re-key script derives from the archived
bootstrap's own digest. Every recency comparison over it is therefore a
singleton — which is the point, and what the ratification override relies on.

The calendar is kept whole and unedited: all 38 rounds report finished and
data_checked, which is what fct_test_player_fixture_closed_season_settled
requires before the closed-season override may call these rows ratified. No
synthetic edit of any kind is applied to this tree — unlike the live one, it
needs none, because the season is over.

Its fixtures payload is the archive's single end-of-season snapshot, carried
as-is: every fixture finished, difficulty as it stood at season end. That is
what makes a pre-kickoff difficulty impossible to claim for this season
downstream — there is no earlier capture to take one from.

event-status is deliberately absent: FPL serves only the current round, so no
capture of a finished season exists. That absence is exactly the condition the
closed-season override exists to handle.

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

          The same transfer seen through the fixtures endpoint: round 1's
          fixture 10 was played for the former club, and so was the retracted
          fixture 16; every fixture from round 2 on is the new club's. Both
          clubs resolve from each fixture's home/away side. Feeds
          stg_test_fixture_tree_transfer_fixtures_and_clubs_resolve.

611       Blank gameweek. Present in bootstrap-static `elements` in all three
          captures — so the spine gives them a row for every finished round —
          but their element-summary carries no round-1 history row at all.
          fct_player_gameweek must therefore show round 1 with fixture_count 0
          rather than dropping the row, which is the original bug the whole
          rebuild exists to fix. Exercises
          fct_test_player_gameweek_blank_round_is_zero.

4         Departed player — SYNTHETIC removal, the second edited case in this
          tree. Played rounds 1 and 2 for real (90 min / 5 pts, 76 min /
          6 pts), is present in `elements` for R1 and R2, and is then removed
          from R3's `elements` entirely, with no R3 element-summary capture
          either — which is how a real departure looks: FPL stops publishing
          the player at all.

          No real departure has occurred this season (verified 2026-09-14
          across all 128 live bootstrap-static captures: the union of
          `elements` is 658 players and the latest capture is also 658, so the
          list has only ever grown, 622 -> 658). So this removal is
          constructed, for the same reason the double gameweek below is.

          Without it, int_player_gameweek_spine's union across all captures is
          indistinguishable from the latest-capture-only build it replaced:
          every capture in this tree would hold the same five players, and
          both fct_test_player_gameweek_spine_covers_departed_players and
          fct_test_player_gameweek_covers_every_fixture would pass vacuously.
          Feeds those two, with
          stg_test_player_departure_present asserting the case is really here.

          The post-departure tail is covered too, which is what R4 and
          SYNTHETIC_FINISHED are for. R4's calendar reports rounds 1-4
          finished, so the spine gives this player four rows: rounds 1 and 2
          with their real fixtures (fixture_count 1), and rounds 3 and 4 with
          no fixture at all (fixture_count 0), because no element-summary was
          written for them after R2. Two zero rounds rather than one, so the
          assertion is not resting on a single row. Feeds
          fct_test_player_gameweek_departed_player_zero_tail.

233       Double gameweek — SYNTHETIC, the other edited case in this tree. No
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

          The fixtures endpoint gets the matching synthetic row, so the double
          still resolves once a player's team is read through the fixture
          (team per fixture). Fixture 12 is copied under the same `id` and
          `kickoff_time` as the history row; every other field, `code` and
          `pulse_id` included, is fixture 12's as captured. The live season
          in this tree therefore holds 381 fixtures, not 380 — nothing may
          assume 380 for the fixture tree (the 380 publish floor is a
          live-data check). Feeds
          stg_test_fixture_tree_double_gameweek_fixtures_resolve.

TRIMMING
--------
element-summary payloads are checked in whole: every history row of every
captured object, ~16-21 KB each. The only content changes are player 233's
synthetic row and the `_fixture_note` key added to every file. They are
re-serialised pretty-printed and key-sorted rather than stored byte-for-byte,
so a regeneration produces a readable diff instead of one reflowed line; the
values themselves are exactly as captured.

bootstrap-static is trimmed, because the real object is 1.65 MB and 99% of it
is unread. `elements` is filtered to the six players above; `events` (all 38,
so the round calendar the spine is built from is real), `teams` (all 20) and
`element_types` (the positions) are kept whole. Every other top-level key is
dropped. The element, event, team and position objects themselves are
verbatim.

fixtures is trimmed by one key. Every fixture of the season is kept — all 380,
so a dimension built over the tree sees the real calendar — and every field of
each is verbatim except `stats`, the per-fixture list of per-player events
(goals, assists, bps, ...), which is dropped. It is most of the payload:
pretty-printed, the 2025-26 snapshot is 1.8 MB with it and 135 KiB without,
and each live capture 320 KiB against 136 KiB. Nothing reads it — the same
per-player figures reach the warehouse through element-summary. If a model
ever needs it, stop dropping it in `trim_fixtures` and regenerate.

The fixtures payload is a JSON array, not an object, so it cannot carry a
`_fixture_note`: any added element would read as a fixture. This docstring is
its note.

Two departures from "filtered, but verbatim" in the bootstrap payloads, plus
the synthetic fixture 999 in the fixtures payloads (see 233 above):
player 4 is dropped from `elements` for R3 and R4 and given no element-summary
capture in either (see DEPARTED), and round 4's `finished` flag is set in R4's
`events` (see SYNTHETIC_FINISHED). The element and event objects are otherwise
untouched.

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

# The ported history season — see HISTORY SEASON below.
ARCHIVE_PREFIX = "archive/2025-26/raw"
HISTORY_SEASON = "2025-26"
HISTORY_RUN_ID = "20260526T034626Z-2a6b73"
HISTORY_DATE = "2026-05-26"
HISTORY_OUT_ROOT = Path(__file__).parent / "history" / HISTORY_SEASON / "fpl"

# 2025-26 fpl_ids, chosen so the fixture exercises what a second season breaks.
# Three of them (4, 166, 426) are ids the live tree also uses — for different
# people — and two (119, 449) are the 2025-26 identities of live players 427 and
# 426. Both shapes must survive: an id that means two people across seasons, and
# a person who changes id.
HISTORY_PLAYERS = {
    4:   "Id collision. In 2026-27 fpl_id 4 is Gabriel; here it is a different "
         "player entirely. Any dedup, retraction check or spine step that "
         "partitions by fpl_id without season collapses these two people into "
         "one row.",
    166: "Id collision, second case — 2026-27's fpl_id 166 is N.Jackson, whose "
         "2025-26 id was 251. Also the id whose live rows carry the retracted "
         "ghost fixture, so a season-blind retraction check would drop this "
         "season's rows as 'not in the player's latest capture'.",
    426: "Id collision, third case, against the live tree's normal-settlement "
         "player 426 (B.Fernandes this season).",
    449: "The same person as the live tree's 426 — B.Fernandes, code 141746, "
         "id 449 in 2025-26. player_code is the only thing that links them, "
         "and nothing in any model may join on it.",
    119: "The same person as the live tree's 427 — Mbeumo, code 446008, id 119 "
         "in 2025-26.",
}

# (run_id, extraction_date) — see CAPTURES above.
RUNS = [
    ("20260829T191108Z-b12d19", "2026-08-29"),
    ("20260831T203609Z-227b9b", "2026-08-31"),
    ("20260906T191056Z-6d5820", "2026-09-06"),
    ("20260914T211204Z-a730c3", "2026-09-14"),
]

# (run_id, extraction_date) for event-status — a separate axis from RUNS above.
# See EVENT-STATUS CAPTURES for why these dates and not the four runs.
EVENT_STATUS_RUNS = [
    ("20260829T191108Z-b12d19", "2026-08-29"),  # round 2 provisional
    ("20260902T071919Z-34bc3a", "2026-09-02"),  # round 2 RATIFIED
    ("20260906T191056Z-6d5820", "2026-09-06"),  # round 3 provisional
    ("20260908T071742Z-02f914", "2026-09-08"),  # round 3 RATIFIED
    ("20260914T211204Z-a730c3", "2026-09-14"),  # round 4 provisional — the
                                                # disagreement case
]

# fpl_id -> the note stamped into that player's payloads.
PLAYERS = {
    4:   "SYNTHETIC departure. Present in `elements` and captured normally for "
         "R1 and R2, then absent from R3 and R4 with no element-summary "
         "capture in either — a player who left the league. Played rounds 1 "
         "and 2 for real, so their fixtures must still reach "
         "fct_player_gameweek via the spine's union across all captures, and "
         "rounds 3-4 must read fixture_count = 0. Feeds "
         "fct_test_player_gameweek_spine_covers_departed_players, "
         "fct_test_player_gameweek_departed_player_zero_tail, and gives "
         "fct_test_player_gameweek_covers_every_fixture something to catch.",
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

# The synthetic departure, stated in one place so the edit is auditable.
# This player is written for every run up to and including `last_run_id`, and
# omitted from both `elements` and element-summary for every run after it. FPL
# drops a departed player from `elements` and stops serving their
# element-summary together, so omitting only one of the two would fabricate a
# state the source never produces.
DEPARTED = {
    "fpl_id": 4,
    "last_run_id": "20260831T203609Z-227b9b",
}

# The synthetic calendar flip, stated in one place so the edit is auditable.
# Round 4 was played and fully ratified by the R4 capture — every non-departed
# player in this tree has a round-4 history row with both scores present — but
# FPL had not yet flipped the round's `finished` flag, which it does only once
# the round fully settles (it was still false at 2026-09-14 21:12, and true
# within a day). int_player_gameweek_spine gates on exactly that flag, so
# without this flip round 4 is absent from the spine and the departed player
# has only one post-departure round instead of two.
#
# This edits one boolean on one event object in one capture. Nothing else in
# `events` is touched, and no history row anywhere is altered: the round-4
# fixture data the flip exposes is entirely as captured.
SYNTHETIC_FINISHED = {
    "run_id": "20260914T211204Z-a730c3",
    "round": 4,
}

# The synthetic double gameweek, stated in one place so the edit is auditable.
# Player 233's real round-2 row (fixture 12) is copied per capture and these two
# fields replaced; the kickoff sits between round 2's deadline (2026-08-28
# 17:30) and round 3's (2026-09-04 17:30), which is where a rearranged second
# round-2 fixture would really fall. `fixture` 999 is outside the real 1-380
# range for a season, so a synthetic row can never be mistaken for a captured
# one — grep 999 to find it.
#
# The fixtures endpoint gets the matching row: fixture 12 copied as fixture 999
# with this kickoff, every other field as captured (add_synthetic_dgw_fixture).
SYNTHETIC_DGW = {
    "fpl_id": 233,
    "round": 2,
    "source_fixture": 12,
    "fixture": 999,
    "kickoff_time": "2026-09-01T19:00:00Z",
}


def s3_get(key: str) -> dict | list:
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


def write(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    print(f"  {path.relative_to(Path(__file__).parent)}  "
          f"{path.stat().st_size / 1024:.1f} KiB")


def build_history_season() -> None:
    """Write the trimmed 2025-26 tree from the archived pre-S3 capture.

    Reads the archive rather than the re-keyed history tree, so this runs
    before scripts/rekey_history_season.py has ever touched S3 and depends on
    nothing that script wrote.
    """
    if HISTORY_OUT_ROOT.exists():
        shutil.rmtree(HISTORY_OUT_ROOT)

    boot = s3_get(f"{ARCHIVE_PREFIX}/bootstrap.json")
    kept = sorted(HISTORY_PLAYERS)
    unsettled = [
        e["id"] for e in boot["events"]
        if not (e["finished"] and e["data_checked"])
    ]
    if unsettled:
        sys.exit(
            f"archived {HISTORY_SEASON} calendar reports rounds {unsettled} not "
            "finished and data_checked — the closed-season override would be "
            "asserting something the source does not say"
        )
    print(f"{HISTORY_SEASON} {HISTORY_RUN_ID}  (history)")
    write(
        HISTORY_OUT_ROOT / "bootstrap-static" / HISTORY_DATE / HISTORY_RUN_ID
        / "payload.json",
        {
            "_fixture_note": (
                f"Trimmed bootstrap-static for the ported {HISTORY_SEASON} "
                f"season. `elements` is filtered to players {kept}; "
                "`events` is kept whole — all 38 rounds, every one finished "
                "and data_checked, which is what the closed-season override is "
                "checked against — and so are `teams` and `element_types`. No "
                "synthetic edits. Sourced from "
                f"s3://{BUCKET}/{ARCHIVE_PREFIX}/bootstrap.json; the element, "
                "event, team and position objects are verbatim."
            ),
            "elements": [e for e in boot["elements"] if e["id"] in HISTORY_PLAYERS],
            "events": boot["events"],
            "teams": boot["teams"],
            "element_types": boot["element_types"],
        },
    )

    # The single end-of-season snapshot, carried as-is apart from `stats`.
    write(
        HISTORY_OUT_ROOT / "fixtures" / HISTORY_DATE / HISTORY_RUN_ID
        / "payload.json",
        trim_fixtures(s3_get(f"{ARCHIVE_PREFIX}/fixtures.json")),
    )

    for fpl_id, note in HISTORY_PLAYERS.items():
        payload = s3_get(f"{ARCHIVE_PREFIX}/players/{fpl_id}.json")
        payload["_fixture_note"] = note
        write(
            HISTORY_OUT_ROOT / "element-summary" / str(fpl_id) / HISTORY_DATE
            / HISTORY_RUN_ID / "payload.json",
            payload,
        )


def trim_fixtures(fixtures: list) -> list:
    """Drop `stats` from every fixture; keep every fixture and other field."""
    return [{k: v for k, v in f.items() if k != "stats"} for f in fixtures]


def add_synthetic_dgw_fixture(fixtures: list) -> list:
    """Add fixture 999 — a copy of fixture 12 — so the synthetic double's
    second history row resolves to a fixture. See SYNTHETIC_DGW."""
    source = [f for f in fixtures if f["id"] == SYNTHETIC_DGW["source_fixture"]]
    if not source or source[0]["event"] != SYNTHETIC_DGW["round"]:
        sys.exit(
            f"fixture {SYNTHETIC_DGW['source_fixture']} is missing or not in "
            f"round {SYNTHETIC_DGW['round']} — the synthetic double's fixture "
            "row would be silently wrong"
        )
    if any(f["id"] == SYNTHETIC_DGW["fixture"] for f in fixtures):
        sys.exit(
            f"fixture {SYNTHETIC_DGW['fixture']} already exists in the capture "
            "— the synthetic id is no longer outside the real range"
        )
    dgw = dict(source[0])
    dgw["id"] = SYNTHETIC_DGW["fixture"]
    dgw["kickoff_time"] = SYNTHETIC_DGW["kickoff_time"]
    return fixtures + [dgw]


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


def mark_synthetic_finished(events: list, run_id: str) -> list:
    """Flip `finished` on one round of one capture — see SYNTHETIC_FINISHED."""
    if run_id != SYNTHETIC_FINISHED["run_id"]:
        return events
    target = [e for e in events if e["id"] == SYNTHETIC_FINISHED["round"]]
    if not target:
        sys.exit(
            f"round {SYNTHETIC_FINISHED['round']} is not in the R4 calendar — "
            "the synthetic finished flag has nothing to set"
        )
    if target[0]["finished"]:
        sys.exit(
            f"round {SYNTHETIC_FINISHED['round']} is already finished in the "
            "captured calendar, so SYNTHETIC_FINISHED is now a no-op and "
            "misleading — drop it and let the real flag stand"
        )
    out = []
    for e in events:
        if e["id"] == SYNTHETIC_FINISHED["round"]:
            e = dict(e, finished=True)
        out.append(e)
    return out


def is_departed(fpl_id: int, run_id: str) -> bool:
    """True once the synthetic departure has taken effect for this run."""
    if fpl_id != DEPARTED["fpl_id"]:
        return False
    run_ids = [r for r, _ in RUNS]
    return run_ids.index(run_id) > run_ids.index(DEPARTED["last_run_id"])


def main() -> None:
    history_only = "--history-only" in sys.argv
    if history_only:
        build_history_season()
        return

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    if DEPARTED["last_run_id"] not in [r for r, _ in RUNS]:
        sys.exit(
            f"DEPARTED last_run_id {DEPARTED['last_run_id']} is not in RUNS — "
            "the departure would never take effect and the union fix would "
            "be tested vacuously"
        )
    if DEPARTED["last_run_id"] == RUNS[-1][0]:
        sys.exit(
            "DEPARTED last_run_id is the final run, so the player is never "
            "actually removed — the fixture would prove nothing"
        )

    for run_id, date in EVENT_STATUS_RUNS:
        print(f"{date} {run_id}  event-status")
        payload = s3_get(f"{RAW_PREFIX}/event-status/{date}/{run_id}/payload.json")
        rounds = sorted({e["event"] for e in payload["status"]})
        payload["_fixture_note"] = (
            "Verbatim event-status capture — no filtering and no edits; the "
            "payload is small enough to keep whole. Covers round(s) "
            f"{rounds}. See EVENT-STATUS CAPTURES in build_fixtures.py for why "
            "these dates were chosen."
        )
        write(
            OUT_ROOT / "event-status" / date / run_id / "payload.json",
            payload,
        )

    for run_id, date in RUNS:
        print(f"{date} {run_id}")

        boot = s3_get(f"{RAW_PREFIX}/bootstrap-static/{date}/{run_id}/payload.json")
        kept = sorted(p for p in PLAYERS if not is_departed(p, run_id))
        finished_note = (
            f" Round {SYNTHETIC_FINISHED['round']}'s `finished` flag is "
            "SYNTHETIC: the round was played and ratified by this capture but "
            "FPL had not yet flipped it. See SYNTHETIC_FINISHED in "
            "build_fixtures.py."
            if run_id == SYNTHETIC_FINISHED["run_id"] else ""
        )
        departure_note = (
            f" Player {DEPARTED['fpl_id']} is deliberately ABSENT: a "
            "synthetic departure, removed from `elements` for every run after "
            f"{DEPARTED['last_run_id']}. See DEPARTED in build_fixtures.py."
            if is_departed(DEPARTED["fpl_id"], run_id) else ""
        )
        write(
            OUT_ROOT / "bootstrap-static" / date / run_id / "payload.json",
            {
                "_fixture_note": (
                    "Trimmed bootstrap-static capture. `elements` is filtered "
                    f"to players {kept}; `events` (all 38 rounds, so the "
                    "spine's calendar is real), `teams` and `element_types` "
                    "are kept whole. Every other top-level key is dropped. The "
                    "element, event, team and position objects themselves are "
                    "verbatim."
                    + departure_note
                    + finished_note
                ),
                "elements": [
                    e for e in boot["elements"]
                    if e["id"] in PLAYERS and not is_departed(e["id"], run_id)
                ],
                "events": mark_synthetic_finished(boot["events"], run_id),
                "teams": boot["teams"],
                "element_types": boot["element_types"],
            },
        )

        fixtures = s3_get(f"{RAW_PREFIX}/fixtures/{date}/{run_id}/payload.json")
        write(
            OUT_ROOT / "fixtures" / date / run_id / "payload.json",
            add_synthetic_dgw_fixture(trim_fixtures(fixtures)),
        )

        for fpl_id, note in PLAYERS.items():
            if is_departed(fpl_id, run_id):
                print(f"  element-summary/{fpl_id}  skipped (departed)")
                continue
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

    # The second season, written last so a full regeneration produces both
    # trees. `--history-only` rewrites just this one, leaving the live tree
    # untouched.
    build_history_season()


if __name__ == "__main__":
    main()
