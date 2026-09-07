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
- Derive `fct_player_gameweek` from it, spine-joined, with an explicit `fixture_count`
  column: `0` = blank gameweek, `1` = normal, `2+` = double.
- **Never model at gameweek grain directly from raw data.**
- **`season` is part of the grain project-wide** — `fct_player_fixture` is
  `(season, fpl_id, fixture_id)`, `int_player_gameweek_spine` and `fct_player_gameweek` are
  `(season, fpl_id, round)`. It is stamped from the `season` var in `dbt_project.yml`
  (currently `2026-27`) because fpl-ingest's raw key layout has no season segment, so every
  raw object read belongs to one season. Multi-season joining is therefore not yet
  exercised; the column exists now so adding a second season is a data change rather than a
  breaking rebuild of every downstream consumer. **Extending the raw key layout with a
  season segment is an open item for fpl-ingest, not fpl-warehouse** — until it lands, the
  constant is the only available source of the value.
- **ASSUMED, not verified: the double-gameweek rule for the event-level fields.**
  `fct_player_gameweek` takes `value`, `selected` and the `transfers_*` family from the
  round's last fixture (`max_by(..., kickoff_time)` — last write wins) on the basis that FPL
  states them per event, so both rows of a double would repeat the same number and summing
  would double-count. **No double gameweek has occurred in the captured data, so this has
  never been observed.** Re-verify at the first real double before trusting these columns
  across one.

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
- Only the served `fct_` models are for external consumption. There is no `agg_` layer:
  `fct_player_gameweek` is a fact table at gameweek grain, not a separate category.

## Served contract

fpl-intelligence must never query staging directly — only `fct_player_fixture` and
`fct_player_gameweek`.

**Enforced (dbt refuses to parse or build on violation):**

- Every model belongs to the `warehouse_internal` group (`models/groups.yml`).
- `stg_player_fixture`, `stg_player`, `stg_gameweek` and `int_player_gameweek_spine` are
  `access: private`. Any model outside the group that `ref()`s one fails **at parse time**.
  Verified 2026-09-03 with a throwaway model in `models/marts/`:
  `attempted to reference node model.fpl_warehouse.int_player_gameweek_spine, which is not
  allowed because the referenced node is private to the 'warehouse_internal' group`.
- The two `fct_` models are `access: public` with `contract: enforced: true` and a full
  explicit column list in `models/marts/schema.yml`. Adding, dropping, renaming or
  retyping a served column now fails the build until the contract is updated, which makes
  every breaking change to the served shape a deliberate, reviewed edit.
- Singular tests are subject to the same rule. The tests in `tests/` that `ref()`
  a staging or intermediate model carry `{{ config(group='warehouse_internal') }}`; without
  it dbt refuses to parse them. Any new test that reads staging needs the same line.
- The `fct_` models are group members themselves — dbt allows a `ref()` of a private model
  only from inside the same group, and they must read staging to be built at all. Their
  `access: public` is what keeps them referenceable from outside.

**Documented only, NOT enforced:**

- **Raw SQL access to staging is not blocked.** The access modifier governs dbt `ref()`
  resolution at parse time; it is not a database grant. `stg_player_fixture` is a real
  table in the same DuckDB schema, and fpl-intelligence connects with raw SQL rather than
  as a dbt project, so nothing here stops it from running
  `select * from main.stg_player_fixture`. The boundary is enforced against dbt models and
  is a convention for everything else. Making it real would need database-level grants (or
  a separate served schema/database that consumers get access to), which this project does
  not do today.
- The `fpl_intelligence` exposure in `models/exposures.yml` declares the two `fct_` models
  as its dependencies. That documents the contract and puts it in the DAG; it enforces
  nothing.

---

## Known bugs from the prior Python implementation — do not reintroduce

1. `team_fpl_id` resolved at build time rather than as-of. This breaks the as-of-inclusive
   snapshot guarantee for players transferred mid-season.
2. Direct mutating `UPDATE` statements against fact tables — untraceable and
   non-idempotent. All transformation logic belongs in SQL models, never in Python
   post-processing.

---

## Tests

```bash
dbt test --select tag:unit          # fast default, with integration
dbt test --select tag:integration   # fast default, with unit
dbt test --select tag:e2e           # opt-in only — needs a build from the live raw tree
dbt build                           # models plus every tier, in DAG order
```

Every test needs the models built first, and the build reads S3 — see "S3 credentials for
local dbt runs" below. The DuckDB database is a file under `.local/`, not `:memory:`, so
one build serves all three tier commands; with an in-memory database each `dbt test`
invocation starts empty and forces a full rebuild. Against a warm database the unit and
integration tiers each finish in about two seconds.

**`dbt test` needs the AWS session too, even though it reads only local tables.**
`profiles.yml` creates the S3 secret when the connection opens, and `chain: "env"` fails
outright with `Secret Validation Failure` if no credentials are in the environment. So the
`eval "$(aws configure export-credentials --format env)"` step below is required before
*any* dbt command here, not just a build.

**Tiers are dbt tags, and the vocabulary matches fpl-ingest's** so the two repos' CI
tiers mean the same thing:

| Tier | What it covers | Cost |
|---|---|---|
| `unit` | Single-model grain and structure — PK uniqueness, `not_null`, range and cross-column bounds within one row. No cross-model logic. | Fast |
| `integration` | Cross-model and business logic — dedup correctness, ratified-preference, retracted rows, spine completeness, `fixture_count` against the real fixtures. Runs against whatever is already built. | Fast |
| `e2e` | The full build against live S3 from scratch. Slow, hits real infrastructure, excluded from the default run. | ~8 min |

**Every test carries exactly one tier tag**, and CI fails if one carries none or two — a
tag-less test runs in no tier and is silently never enforced. Prefer a generic test in
`schema.yml` (`unique` / `not_null` / `relationships` / `accepted_values`) over a singular
`.sql` wherever the assertion is expressible that way.

Tag generic tests explicitly rather than through a project-level default: dbt **merges**
tag configs rather than overriding them, so a `data_tests: +tags: [unit]` default in
`dbt_project.yml` would also stamp `unit` onto the integration and e2e tests.

Singular tests live flat in `tests/` (dbt's default `test-paths`) and are named
`<layer>_test_<subject>_<assertion>.sql` — layer `stg` or `fct`, subject the model,
assertion the claim. Each opens with a header stating its layer, model, the claim in one
sentence, its origin, and its tier:

```sql
-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: fixture_count equals the real number of fct_player_fixture rows for
--          that (season, fpl_id, round).
-- Origin: new in Phase 2, modelled on
--         tests/team_fixture/sql/fct_test_fixture_count_nonneg.sql
-- Tier: integration
```

There is no separate test-tracking document — the header is it. The 31 pre-dbt SQL
assertion files that used to sit under `tests/*/sql/` were triaged and either ported,
found duplicate, or retired in commit `c1f820a`, whose message carries the full
disposition of each one.

**The e2e tier is not just the slow tier.** `stg_test_player_fixture_multiple_captures_present`
asserts staging holds more than one capture of the same key, which is true only of a build
against the real accumulated raw tree. Every dedup assertion in the integration tier passes
vacuously on a single-capture build — such as the documented
`--vars '{raw_root: .local/raw}'` fallback — so this test exists to fail there rather than
let a green suite claim something it never checked.

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

**Build cost — staging reads ~26k S3 objects.** Because `stg_player_fixture` was once
materialized as a view, *every* consumer re-read it: the fact model, then each test that
references staging. A full `dbt build` on 2026-09-03 exceeded the exported credential's
lifetime partway through and failed with `ExpiredToken`. Materializing staging as a table
makes the same build read S3 once. **Resolved: `dbt_project.yml` sets
`staging: +materialized: table`.** Do not revert it to a view — the `ExpiredToken` failure
returns immediately, and CI cannot re-export credentials mid-run either.

**`ExpiredToken` returned on 2026-09-07, and the table fix alone no longer covers it.**
The credential source is the constraint: `aws configure export-credentials`, backed by
`aws login`, issues **15-minute** tokens, and there is no static key in `~/.aws` to fall
back on. At DuckDB's default of one thread per core the element-summary read had grown to
901s — 15.0 minutes — so it raced the token and lost mid-read.

The read is bound by HTTP round-trip latency, not CPU, so the number of concurrent
requests is what matters. Measured over an 8,436-object subset: **474s at 4 threads, 49s
at 32.** **Resolved: `profiles.yml` sets `threads: 32` in its `settings:` block** — DuckDB's
own thread count, distinct from the `threads: 4` above it that sets dbt's model
concurrency. A full `dbt build` then completes in **7m53s**, comfortably inside the token
window. Treat that setting as a correctness requirement rather than a speed preference:
lowering it puts the build back in a race with the credential lifetime.

Also note the read is memory-hungry: loading all element-summary payloads in one
`read_json` OOM'd at 12.7 GiB on default settings. **Resolved: `preserve_insertion_order:
false` in `profiles.yml`'s `settings:` block** — confirmed root cause. Nothing in this
project depends on raw row order; every model orders explicitly.

---

## CI

`.github/workflows/ci.yml` has two jobs.

**`validate`** is the required check on every PR and runs without credentials, because it
executes no model: `dbt parse` plus the tier-tag check. The access boundary is genuinely
enforced here — group membership and `access: private` are resolved at parse time, so a
model or test that reads staging without declaring its group fails this job. The column
contracts are *not*: dbt compares a served model's real columns against its declared ones
when the model is built, so a contract violation surfaces in `data-tests` instead.

**`data-tests`** runs the three tiers and is `workflow_dispatch` only. It cannot be a PR
check yet: every data test needs the models built, building them means reading the raw tree
from S3, and this repo has no route to that bucket from Actions. The only OIDC role in the
account (`github-actions-fpl-ingest`) trusts `repo:gisaf22/fpl-ingest:ref:refs/heads/main`
and nothing else, and fpl-warehouse has no repository variables or secrets set. The job
fails immediately with an explanatory message when `vars.AWS_ROLE_ARN` is unset.

**Making the fast tiers a real PR check is the open item.** Two routes: stand up an IAM
role trusting this repo (the Phase 5 automation item), or commit a raw fixture capture and
build against it with `--vars`. The fixture route needs a *multi-capture* fixture to be
worth anything — a single-capture one passes every dedup assertion vacuously, which is the
failure mode the e2e tier exists to catch.
