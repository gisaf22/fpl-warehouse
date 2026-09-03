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

## Capture dedup — provisional vs ratified

Confirmed against live S3 on 2026-09-03, building `stg_player_fixture` over all 25,611
`element-summary` payloads (50,568 rows, 1,238 distinct `(fpl_id, fixture_id)` keys):

- An `element-summary` payload captured **before a round's scores are ratified** carries
  `NULL` `team_h_score` / `team_a_score`. Round 2 was 36.8% null (9,411 of 25,558 rows);
  settled round 1 was 0%.
- **558 `(fpl_id, fixture_id)` keys have both** a null-score and a populated-score capture,
  because staging is 1:1 with the raw source and a player is captured once per run.

**Hard requirement for `fct_player_fixture`:** dedup per `(fpl_id, fixture_id)` MUST prefer
the latest/ratified capture — never an arbitrary one. Picking wrong reintroduces the same
zeroed-stat corruption class that fpl-ingest's settlement-transition fix was built to
prevent (`influence`/`creativity`/`threat`/`ict_index` all `"0.0"` pre-ratification), one
layer downstream. The `NULL` scores are the visible marker of a provisional capture; the
zeroed ICT fields ride along with it silently.

Staging itself is correct as-is — a 1:1 model must carry provisional captures through.
This is a served-layer obligation, not a staging bug.

The ordering field is the raw object key, not the payload: the body carries no extraction
timestamp, so `sources.yml` reads with `filename = true` and staging parses
`extraction_date`, `run_id` and `extracted_at` out of
`.../element-summary/{fpl_id}/{extraction_date}/{run_id}/payload.json`. `run_id` is
`{YYYYMMDDTHHMMSSZ}-{hash}`, so its prefix is the run's start instant and the hash breaks
ties. There is no `metadata.json` alongside element-summary payloads to read instead.

---

## Retracted history rows

**FPL sometimes deletes a history row it published earlier.** Confirmed on 2026-09-03: two
mid-season transfers (`fpl_id` 28 and 166) each briefly carried a round-2 row for their
*other* club's fixture, which later captures dropped — 28 lost fixture 20, 166 lost
fixture 16. Both ghosts had 0 minutes, 0 points and a zeroed ICT family.

Because staging accumulates every capture ever taken, a retracted key survives there
forever. Carried into `fct_player_fixture` it becomes a fixture the player never played,
and the gameweek reports `fixture_count = 2` — a fabricated double gameweek, which is the
same class of grain corruption this rebuild exists to remove.

**The ratified-preference rule does not catch this** — `fpl_id` 166's ghost row is itself
ratified. `fct_player_fixture` therefore carries a key only while it is still present in
that player's most recent capture; each payload holds the player's complete history array,
so absence from the newest one is a deletion by the source, not a partial read. Staging
keeps the retracted rows as the audit trail.

---

## ICT aggregation — `ict_index` is additive

Do not recompute `ict_index` as `(influence + creativity + threat) / 10` when aggregating
to gameweek grain. That formula holds for most rows but **not all**: 31 of 1,236 fixture
rows publish an index that does not reconcile with their own components (`fpl_id` 415
round 1 states influence 0.0, creativity 1.2, threat 16.0 and an index of 0.7, where the
formula gives 1.7).

Verified against FPL's own season totals in bootstrap-static on 2026-09-03: **summing the
per-match `ict_index` reproduces the published season figure for 626 of 626 players**,
while recomputing from components matches only 538. `influence` / `creativity` / `threat`
sum exactly (626/626). The published index is the authority; the inconsistency is carried,
not silently corrected.

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

---

## S3 credentials for local dbt runs

DuckDB does **not** inherit the AWS CLI session. `profiles.yml` names a credential chain
only — it holds no secrets and is safe to commit — but the chain alone does not resolve an
`aws login` session. Confirmed failures on 2026-09-03:

- `provider: credential_chain` with no `chain` → `Secret Validation Failure ... 'config'`
- `chain: "sso;sts;env;config"` → `STS is only supported with an ASSUME_ROLE_ARN value`
- `chain: "sso;env;config"` → `Secret Validation Failure`

What works locally is `chain: "env"` with credentials exported into the environment first:

```bash
eval "$(aws configure export-credentials --format env)"
dbt run --select stg_player_fixture
```

Without that `eval` the run fails with `HTTP 403 Forbidden — No credentials are provided`.
A local build is therefore **not self-contained**; the export is a required first step.

**This will not work as-is in GitHub Actions.** CI authenticates via OIDC (see fpl-ingest's
`scheduled_run_*.yml`), which populates the environment differently and has no
`aws configure export-credentials` session to export from. Solving that properly is a
**Phase 5 (automation) item — not solved yet.**

To build without any AWS session at all, override the raw root to a local capture:
`dbt run --select stg_player_fixture --vars '{raw_root: .local/raw}'`.

**Build cost — staging is a view over ~25k S3 objects.** One pass over the
element-summary tree takes ~8 minutes, and because `stg_player_fixture` is materialized as
a view, *every* consumer re-reads it: the fact model, then each test that references
staging. A full `dbt build` on 2026-09-03 exceeded the exported credential's lifetime
partway through and failed with `ExpiredToken`. Materializing staging as a table makes the
same build read S3 once (~8 min total, all downstream nodes then sub-second). Phase 2 was
verified that way; the committed config still says `view`. **Unresolved — decide before
Phase 5 wires up CI**, since CI cannot re-export credentials mid-run either.

Also note the read is memory-hungry: loading all element-summary payloads in one
`read_json` OOM'd at 12.7 GiB on default settings. `preserve_insertion_order: false` (and
a `memory_limit`) in the profile's `settings:` block avoids it.

---

## CI

CI currently runs only `uv run pytest -m unit` (`.github/workflows/ci.yml`), so the SQL
suite is never enforced. Once dbt is set up, CI must run `dbt build` — which runs tests in
DAG order — and block publishing on failure.
