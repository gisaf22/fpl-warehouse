# fpl-warehouse — agent rules

**This file describes the target architecture the repo is being migrated *to*, not its
current state.** For current state, read `docs/architecture/current-state.md` if it still
exists; `docs/architecture/target-state.md` is the governing target document.

These rules sit on top of the global engineering policy in `~/.claude/CLAUDE.md`.

---

## What this repo is

A dbt-duckdb project that transforms fpl-ingest's raw S3 JSON into served fact and
aggregate tables for fpl-intelligence to consume.

It is being rebuilt. The existing Python builders under `src/fpl_warehouse/` and the
SQLite-dialect SQL under `src/models/` are being **replaced, not extended** — do not add
to them. `sql_runner.py` describes itself as the manual equivalent of dbt's model executor
and states it can be deleted on migration.

---

## Grain — locked

- `player_histories` (per-fixture) is the canonical player-gameweek source. The old
  `gameweeks` table is gone (deleted upstream in fpl-ingest).
- Build `fct_player_fixture` at **per-fixture grain** first.
- Derive `agg_player_gameweek` from it, spine-joined, with an explicit `fixture_count`
  column: `0` = blank gameweek, `1` = normal, `2+` = double.
- **Never model at gameweek grain directly from raw data.**

---

## Layering

- `stg_` staging is 1:1 with its raw source — typing and renaming only. No business logic,
  no joins.
- Intermediate models only when a join or reshape is genuinely complex or reused. Skip the
  layer otherwise.
- Only the served `fct_` / `agg_` models are for external consumption.

## Served contract

fpl-intelligence must never query staging directly — only the two served models. Once
implemented: `access: private` plus a `group` on staging and intermediate models;
`contract: enforced` on the served models.

---

## Known bugs from the prior Python implementation — do not reintroduce

1. `team_fpl_id` resolved at build time rather than as-of. This breaks the as-of-inclusive
   snapshot guarantee for players transferred mid-season.
2. Direct mutating `UPDATE` statements against fact tables — untraceable and
   non-idempotent. All transformation logic belongs in SQL models, never in Python
   post-processing.

---

## Tests

The 31 SQL assertion files under `tests/*/sql/` already follow dbt's singular-test
convention (zero rows on pass). **Port them as dbt tests rather than rewriting them.**

Grain-uniqueness and `fixture_count` assertions are an established pattern in this repo,
not a concept to invent: `fact_test_grain_uniqueness.sql` / `fct_test_grain_uniqueness.sql`
exist under `tests/availability/`, `tests/market/`, `tests/performance/` and
`tests/team_fixture/`, and `tests/team_fixture/sql/fct_test_fixture_count_nonneg.sql`
covers `fixture_count`.

The concrete action is **extending that same pattern to the new served models**, which have
no such coverage yet:
- row-uniqueness on the grain of `fct_player_fixture` and `agg_player_gameweek`;
- a check on `agg_player_gameweek` that `fixture_count` matches the real number of fixtures
  (stronger than the existing non-negativity assertion it is modelled on).

## CI

CI currently runs only `uv run pytest -m unit` (`.github/workflows/ci.yml`), so the SQL
suite is never enforced. Once dbt is set up, CI must run `dbt build` — which runs tests in
DAG order — and block publishing on failure.
