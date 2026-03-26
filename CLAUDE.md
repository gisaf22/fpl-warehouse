# fpl-warehouse — Module Guide

Status: COMPLETE — maintain only
Last updated: 2026-03-23

---

## TL;DR

Warehouse is clean and tested.
Only modify if schema changes needed.
Rebuild: TEAM_ID=X ./scripts/refresh.sh
Takes ~2 minutes end to end.

Tests: python -m pytest projects/fpl-warehouse/ -q
  Unit: test_manager_squad.py
  Integration: test_snapshot_dtypes.py
               test_team_normalization.py

---

## What this builds

fact_decision_snapshot  — captain features
fact_transfer_snapshot  — transfer features
  (39 cols, 12 new beyond base snapshot)
fact_player_gw          — per-player per-GW
fact_match_stats        — match xG, PPDA
fact_manager_squad      — manager 15 players
fact_fixtures           — fixture calendar
fact_shots              — shot data
dim_players             — player registry
  includes: chance_of_playing_next_round,
            news, news_updated
dim_teams               — team registry
views (10)              — analytical views

---

## Key rules

build.py orchestrates everything.
  Call build_all() to rebuild from scratch.

matching.py: FPL ↔ Understat player match.
  5-tier fuzzy matching.
  Do NOT simplify — complexity is necessary.
  Manual overrides in MANUAL_OVERRIDES dict.

views.py: SQL views for downstream queries.
  All downstream modules use these views.

All joins use fpl_id (integer).
Boundary: round <= as_of_gw (inclusive).

---

## Connection pattern

fpl-warehouse reads from two source DBs:
  data/fpl/fpl.db         — FPL source
  data/understat/understat.db — Understat

Writes to:
  data/warehouse/master.db — output

This is the ONLY package that opens
multiple DB connections. All downstream
packages use only master.db via
get_connection().

---

## Spec file

problems/shared/docs/pipeline_spec.md
