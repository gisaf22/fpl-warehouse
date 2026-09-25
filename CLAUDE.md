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
  `(season, fpl_id, round)`. Each row reads its season from its own raw key via the
  `season_from_filename` macro: a season-shaped segment before `/fpl/` means a ported
  history season and states its own season, anything else is the live tree and takes the
  `season` var (currently `2026-27`). The live key layout still has no season segment, so
  for live rows the var remains the only available source of the value — **extending it is
  an open item for fpl-ingest, not fpl-warehouse.**
- **`season` partitions; it never relates.** Every dedup, retraction check, ratification
  rollup and spine cross is keyed by season, because `fpl_id`, `fixture_id` and `round` are
  all reassigned each season and unscoped logic would silently merge two different people
  or two different rounds. Season appears in joins only as same-season equality. **No model
  anywhere joins, matches or combines one season's rows with another's.**
- **`player_code` is carried, never used.** FPL's cross-season player identifier
  (`elements[].code`) sits on `stg_player` as a plain column so a consumer can follow a
  person across seasons. Nothing in this project joins, deduplicates or filters on it;
  `fpl_id` remains the key within a season.
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

## Round ratification — `is_ratified` is sourced, not inferred

`is_ratified` on both served models comes from FPL's `event-status` endpoint, via
`stg_event_status` -> `int_round_ratification`. **Do not re-derive it from the scoreline.**

Until 2026-09-14 it was inferred in `fct_player_fixture` as `team_h_score is not null and
team_a_score is not null`, i.e. scoreline publication used as a proxy for points
ratification. Those are different events. Scores appear at full time; bonus points are
applied hours later, typically the next morning. In that window the inference reported
`is_ratified = true` while `bonus` was still 0 — the served flag said "safe to use" about
rows whose points were not final. It was also blind to the rest of the round: a player
whose Saturday fixture had finished read ratified while the round's Monday match was
still unplayed.

Confirmed against live S3 on 2026-09-14, over every `event-status` capture in the bucket:

- The payload is `{"status": [...], "leagues": "..."}`. **`status` is one row per
  `(event, match-date)`, not one per round** — a round spanning three match days
  contributes three entries, and a round mid-transition carries a mix of values across
  them within a single payload. Round-level finality is therefore an aggregate.
- `status[].points` is a string with three observed values: `"r"`, `"p"` and `""`. The
  empty string is an in-progress state seen alongside `"p"`, not a missing one; both are
  treated as not-ratified. `status[].bonus_added` is the boolean companion and moves with
  `points` in every capture observed.
- **Only the current round's dates are served.** A finished round rolls out of the window
  completely — the 2026-09-14 payload mentions round 4 and nothing else.

That last point drives the rollup rule in `int_round_ratification`, which is two-level and
must stay that way:

1. **Within one capture**, a round is ratified only when *every* dated entry for it is
   ratified — `bool_and`, never `bool_or`.
2. **Across captures**, a round is ratified if *any* capture ever said so. Resolving to the
   latest capture the way `fct_player_fixture` resolves competing element-summary captures
   would lose every past round, because the latest capture reports nothing about them.
   Ratification is monotonic, so "ever observed ratified" is sound.

### The 2026-08-29 fallback — bounded, and meant to die

All three raw endpoints' capture history begins **2026-08-29**, after round 1 of 2026-27
had already finished and settled. Round 1 therefore appears in **zero** `event-status`
captures and its finality is unrecoverable from the source. A plain join would flip an
entire round from `true` to `NULL`.

So `fct_player_fixture` accepts a final scoreline as proof of ratification for a round that
is absent from `event-status` entirely *and* whose kickoff predates that date. This is a
dated backfill for one round of one season, not a revival of the general inference — a
round absent from `event-status` with a kickoff on or after the cutoff reads `false`, never
fallback. When raw history for 2026-27 is superseded, **delete the clause rather than
re-dating it.**

### Migration — a breaking change to the served contract (2026-09-15)

The column's name and type are unchanged, so the enforced contract in
`models/marts/schema.yml` does not move. **Its values do.** Measured against live S3 on
2026-09-15, over the latest element-summary capture and all 17 `event-status` captures:

| round | old (inferred) | new (sourced) | rows |
|---|---|---|---|
| 1 | true | true | 610 — via the 2026-08-29 fallback |
| 2 | true | true | 626 |
| 3 | true | true | 654 |
| 4 | **true** | **false** | **658 — changed** |

**658 rows in `fct_player_fixture` flip `true` -> `false`**, plus the corresponding rows in
`fct_player_gameweek`. Every one is a genuine correction, not a join defect: round 4 was
played and scored by the 2026-09-14 capture but `event-status` reported `points: "p"` and
`bonus_added: false` — bonus points had not been applied, so those rows' `bonus` and BPS
were not final while the old flag said they were.

Round 4's divergence is transient — it resolves the moment FPL ratifies the round. The
*class* is not: it recurs every gameweek for the hours between full time and bonus
application, which is exactly the window the fix exists to close.

**No special first-deploy handling is needed.** Both served models are full-refresh tables,
so the next scheduled build republishes `served/` with corrected values and no backfill,
migration or manual step. This is safe today only because no consumer reads these tables in
production yet. It is recorded as breaking regardless: the semantics change even for rows
whose value does not, since `is_ratified` now means "FPL has ratified this round" rather
than "a scoreline exists for this fixture". Any future consumer that started reading
`served/` before this date and cached `is_ratified` would need to re-read.

### What the column means to a consumer

The flag is a property of the *round*, carried on each of its fixture rows. On
`fct_player_gameweek` it stays a `bool_and` over the round's fixtures rather than a direct
join, deliberately: every contributing fixture carries the same value, so the aggregate is
a pass-through that keeps returning `NULL` for a blank round — the contract
`fct_test_player_gameweek_counted_round_has_kickoff` asserts. Joining
`int_round_ratification` there instead would hand a blank round the round's real flag and
break it.

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

### Where the served tables live

Both `fct_` models are published as parquet to fixed keys, overwritten in place after every
successful scheduled build (see "Scheduled build"):

```
s3://fpl-data-safari/served/fct_player_fixture.parquet
s3://fpl-data-safari/served/fct_player_gameweek.parquet
s3://fpl-data-safari/served/_manifest.json
```

Consumers read them with `duckdb.read_parquet()` against those stable keys — they do not
connect to a DuckDB database file, and there is no shared served database.

### Multi-season shape — published

**`served/` carries every season in one combined table, with `season` as a plain column.**
There is no separate history-only serving path, no per-season key, and no season dimension
table. This matches how season is already modelled everywhere upstream: a partition label
on the grain, never a join key.

This is live as of the history port's Step 7: `scheduled_build.yml` sets
`HISTORY_ROOT: s3://fpl-data-safari/history` and passes it to `dbt build` as `--vars`, so
every scheduled build reads and publishes both seasons. It is a constant in the workflow,
not a dispatch input as it is in `ci.yml`'s `live-tests` job — there is no per-run decision
to make, and a build that quietly dropped a season would overwrite good served data with a
single-season table.

**Any query that assumes one season must filter on `season` explicitly.** This is the
consumer consequence and it has teeth: `fpl_id`, `fixture_id` and `round` are all
reassigned every season and therefore repeat across them, so an unfiltered group-by on any
of them silently merges two different people or two different rounds. Row counts went up
roughly 10x at the switchover — measured 2026-09-21, `fct_player_fixture` holds 32,963 rows
of which only 3,216 are 2026-27, and `fct_player_gameweek` holds 34,626 of which 2,668 are
2026-27.

**2025-26 is closed and will never change again.** Every future scheduled build re-reads
the same ported history tree and reproduces the same rows for it; only 2026-27's data
actually grows and updates. Two consequences worth knowing. First, a change in a closed
season's row count between two builds is a defect, not data — there is no legitimate reason
for it to move. Second, most of the published volume is static, so a consumer that caches
per season gets nearly all of the benefit; this is also why the publish guard below is
computed per season rather than on the total, since the live season is small enough to
vanish inside the total's noise.

The season's `is_ratified` is true on every row, set unconditionally by the `closed_seasons`
var rather than derived from event-status, which only ever serves the current round. See
"Round ratification".

`_manifest.json` describes what is currently published, not a history of publishes. It
carries `run_id`, the build timestamp (UTC, seconds precision), the git SHA the build ran
from, `seasons` (a sorted list of what is in the files), `row_counts` (per table) and
`row_counts_by_season` (per table, per season). A consumer that wants a consistency check
can compare those counts against what it actually reads.

`row_counts` deliberately kept its original `{table: total}` shape instead of becoming
nested when the second season arrived, so nothing reading it has to change; the breakdown
was added alongside it. `seasons` is a list rather than a multi-season boolean for the same
reason — a flag would encode today's two-season state as the thing to branch on, and the
count changes again the next time a season is ported.

### The publish floor is computed, not configured

`scripts/publish_served.py` refuses to publish a table that falls meaningfully short of
what the build's own data says it should hold. The expectation is derived per run rather
than hardcoded, so it tracks the data instead of needing an edit whenever the data grows:

- For each season, expected rows = that season's distinct player count x its round count,
  both read from that season's own captures in `stg_player` and `stg_gameweek`.
- Round count means **every** round for a closed season, and only the rounds the latest
  capture reports `finished` for the live season. That distinction is the whole point: the
  live calendar publishes all 38 rounds from day one, so counting them all would have
  expected 667 x 38 = 25,346 rows for 2026-27 on 2026-09-21 against a real 3,216.
- Computed from staging, not from `int_player_gameweek_spine` — which is already exactly
  this product. The spine is `fct_player_gameweek`'s direct parent, so checking that table
  against it would compare a number against itself and pass unconditionally.

Measured on run 35632785680 (2026-09-21): expected 31,958 for 2025-26 (841 x 38) and 2,668
for 2026-27 (667 x 4), total 34,626. `fct_player_gameweek` matched it exactly.
`fct_player_fixture` returned 32,963, 4.8% below — legitimately, because it is a different
grain: one row per fixture a player actually has history for, so a blank gameweek removes
rows the expectation counted. 2025-26 alone was 6.9% low, 2,211 player-rounds in which that
player's club did not play.

Hence a tolerance per table rather than exact equality: 2% for `fct_player_gameweek`, which
is the expectation's own grain, and 15% for `fct_player_fixture`, roughly 2x its observed
worst case. Double gameweeks push the other way and nothing caps the upside — a table
larger than expected is not the failure this guards against.

The check is applied **per season**, and a season present in staging but absent from a
served table scores zero and fails outright. The summed total is reported but is not what
is enforced, because it is not sensitive enough: on 2026-09-21 losing all of 2026-27 would
have shown as a 9.3% shortfall on `fct_player_fixture`'s total, comfortably inside the 15%
that table needs for blank gameweeks. Against that season's own expectation the same loss
is unmissable. An empty `expected` — no seasons in staging at all — is itself a failure,
which the old static floor caught only by accident.

This replaced a static `ROW_FLOOR = 500`, sized in 2026-09 when one part-played season held
~3,200 rows. Against a two-season build it sits three orders of magnitude below anything
real: a build that dropped all of 2025-26 would have cleared it comfortably.

**No dated or versioned keys, and no staging/promote step.** The keys are stable so
consumers need no discovery logic, and the objects are overwritten because there is no
requirement to pin a historical build. The full "only publish on success" guarantee is two
things and nothing more:

1. `dbt build` interleaves each model with its own tests in DAG order and exits non-zero on
   any model error or test failure, so the publish step never runs on a build whose
   assertions did not hold.
2. `scripts/publish_served.py` re-reads each exported parquet file and exits non-zero if
   any season's slice of either table is below its computed floor (above), which catches a
   build that exited 0 having produced an empty or truncated table, or having lost a whole
   season, for an upstream reason.

Neither is atomic across the two objects: they are uploaded by two separate `put_object`
calls, so a reader can in principle catch one updated and the other not. Accepted for now
— revisit if a consumer turns out to need a cross-table point-in-time read.

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

- **The access modifier is not a database grant.** It governs dbt `ref()` resolution at
  parse time. `stg_player_fixture` is a real table in the same DuckDB schema, so anything
  holding the built `.duckdb` file can run `select * from main.stg_player_fixture` — the
  boundary is enforced against dbt models and is a convention for everything else.
  Publishing narrows this in practice rather than by enforcement: only the two `fct_`
  parquet files are uploaded, so a consumer reading `served/` has no path to staging at
  all. That is a property of what the publish step happens to write, not a grant, and it
  holds only as long as nothing else is added under that prefix.
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
# Fast tiers — no AWS session, no S3. Build once, then run either tier.
dbt run  --target fixtures                            # build from tests/fixtures/raw
dbt test --target fixtures --select tag:unit
dbt test --target fixtures --select tag:integration
dbt build --target fixtures --exclude tag:e2e         # both tiers, in DAG order

# e2e — the only tier that reads live S3. Needs credentials; see below.
eval "$(aws configure export-credentials --format env)"
dbt build                                             # models plus every tier
dbt test --select tag:e2e
```

**`unit` and `integration` build against a checked-in fixture, not against S3.**
`--target fixtures` points the raw source at `tests/fixtures/raw` — three real captures
over five players, ~430 KB — instead of the live bucket's ~74k objects. The tree is real
captured data, trimmed; `tests/fixtures/build_fixtures.py` documents every edge case it
covers and regenerates it from S3 when one needs adding.

What makes that hermetic is the path, not the connection: under `--target fixtures` the
source resolves to a local relative path, so no `s3://` URL is ever issued. Do not read
the target's missing `httpfs`/`aws` extensions as the barrier — DuckDB autoloads `httpfs`
on demand and will use ambient `AWS_*` environment credentials with no declared secret
(verified 2026-09-07: a bare connection read the bucket with credentials exported, and
failed 403 without them). The target contributing no credential of its own is a second
layer, and CI asserting no `AWS_*` variable is set is the third.

The whole pair builds and runs in a few seconds with no AWS session at all, which is what
makes them a viable PR check — see "CI" below.

The switch is on the target name, not on the `raw_root` var, so `--target fixtures` is a
complete invocation and the target cannot be paired with the wrong root. `--vars
'{raw_root: ...}'` therefore applies to `dev` only.

**The `dev` target still needs an AWS session for every command, including `dbt test`.**
`profiles.yml` creates the S3 secret when the connection opens, and `chain: "env"` fails
outright with `Secret Validation Failure` if no credentials are in the environment — so
the `eval "$(aws configure export-credentials --format env)"` step below is required
before *any* `dev` command, not just a build. That constraint is exactly why the fast
tiers moved off `dev`: it put a full production read on the PR-blocking path to run tests
that should be hermetic.

Each target has its own database file under `.local/`, so a fixture build and a live build
coexist and one build serves all the tier commands run against it. The files are not
`:memory:` for that reason — with an in-memory database each `dbt test` invocation starts
empty and forces a full rebuild.

**Tiers are dbt tags, and the vocabulary matches fpl-ingest's** so the two repos' CI
tiers mean the same thing:

| Tier | What it covers | Builds against | Cost |
|---|---|---|---|
| `unit` | Single-model grain and structure — PK uniqueness, `not_null`, range and cross-column bounds within one row. No cross-model logic. | Fixture | Seconds, no credentials |
| `integration` | Cross-model and business logic — dedup correctness, ratified-preference, retracted rows, spine completeness, `fixture_count` against the real fixtures. Runs against whatever is already built. | Fixture | Seconds, no credentials |
| `e2e` | The full build against live S3 from scratch. Hits real infrastructure, excluded from the default run. | Live S3 | 7-16 min, needs a session |

**That split is the standard one, and it was not before.** `unit` and `integration` are
supposed to be fast and hermetic; until the fixture tree landed both required a full
production read of ~74k objects before a single assertion could run, which made every PR
check a read of live data and made the tiers unusable in CI at all. Only `e2e` is meant to
touch real infrastructure, and now only `e2e` does.

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
asserts staging holds more than one capture of the same key — the precondition that makes
every dedup assertion mean something, rather than an invariant. On a single-capture build,
such as the documented `--vars '{raw_root: .local/raw}'` fallback, the whole integration
tier passes vacuously because there is nothing to collapse, and this test exists to fail
there rather than let a green suite claim something it never checked.

The fixture tree is deliberately multi-capture for the same reason — three runs of the
same keys, so ratified-preference and retracted-row dedup are genuinely exercised on a PR.
One consequence is worth knowing: this test now also passes against the fixture build, so
it no longer distinguishes a fixture build from a live one on its own. It is only ever run
against `dev`, where that distinction is not needed. If a stronger live-only assertion is
ever wanted, the scale of the accumulated tree — thousands of keys, dozens of runs — is
the thing to assert.

---

## S3 credentials for local dbt runs

**Only the `dev` target needs any of this.** The `unit` and `integration` tiers run under
`--target fixtures` against the checked-in capture and never open an S3 connection — see
"Tests" above. What follows applies to a live build and to the `e2e` tier.

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

**In GitHub Actions none of this is needed — disproven 2026-09-10.** This section
previously said a live build "will not work as-is" in CI and called it an unsolved Phase 5
item. That was wrong. `aws-actions/configure-aws-credentials` writes `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` straight into the job environment, which is
exactly what `chain: "env"` reads — so CI needs no export step at all. The `eval` above is
a local-only workaround for an SSO session that lives in `~/.aws` rather than in the
environment.

Verified on two green runs from `main`: ci.yml's `live-tests` (run `34498685397`) and the
first `scheduled_build.yml` dispatch (run `34501607108`), both building all models and
running all three tiers against live S3.

To build without any AWS session at all, use `--target fixtures` (the checked-in capture,
which is what the fast tiers do). For an ad-hoc build against some other local tree,
`dev` still takes `dbt run --select stg_player_fixture --vars '{raw_root: .local/raw}'` —
but note that a single-capture tree passes every dedup assertion vacuously, which is what
the fixture tree exists to avoid.

**Build cost — staging reads ~74k S3 objects.** Because `stg_player_fixture` was once
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

At low thread counts the read is bound by HTTP round-trip latency rather than CPU, so the
number of concurrent requests is what matters. Measured over an 8,436-object subset:
**474s at 4 threads, 49s at 32** — near-linear. **Resolved: `profiles.yml` sets
`threads: 32` in its `settings:` block** — DuckDB's own thread count, distinct from the
`threads: 4` above it that sets dbt's model concurrency. A full `dbt build` then completed
in **7m53s**, comfortably inside the token window. Locally that setting is a correctness
requirement rather than a speed preference: lowering it puts the build back in a race with
the 15-minute credential lifetime. In CI, where the OIDC session is an hour, it is a
performance setting.

### The latency-bound model does not extrapolate — measured 2026-09-16

The paragraph above was written as a general rule and used to justify oversubscribing the
cores without an upper bound. **It holds only in the range it was measured (4 → 32, on a
subset, locally).** Measured on a CI runner over the full ~74k tree, via the
`duckdb_threads` dispatch input on `live-tests`:

| threads | `stg_player_fixture` | glob (LIST only) | peak RSS |
|---|---|---|---|
| 64 | 332s | 16.6s | 14.6 GiB |
| 128 | **397s — slower** | **86.5s — 5.2x worse** | 14.4 GiB |

Peak RSS is pinned at ~14.5 GiB of the runner's 15.6 GiB at *both thread counts*, so
somewhere below 128 the read stops being bound by round trips and becomes bound by memory.
Past that point more threads buy queueing, not concurrency. That peak RSS was measured with
`preserve_insertion_order: false` already set, which suggests the workload's memory
appetite sits near the runner's ceiling independent of that setting — **not confirmed
against the setting reversed**, since the two have never been compared at the same thread
count.

**A second term the old model ignored now dominates: run-to-run variance.** The same build
at 32 threads took **409s, 441s and 925s** across three runs within 18 hours
(2026-09-15 07:49, 2026-09-15 19:48, 2026-09-16 01:40), against job totals of 7m11s, 7m43s
and 15m50s. That **2.3x spread at identical configuration is larger than any difference
measurable between 32 and 64 threads**, which is why no thread-count change is recommended
on the strength of a single pair of timings. Treat any one timing as a sample, never as
the figure, and size timeouts against the worst observed run rather than the median — that
is what `scheduled_build.yml`'s `timeout-minutes: 45` is sized on.

**LIST is not the cost.** Glob expansion is **16.6s**, ~4-5% of the build. The listing
returns **148,120 keys for 74,060 payloads — exactly 2.0x**, because every payload has a
`metadata.json` sidecar the models never read. All three glob patterns tested cost the
same, including one matching zero keys: DuckDB lists the whole wildcard-free prefix and
matches client-side, so **narrowing the glob by date would not reduce LIST at all.**

Also note the read is memory-hungry: loading all element-summary payloads in one
`read_json` OOM'd at 12.7 GiB on default settings. **Resolved: `preserve_insertion_order:
false` in `profiles.yml`'s `settings:` block** — confirmed root cause. Nothing in this
project depends on raw row order; every model orders explicitly.

---

## CI

`.github/workflows/ci.yml` has three jobs. **The PR-blocking path is `validate` plus
`fixture-tests`, and neither touches AWS** — no OIDC role, no repository variables, no
`id-token` permission.

**`validate`** runs without credentials because it executes no model: `dbt parse` plus the
tier-tag check. The access boundary is genuinely enforced here — group membership and
`access: private` are resolved at parse time, so a model or test that reads staging
without declaring its group fails this job. The column contracts are *not*: dbt compares a
served model's real columns against its declared ones when the model is built, so a
contract violation surfaces in `fixture-tests` instead.

**`fixture-tests`** is the required check that actually builds and asserts. It runs
`dbt run --target fixtures` and then the `unit` and `integration` tiers against the
checked-in capture, in seconds. A step asserts no `AWS_*` variable is in the environment,
so "this job needs no credentials" is verified on every run rather than assumed — if a
change ever puts a production read back on the PR path, the job fails loudly.

**`live-tests`** runs all three tiers against live S3 and is `workflow_dispatch` only. It is
not a PR check, and as of 2026-09-10 that is a deliberate choice rather than a limitation: a
job that reads live S3 fails for reasons that have nothing to do with the pull request in
front of it, so it should not gate merges. The same reasoning keeps the scheduled build off
the required list.

**The OIDC role now exists — this closes the Phase 5 credential item.**
`arn:aws:iam::737634035092:role/github-actions-fpl-warehouse` is set as the `AWS_ROLE_ARN`
repository variable (confirmed present 2026-09-10 via `gh variable list`). Its trust policy
was verified by the maintainer the same day: `aud` is `sts.amazonaws.com`, and `sub` admits
both `repo:gisaf22/fpl-warehouse:ref:refs/heads/main` and
`repo:gisaf22/fpl-warehouse:pull_request`. The ref entry is what covers the scheduled build,
whose token carries the ref subject form — see "Scheduled build". This supersedes the
earlier note that the account's only role was `github-actions-fpl-ingest`.

The `AWS_ROLE_ARN` guard step in both jobs stays regardless. It is no longer describing the
normal state, but it still gives a fork or a fresh clone with no variable set an explanatory
failure instead of an opaque credentials error.

### Actions are SHA-pinned, not tag-pinned

Every `uses:` in both workflows names a full 40-character commit SHA with the version tag
kept as a trailing comment, e.g.
`uses: actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09 # v5`. Pinned 2026-09-13:
`actions/checkout` v5 → `fbc6f399…`, `astral-sh/setup-uv` v7 → `37802adc…`,
`aws-actions/configure-aws-credentials` v4 → `7474bc46…`.

The reason is credential access, not tidiness. `live-tests` and the scheduled build assume
an AWS role via OIDC, so a third-party action runs in a job holding real credentials. A
version tag is a mutable pointer: whoever controls the action's repository can move `v5` to
different code at any time, accidentally or through a compromised maintainer account, and
the workflow would silently run it with that credential access and no diff in this repo. A
commit SHA cannot be moved.

**The cost is real and falls on future version bumps.** Upgrading an action is no longer a
one-character edit to the tag — the new SHA has to be looked up live and cross-checked
before it goes in the file:

```
gh api repos/<owner>/<repo>/commits/<tag> --jq .sha       # always the commit SHA
gh api repos/<owner>/<repo>/git/refs/tags/<tag>           # cross-check, see below
gh api repos/<owner>/<repo>/commits/<sha> --jq .sha       # the SHA is a real commit
```

Mind the annotated-tag trap on the cross-check. `setup-uv@v7` and
`configure-aws-credentials@v4` are annotated tags, so `git/refs/tags` returns
`object.type: tag` and a *tag object* SHA — not the commit, and pinning that value would
break the workflow. Dereference it with `gh api repos/<owner>/<repo>/git/tags/<tag-object-sha>`
and confirm it points at the same commit the `/commits/<tag>` call returned.
`actions/checkout@v5` is a lightweight tag and returns `object.type: commit` directly. Never copy a SHA from
memory or from another repository. The trailing `# v5` comment is human documentation only —
editing it changes nothing about which code runs, so a bump that updates the comment and not
the SHA is a silent no-op. Dependabot can maintain SHA pins if the manual lookup becomes a
burden.

Branch protection is repository configuration, not code. The `protect-main` ruleset
(id `22415012`, active) requires exactly `validate` and `fixture-tests` — verified
2026-09-10. Nothing else is required, and the scheduled build deliberately stays off that
list; see "Scheduled build".

---

## Scheduled build

`.github/workflows/scheduled_build.yml` runs `dbt build` — all models, all three tiers,
against live S3 — at **07:45 and 19:45 UTC**, plus `workflow_dispatch` for manual runs.

**It is informational, not blocking.** It is deliberately absent from the `protect-main`
required-checks list, which stays `validate` + `fixture-tests` (both credential-free). This
job depends on live S3 and on fpl-ingest's output, so it fails for reasons unrelated to any
open pull request; making it required would let a bad upstream capture block every
unrelated merge. A failure here pages a human via GitHub's own run-failure notification —
there is no custom alerting, by design.

**The offset is sized against GitHub's scheduler, not against ingest's runtime.** The
scheduler is the larger term by far. Measured over 26 scheduled fpl-ingest daily runs
(2026-08-28 → 2026-09-10):

| | median | p90 | max |
|---|---|---|---|
| ingest job duration | 3.2m | 8.6m | 9.0m |
| delay from cron to actual start | 14.9m | 23.6m | 24.5m |
| **ingest finished at cron+** | **18.6m** | **27.7m** | **32.0m** |

So a 30-minute offset is *not* safe — ingest has been seen still running at cron+32. The
45-minute offset clears the worst observed finish by 13 minutes even assuming this
workflow's own scheduler delay is zero, and in practice it inherits a comparable 10–25
minute delay of its own. `:45` also sits off the top of the hour, where the queueing that
causes those delays is heaviest. **Re-check this if fpl-ingest's runtime grows: the number
to beat is its max "finished at cron+", not its duration.**

This is a cron offset rather than a `repository_dispatch` fired by fpl-ingest on
completion. Trigger-on-completion is the stronger design and remains the upgrade path, but
it needs a dispatch step and a cross-repo token in fpl-ingest, and the measured margin
above leaves it buying nothing yet.

**Failure is loud by construction.** `dbt build` exits 1 when any model errors or any test
fails, Actions' default `bash -e` propagates it, and the run is marked failed. Verified
2026-09-10: a deliberately failing singular test returned exit 1 from `dbt build`. Every
test in the project is `error` severity — there is no `severity: warn` anywhere — so no
real failure can land as a passing warning. `dbt build` is used rather than `dbt run` then
`dbt test` so each model's tests gate its own dependents in DAG order.

**It publishes.** After a successful `dbt build`, the `Publish served tables to S3` step
runs `scripts/publish_served.py`, which exports both `fct_` tables to parquet and uploads
them to `s3://fpl-data-safari/served/` alongside a `_manifest.json`. Layout, format and the
publish-on-success guarantee are specified under "Served contract" — this section covers
only how the workflow invokes it.

This workflow was previously validation-only, and that was a deliberate scope decision
rather than an oversight: publishing was deferred because no consumer read the output, and
inventing a served layout with nothing to validate it against was judged worse than waiting.
**That decision has been resolved — the layout is now specified and the workflow publishes.**
Any comment or prose elsewhere arguing the absent S3 write is intentional is stale; the
`dev` target still writes `.local/warehouse.duckdb` on the runner and that file still dies
with the runner, but it is now the source for the parquet export rather than the end of the
line.

**The publish step is gated on `if: success()`**, which is a step's default — stated
explicitly so that the invariant is visible to anyone adding a `continue-on-error` or an
`always()` step above it. A failed build cannot overwrite good served data.

**Credentials.** Same OIDC pattern as `live-tests`: `vars.AWS_ROLE_ARN` plus
`aws-actions/configure-aws-credentials@v4`, guarded by an explicit check that names the
missing variable. A scheduled run's OIDC subject is the ref form
(`repo:gisaf22/fpl-warehouse:ref:refs/heads/main`) because a schedule always runs on the
default branch — there is no distinct `schedule` subject format, so a role trust policy
that already admits main covers this workflow with no change. Note the session is an
`AssumeRoleWithWebIdentity` session (1 hour by default), not the 15-minute `aws login`
export that forced `threads: 32` locally, so this build is not racing its credentials and
32 is a performance setting here rather than a correctness one.
Keep `threads: 32` regardless — but not because more is better: 64 and 128 were measured
on this runner and 128 is *slower*. See "The latency-bound model does not extrapolate".

**The role reads raw and writes served, under one inline policy.** Publishing needed a
permission change but **not** a trust-policy change — the distinction is
authorization versus authentication. The trust policy governs who may assume the role,
which is unchanged: the same OIDC subject assumes the same role for the same reason. What
changed is what the role is permitted to do once assumed, which lives in its inline
permissions policy. Confirmed live via `aws iam get-role-policy` — inline policy
`fpl-warehouse-s3-read`, three statements:

- `ReadRawCaptures` — read access to `arn:aws:s3:::fpl-data-safari/raw/*`, what the build
  consumes.
- `ListBucketForGlobExpansion` — bucket-level `ListBucket`, which DuckDB's glob expansion
  over the raw tree requires; object-level read alone is not sufficient.
- `WriteServedOutputs` — `s3:PutObject` on `arn:aws:s3:::fpl-data-safari/served/*`, what the
  publish step needs.

Note the policy *name* predates the write grant and is now a misnomer: `-s3-read` describes
what the role originally did, not what it does. The statement names are the accurate
description. Renaming it is cosmetic and would require updating the role, so it has been
left alone deliberately — do not read the name as evidence the write grant is missing.

The write grant is scoped to the `served/` prefix, so a bug in the publish step cannot
overwrite anything under `raw/`. That containment is the reason to keep the two statements
separate rather than widening one to the whole bucket.

**Measured CI runtime, 2026-09-15/16.** Effectively the whole job is one model —
`stg_player_fixture` is the S3 read and every other model is sub-second — so these are the
same number twice:

| run | `stg_player_fixture` | job total |
|---|---|---|
| 2026-09-15 07:49 | 409s | 7m11s |
| 2026-09-15 19:48 | 441s | 7m43s |
| 2026-09-16 01:40 | **925s** | **15m50s** |

Size timeouts against the **worst** row, not the median: the spread is 2.3x at identical
configuration, and it is variance in the S3 read rather than growth in the tree. That is
what `timeout-minutes: 45` is sized on, and why it is not 30.

**The figures this replaces were not merely outdated — they were already wrong when
written.** The previous text paired "~26k objects" with "593s of the 597s" as though both
came from run `34501607108` on 2026-09-10. They came from different dates: 25,611 payloads
was counted on 2026-09-03, while 593s was measured a week later, by which time the tree
held **at least 49,699** objects (directly counted from a staging build of 2026-09-07) —
already roughly double the object count it was attributed to. Per-object cost was therefore
overstated by about 2x, and the resulting "~10 minutes, comfortable against a 30-minute
timeout" conclusion outlived the data behind it. The correction matters beyond the
arithmetic: it is what made the build look like it had years of headroom when a single slow
run had already reached half the timeout.

---

## Working on board items

Items on the [FPL Platform board](https://github.com/users/gisaf22/projects/3) follow
[AGENT_WORKFLOW.md](https://github.com/gisaf22/.github/blob/main/AGENT_WORKFLOW.md) in
`gisaf22/.github`. "Pick up #N" means: run that procedure for #N — pick up → tests →
implement → PR → close. Read it before starting. This section is identical in fpl-ingest,
fpl-warehouse and fpl-intelligence; change all three together.

Must-follow rules:

- **No acceptance criteria table → stop.** Add the `needs-spec` label and ask.
- **Move the item to In Progress** when you pick it up. Bigger than its Size → stop and
  propose a split.
- **Tests come from the acceptance criteria only**, one or more per AC at its test tier,
  each marked `covers("#<issue> AC<n>")`, with plain-English names. Don't invent tests;
  flag any you think are missing. Manual/e2e tiers: record the result on the PR or issue.
- **Commit the tests first (failing), then stop and report for approval** before implementing.
- **Stay inside Out of scope.** Spec wrong or ambiguous → stop and ask; don't improvise.
- **PR body says `Closes #N`; post AC results (pass/fail per AC, with evidence) as a PR
  comment; tick the Definition of Done** (N/A with reason where it doesn't apply).
- **Never merge.** The human merges.
- **After merge:** confirm the item is Done, then move every item it was blocking that has
  no other open blocker from Blocked to Todo.
- **New items:** use the `gisaf22/.github` templates, create with `--body-file`, and set
  Work Item Type, Epic, Size, Status and parent.
- **Public board:** no account IDs, ARNs or secrets in any issue, PR or comment.
