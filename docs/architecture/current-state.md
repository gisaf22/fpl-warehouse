# Current-State Architecture Audit

**Deliverable 1 — current state only.** No target architecture, no ownership assignment, no migration steps.

**Date of audit:** 2026-08-24
**Method:** read-only inspection of working trees, `git log`, materialised SQLite databases, test collection, and CI workflow definitions. No code was modified.

## Tag legend

| Tag | Meaning |
|---|---|
| **FACT** | Verified directly against code, a database, a config file, or a command run during this audit. |
| **INFERENCE** | Plausible reading of the evidence, not directly confirmed. |
| **OPEN QUESTION** | Needs a decision or an answer from Fred; cannot be resolved from the repos. |

## Repositories in scope

| Repo | Working tree | HEAD | Last commit |
|---|---|---|---|
| fpl-ingest | `~/Documents/fpl-ingest` | `1134a88` | 2026-05-18 |
| fpl-warehouse | `~/Documents/fpl-warehouse` | `cd90148` | 2026-04-13 |
| fpl-intelligence | `~/Documents/fpl-intelligence` | `ec9c537` | 2026-08-24 |

**FACT** — A fourth repo, `understat-ingest` (`~/Documents/understat-ingest`), is a hard build-time input to fpl-warehouse. It was not named in the audit scope but cannot be omitted from the current-state picture: without `understat.db` the warehouse build exits with status 1.

**FACT** — Two further repos consume warehouse output and are therefore part of the current state: `fpl-advisor-api` and `fpl-decision-engine-src`. Both are covered in the consumer sections below.

---

# 1. fpl-warehouse

This section was established from scratch, per the brief.

## 1.0 Correction to the known context

**FACT** — The premise "NO CURRENT DOCUMENTATION EXISTS" is **incorrect**. fpl-warehouse contains 15 documentation files under `docs/`, plus a substantive `README.md` and four `.github/agents/*.agent.md` role definitions:

```
docs/README.md
docs/contracts/snapshot_contract.md
docs/design/{player_availability,player_market,player_performance,team_fixture}_context_design_historical.md
docs/governance/{change_versioning_policy,data_freshness_policy,validation_test_spec,warehouse_governance_spec}.md
docs/history/{README,snapshot_audit,sources_refresh_debt,views_retirement}.md
docs/system/{architecture,build_transformation_spec,data_lineage_map}.md
```

**FACT** — Spot-checked against code, this documentation is largely accurate and current. `docs/history/views_retirement.md` correctly describes the retirement of the ten `v_*` views and names all five replacement snapshot tables; `docs/system/data_lineage_map.md` correctly lists the five `fpl.db` source tables. The SQL models themselves carry extensive header docblocks stating purpose, grain, PIT contract, source refs, and known limitations.

**FACT** — The documentation gaps that do exist are specific rather than total, and are itemised in §1.9.

**OPEN QUESTION** — The brief's premise was materially wrong about this repo. Was the intended gap "no *architecture* documentation in the shared cross-repo sense" rather than "no documentation"? This changes what Deliverable 2 needs to produce.

## 1.1 What it reads from

**FACT** — **Both** fpl-ingest's SQLite *and* Understat, plus one network source. Three inputs:

| Input | Path (resolved) | Read by |
|---|---|---|
| `fpl.db` | `~/Documents/FPL/data/fpl/fpl.db` | `builders/dimensions.py`, `builders/facts.py` |
| `understat.db` | `~/Documents/FPL/data/understat/understat.db` | `builders/dimensions.py`, `builders/facts.py` |
| reep people CSV | `raw.githubusercontent.com/withqwerty/reep/main/data/people.csv` | `integration/matching.py:385` |

**FACT** — Source tables actually read, verified against the SQL in `builders/`:

- From `fpl.db`: `teams`, `players`, `events`, `fixtures`, `gameweeks`
- From `understat.db`: `shots`, `match_info`, `rosters`

**FACT** — All eight are real tables in the respective producers. The five `fpl.db` tables are all declared in fpl-ingest's `PUBLIC_TABLES` contract, so the read is against a governed surface, not incidental internals.

**FACT** — Path resolution is a three-tier fallback in `warehouse/db.py:23-31` and `cli.py:22-25`: CLI flag → environment variable → hardcoded `~/Documents/FPL/...` default. `_load_fpl_env()` (`warehouse/db.py:10`) reads `~/Documents/FPL/.env` and populates the environment without overriding existing values.

**FACT** — That `.env` file lives **outside all three repositories**, at `~/Documents/FPL/.env`. It sets `FPL_DB_PATH`, `UNDERSTAT_DB_PATH`, and `WAREHOUSE_DB_PATH`. It is not version-controlled in any repo in scope and has no committed template or example.

**OPEN QUESTION** — `~/Documents/FPL/.env` is currently load-bearing, untracked, and machine-local. Is this intentional, or is it accumulated local setup that nothing would reproduce on a second machine?

### The reep network dependency

**FACT** — `load_reep_map()` (`integration/matching.py:389`) downloads a CSV from a third-party GitHub repository on first call and caches it at `~/.cache/fpl_warehouse/reep_people.csv`. There is no version pin, no checksum, and no vendored fallback. It maps FPL player code (Opta numeric) → Understat `player_id` and is the primary player-matching mechanism as of `cd90148`.

**FACT** — Once cached the file is never refreshed; the cache is only invalidated by manual deletion.

**INFERENCE** — A build on a clean machine with no network access, or after that upstream repo moves or deletes the file, would fail at `response.raise_for_status()` rather than degrade to fuzzy matching. The fuzzy path exists but only runs as fallback for players *not* resolved by reep, and is unreachable if the map cannot be loaded at all.

**OPEN QUESTION** — Should the reep CSV be vendored and version-pinned into the repo? It is currently an unpinned external dependency on a third party's `main` branch sitting on the critical build path.

### The dead FPL API client

**FACT** — `sources/fpl.py` calls the live FPL API (`https://fantasy.premierleague.com/api/bootstrap-static/`). Both that module and its only caller, `refresh_player_availability()` (`builders/snapshots.py:169`), carry `# WARNING: architectural debt` comments stating the warehouse must not call the API directly.

**FACT** — `refresh_player_availability()` has **no caller anywhere in the repository**. Grep across all `*.py` returns only the definition itself, its docstring, and `sources/__init__.py` re-exporting `get_bootstrap`. It is not wired into `build_all()`.

**FACT** — Its docstring references a `--refresh-availability` CLI flag. That flag **does not exist** in `cli.py`, which defines only `--fpl-db`, `--understat-db`, `--warehouse-db`, `--threshold`, and `--verbose`.

So the documented "warehouse calls the FPL API" debt is **already inert** — the code path is unreachable and the API is not contacted during a build. The debt is dead code that was never deleted, not live behaviour. `dim_players` still carries the three columns it would populate (`chance_of_playing_next_round`, `news`, `news_updated`); these are declared in the DDL and are therefore always NULL in a normal build.

**INFERENCE** — The columns are dead weight in `dim_players` under current behaviour, since nothing writes them.

## 1.2 dbt-based or ad hoc?

**FACT** — **Neither, precisely.** It is hand-rolled Python + SQL, deliberately written to mirror dbt's structure so a later migration is mechanical.

**FACT** — No dbt dependency exists. `pyproject.toml` declares only `rapidfuzz>=3.0` and `requests>=2.28` at runtime; dev adds `pytest`, `ruff`, `vulture`. There is no `dbt_project.yml`, no `profiles.yml`, no `dbt` import anywhere.

**FACT** — The dbt-shaped conventions are explicit and consistently applied:

- `sql_runner.py` describes itself as "the manual equivalent of dbt's model executor and test runner" and states "When migrating to dbt, this file can be deleted."
- Every model file under `src/models/` carries a `Future dbt migration` section in its header naming the exact `{{ ref() }}` substitution and materialisation config.
- Layer prefixes follow dbt convention: `int_` (intermediate, materialised as views), `fct_` (feature views), `fact_` (final materialised tables).
- Table references in SQL are annotated `-- ref: <table>` in the position a `{{ ref() }}` would occupy.
- SQL tests return 0 rows on pass, matching dbt's singular-test contract exactly.

**FACT** — Execution model, from `build.py:27-61`: `create_schema()` applies `base_tables/*.sql` in filename order; builders run in dependency order; `materialize_all_snapshots()` creates the intermediate views then does `DROP TABLE` → `CREATE TABLE` → `CREATE INDEX` → `INSERT INTO … SELECT` per snapshot; `validate_build()` runs contract checks last.

**FACT** — Snapshot materialisation is full-refresh, not incremental. `materialize_snapshot()` (`builders/snapshots.py:129`) unconditionally drops and rebuilds each snapshot table on every run. Base fact tables, by contrast, use `INSERT … ON CONFLICT DO UPDATE` upserts and are cumulative.

**INFERENCE** — This is a coherent, disciplined design choice rather than accumulated ad-hockery. The migration path to dbt is genuinely short for the model layer; the Python builders in `builders/` would need to become sources or seeds regardless.

## 1.3 Tables, models, and grain

**FACT** — Verified against the live database at `~/Documents/fpl-warehouse/data/warehouse/master.db` (11.3 MB, last built 2026-04-13 17:10).

### Persisted tables (12)

| Table | Grain | Rows | Source |
|---|---|---|---|
| `dim_teams` | one row per team | 20 | `fpl.db.teams` + static name map |
| `dim_players` | one row per FPL player | 826 | `fpl.db.players` × `understat.db` via reep/fuzzy |
| `dim_gameweeks` | one row per gameweek | 38 | `fpl.db.events` |
| `fact_player_gw` | `(fpl_id, round)` | 24,737 | `fpl.db.gameweeks` + Understat `rosters` enrichment |
| `fact_fixtures` | `(fixture_id)` | 380 | `fpl.db.fixtures` |
| `fact_shots` | `(shot_id)` | 7,916 | `understat.db.shots` |
| `fact_match_stats` | `(understat_match_id)` | 318 | `understat.db.match_info` + fixture bridge |
| `fact_player_availability_snapshot` | `(as_of_gw, fpl_id)` | 24,737 | `int_player_gw_base` |
| `fact_player_performance_snapshot` | `(as_of_gw, fpl_id)` | 24,737 | `int_player_gw_base` |
| `fact_player_market_snapshot` | `(as_of_gw, fpl_id)` | 24,737 | `int_player_gw_base` |
| `fact_team_fixture_snapshot` | `(as_of_gw, team_fpl_id)` | 640 | `int_team_fixture_base` |
| `fact_team_performance_context_snapshot` | `(as_of_gw, team_fpl_id)` | 640 | `int_team_fixture_base` |

### Views (7)

**FACT** — Two intermediate views and five feature views, all created as a side effect of snapshot materialisation and left in the database:

| View | Grain | Rows |
|---|---|---|
| `int_player_gw_base` | `(as_of_gw, fpl_id, round)` | 397,321 |
| `int_team_fixture_base` | `(as_of_gw, team_fpl_id, …)` | 10,564 |
| `fct_player_availability_features` | `(as_of_gw, fpl_id)` | 24,737 |
| `fct_player_performance_features` | `(as_of_gw, fpl_id)` | 24,737 |
| `fct_player_market_features` | `(as_of_gw, fpl_id)` | 24,737 |
| `fct_team_fixture_features` | `(as_of_gw, team_fpl_id)` | 640 |
| `fct_team_performance_context_features` | `(as_of_gw, team_fpl_id)` | 640 |

**FACT** — Five snapshot families exist in code and in the database. Only four have design documents under `docs/design/`; `team_performance_context` has none.

### The snapshot / PIT model

**FACT** — Snapshots are a **cross-product of every finished gameweek × every entity**, not a single latest-state row per entity. The `all_gws` CTE in `int_player_gw_base.sql` selects `DISTINCT event FROM fact_fixtures WHERE finished = 1`, then joins every player-round row where `round <= as_of_gw`. This is why `fact_player_availability_snapshot` has exactly as many rows as `fact_player_gw` (24,737): one row per player per as-of gameweek.

**FACT** — The PIT boundary is **inclusive of `as_of_gw`**. `rn_calendar = 1` is the most recent round `<= as_of_gw`, i.e. the as-of gameweek itself when the player featured. Window filters are on `rn_calendar` (`<= 3`, `<= 5`), never calendar arithmetic. This is stated explicitly in the model headers and enforced by SQL tests including `fact_test_pit_no_future_data.sql`.

This inclusivity is the single most important semantic fact about the warehouse and is the crux of the divergence with fpl-intelligence — see §4.2.

**FACT** — A documented, unresolved correctness limitation, stated in the `int_player_gw_base.sql` header: `team_fpl_id` reflects `dim_players` **at warehouse build time**, not the player's team at `as_of_gw`. Players who transferred mid-season carry the wrong team on all rows predating the move. No historical player-team mapping table exists.

**INFERENCE** — Given `dim_players.team_id` is overwritten on every build, this defect is silent, grows over a season, and is not detectable from the snapshot tables alone.

**OPEN QUESTION** — Is the mid-season transfer team-attribution defect acceptable at current scale, or does it need a slowly-changing `dim_player_team` before the snapshots can be trusted for historical backtests?

## 1.4 Contract enforcement

**FACT** — `warehouse/contracts.py` runs at the end of every build via `validate_build()`. Eight tables are registered in `build_contract_specs()`. Per table it checks: existence, required columns present, **exact schema match** (column order *and* declared type) for the five snapshots, minimum row count, grain uniqueness, and no NULLs in required columns. Any failure raises `ValueError` and aborts the build.

**FACT** — Row-count minimums are season-aware, not fixed. `_scaled_min_rows()` computes `finished_gameweeks × (entity_count × 0.5)`, so the threshold grows through the season instead of passing trivially in August.

**FACT** — Snapshot DDL is generated from a single source of truth. `warehouse/ddl.py` reads base-table DDL from `base_tables/*.sql` and renders snapshot DDL from the specs in `warehouse/schema_specs.py`; the same specs feed the contract checks. There is no duplicated schema definition between DDL and validation.

**INFERENCE** — This is the strongest part of the repo. Schema drift between the DDL, the SQL models, and the contract checks is structurally prevented rather than caught by convention.

## 1.5 Test coverage

**FACT** — 161 tests, **all passing** (`uv run pytest -q` → `161 passed in 0.94s`, run during this audit). Breakdown by marker: 137 `unit`, 24 `integration`, 0 `smoke`.

**FACT** — Coverage is layered and genuinely substantial for the snapshot pipeline:

- Python behavioural tests per snapshot family (`tests/{availability,market,performance,team_fixture,team_performance_context}/test_snapshot.py`), each building a controlled temp SQLite fixture via `tmp_path` with deliberate DGW, BGW, and edge-case data.
- 31 SQL constraint tests under `tests/*/sql/`, parametrised one-test-per-file, covering grain uniqueness, key nullability, PIT no-future-data, monotonicity, rate bounds, BGW/DGW flag consistency, and window-arithmetic sanity.
- Unit tests for player matching (`test_unit_matching.py`) and contract validation (`test_unit_contract.py`).

**FACT** — Despite the `integration` marker's declared meaning ("tests against real master.db"), the five snapshot test modules are marked `unit` and build their own temp databases. They therefore run in CI and do not depend on a built warehouse. This is a strength.

### Three real gaps

**FACT — CI runs only unit tests.** `.github/workflows/ci.yml` has a single step, `uv run pytest -m unit`. The 24 integration tests never execute in CI. There is no lint step, no `vulture` step, and no type-check step, despite `ruff` and `vulture` being declared dev dependencies. By contrast fpl-ingest's CI runs unit tests, integration tests, a contract-artifact check, and `mypy`.

**FACT — The integration tests validate the wrong database.** `tests/test_team_normalization.py:23` hardcodes:

```python
WAREHOUSE = Path.home() / "Documents/FPL/data/warehouse/master.db"
```

It ignores `WAREHOUSE_DB_PATH` entirely. That path holds a **stale April 1 database**, while the build writes to `~/Documents/fpl-warehouse/data/warehouse/master.db` (April 13). The 24 integration tests are asserting against a database 12 days older than the one the pipeline produces, and they pass only because the assertions are loose — `test_row_count_matches_expectation` asserts `count >= 290` against 309 stale rows where the live database holds 318.

**FACT — No end-to-end build test.** No test invokes `build_all()` or the CLI. The orchestration in `build.py`, the fixture bridge, the Understat xG enrichment, and `validate_build()` are exercised only by running the real pipeline by hand.

**INFERENCE** — The snapshot SQL layer is well covered; the ingestion-and-merge layer (`builders/dimensions.py`, `builders/facts.py`) and the build orchestration are covered mainly by tests pointed at a stale artifact.

## 1.6 The two-database problem

**FACT** — Two `master.db` files exist with materially different schemas:

| | `~/Documents/fpl-warehouse/data/warehouse/master.db` | `~/Documents/FPL/data/warehouse/master.db` |
|---|---|---|
| Size / built | 11.3 MB, 2026-04-13 | 8.4 MB, 2026-04-01 |
| Status | **live** — current code writes here | **stale** — legacy |
| Tables | 12 | 10 |
| Views | 7 (`int_`/`fct_`) | 10 (`v_*`, all retired) |
| Snapshot tables | all 5 present | **none** |
| Extra tables | — | `fact_decision_snapshot`, `fact_transfer_snapshot`, `fact_manager_squad` |

**FACT** — The live path is the repo-local one *only because* `~/Documents/FPL/.env` sets `WAREHOUSE_DB_PATH` to it. The hardcoded default in `warehouse/db.py:23` still points at the stale location. Remove or lose the `.env` and the build silently starts writing to the stale database instead of failing.

**FACT** — The stale database still contains the ten retired `v_*` views that `docs/history/views_retirement.md` documents as removed, plus three tables the current warehouse code does not create.

**OPEN QUESTION** — Can `~/Documents/FPL/data/warehouse/master.db` be deleted? Determining this requires knowing whether fpl-decision-engine-src or fpl-advisor-api still read it — see §1.7. It is not safe to delete on the evidence gathered here.

## 1.7 Is anything consuming it?

**FACT** — **Yes, but not fpl-intelligence.** The consumer picture is the most consequential finding in this audit.

### fpl-intelligence consumes nothing from the warehouse

**FACT** — A grep for `master.db`, `warehouse`, `WAREHOUSE`, and `fpl_warehouse` across all `*.py`, `*.toml`, `*.yaml`, `*.yml`, and `*.cfg` in fpl-intelligence returns **zero matches** outside `archive/`. There is no dependency declaration, no import, no path reference.

**FACT** — `dal/config.py` is three lines:

```python
DB_PATH: Path = Path(os.environ.get("FPL_DB_PATH", "~/.fpl/fpl.db")).expanduser()
```

`FPL_DB_PATH` resolves to `fpl.db` — fpl-ingest's output. **fpl-intelligence reads fpl-ingest directly and bypasses the warehouse entirely.**

### fpl-advisor-api consumes it, and its contract is broken

**FACT** — `fpl-advisor-api/pyproject.toml` declares `fpl-warehouse` as a git dependency (`ssh://git@github.com/gisaf22/fpl-warehouse`), alongside `fpl-ingest` and `understat-ingest`. Its `docker-compose.yml` and `render.yaml` both mount `master.db` at `/data/warehouse/master.db`, read-only.

**FACT** — It queries `dim_gameweeks`, `dim_players`, `fact_player_gw` — all of which the current warehouse produces — **and `fact_transfer_snapshot`**, which it does not. `services/recommender.py:94-95`:

```sql
JOIN fact_transfer_snapshot fts ON dp.fpl_id = fts.fpl_id
 AND fts.as_of_gw = (SELECT MAX(as_of_gw) FROM fact_transfer_snapshot)
```

**FACT** — `fact_transfer_snapshot` exists only in the **stale** database. The current fpl-warehouse build does not create it. Its producer is a different repo: `fpl-decision-engine-src` (`decisions/shared/src/core/data/snapshot.py`, `decisions/captain/src/fpl_captain/pool.py`).

**INFERENCE** — fpl-advisor-api pointed at a freshly-built current warehouse would fail with `no such table: fact_transfer_snapshot`. It works today only against the stale database, or only if fpl-decision-engine-src writes that table into whichever database it is pointed at first.

**FACT** — This means `master.db` has **multiple writers across repositories**. This directly contradicts `warehouse/db.py:53-59`, whose `connect_warehouse()` docstring states the warehouse "is the single SQLite file this project owns and writes to" and enables WAL "to support the single-writer, read-many pattern."

**OPEN QUESTION** — Is fpl-advisor-api still live? If so, `fact_transfer_snapshot` is a cross-repo write into a database fpl-warehouse believes it owns exclusively, and the ownership boundary needs an explicit decision.

**OPEN QUESTION** — Is fpl-decision-engine-src (last commit 2026-04-04) still active, or superseded by fpl-intelligence? Whether the warehouse's decision/transfer surface must be preserved depends entirely on this.

### Verdict

**FACT** — fpl-warehouse is **not unused scaffolding**. It is a complete, tested, contract-enforced pipeline producing five governed snapshot families, with at least one declared downstream consumer.

**INFERENCE** — It is nonetheless **bypassed by the repo doing the most active work**. fpl-intelligence has committed 15+ times since fpl-warehouse's last commit (2026-04-13) and reads around it. The warehouse's actual consumers are the older decision-engine/advisor-api line, whose activity stopped in April.

## 1.8 Operational execution

**FACT** — Execution is **entirely manual**. `fpl-warehouse` is a console script (`fpl_warehouse.cli:main`) invoked by hand. Prerequisites per the README: run `fpl-ingest` and `understat-ingest` first.

**FACT** — `docs/governance/data_freshness_policy.md` states the intended cadence twice — "refresh sources twice daily", "run full source refresh and warehouse rebuild twice daily" — and the README repeats it: "operated as a twice-daily latest-reconstructed-truth rebuild."

**FACT** — **No scheduler implements this.** Verified: no crontab for the user (`crontab -l` → "no crontab"); the repo's only workflow is `ci.yml`, which runs tests on push/PR and never invokes a build; no launchd agent references fpl-warehouse. The one relevant-looking launchd agent, `com.thedugout.pull-fpl-data`, belongs to an unrelated project (`Springboard/Google5DayAI/the-dugout`) and writes to a different database.

The twice-daily rebuild is a **documented policy with no implementing mechanism**.

**FACT** — The build is not idempotent with respect to freshness: base facts upsert cumulatively while snapshots are dropped and rebuilt, so a build against stale sources silently produces stale-but-valid snapshots. Contract checks would pass, since minimums scale off `fact_fixtures.finished` which would also be stale.

**FACT** — There is no freshness gate. Unlike fpl-intelligence, which has `dal/staging/stg_freshness.py` raising `DataFreshnessError`, fpl-warehouse checks only that the source files *exist* (`cli.py:57-60`), never that they are current.

**OPEN QUESTION** — Should the twice-daily cadence be implemented, or should the documentation be corrected to describe manual-on-demand operation? Right now the docs describe a system that does not exist.

## 1.9 Documentation drift

Specific, verified inaccuracies:

**FACT** — `README.md` documents `fpl-warehouse --force` ("Rebuild from scratch"). No `--force` argument exists in `cli.py`. The README also omits `--threshold`, `--fpl-db`, `--understat-db`, and `--warehouse-db`, which do exist.

**FACT** — `README.md`'s "What it does" section describes player matching as "Fuzzy-matches FPL players to Understat players using name + team". As of `cd90148` the primary mechanism is the deterministic reep lookup, with fuzzy matching as fallback only. The README predates the change described in its own repo's HEAD commit message.

**FACT** — `README.md`'s table list names five tables and omits the five snapshot tables, `dim_gameweeks`, and `fact_match_stats` — i.e. it omits the warehouse's actual primary outputs.

**FACT** — The `refresh_player_availability()` docstring references a `--refresh-availability` CLI flag that does not exist.

**FACT** — Neither the README nor the docs mention the reep network dependency or its cache.

**FACT** — `team_performance_context` has no design document, unlike the other four snapshot families.

---

# 2. fpl-ingest

Verification of known context, plus extension.

## 2.1 Known context — verified with corrections

| Claim | Status |
|---|---|
| ELT-aligned layout: `extract/`, `transform/`, `load/`, `schema/`, `orchestration/` | **FACT — confirmed.** All five packages exist under `src/fpl_ingest/`, exactly as described. |
| Writes SQLite | **FACT — confirmed.** `load/store.py`, `load/db_setup.py`. |
| mypy clean | **FACT — enforced in CI.** `ci.yml` runs `uv run mypy src/fpl_ingest` as a required step. |
| Has replay command | **FACT — confirmed.** `orchestration/replay.py`. |
| Cross-table integrity checks | **FACT — confirmed.** `load/integrity.py`. |
| Schema versioning | **FACT — confirmed.** `schema/compiler.py` emits contract artifacts to `artifacts/contract/`; CI asserts the checked-in artifacts match compiled output. |
| **393 unit / 247 integration / 4 performance tests** | **FACT — drifted.** Actual counts at HEAD `1134a88`: **413 unit, 248 integration, 4 perf, 0 smoke; 476 collected total.** The repo has moved since 2026-08-17. Shape and proportions hold; absolute numbers are stale. |
| Azure Blob persistence not yet built | **FACT — confirmed, and it is the live blocker.** See §2.3. |

## 2.2 Extension — what the known context did not cover

**FACT — Public data contract.** `schema/definition.py` declares `PUBLIC_TABLES`, eight tables each with an explicit declared grain:

| Table | Declared grain | Unique key |
|---|---|---|
| `players` | one row per player | `id` |
| `teams` | one row per team | `id` |
| `fixtures` | one row per fixture | `id` |
| `fixture_stats` | one row per (fixture_id, identifier, element) | `(fixture_id, identifier, element)` |
| `gameweeks` | one row per (element_id, round) | `(element_id, round)` |
| `player_histories` | one row per (element_id, round, fixture) | `(element_id, round, fixture)` |
| `events` | one row per event/gameweek | `id` |
| `element_types` | one row per element type | `id` |

This is the shared contract surface both downstream repos read from, and the grain difference between `gameweeks` and `player_histories` is the root of the divergence in §4.2.

**FACT — APIs called.** Four FPL API stages under `extract/stages/`: `bootstrap.py`, `element_summary.py`, `fixtures.py`, `gameweeks.py`. HTTP layer under `extract/http/` includes an async client, a sync client, and explicit rate limiting (`rate_limiter.py`, `rate_config.py`).

**FACT — Audit metadata.** Runs and stages are recorded to a `_runs` table (referenced by the scheduled workflow's export step) via `orchestration/run_status.py` and `orchestration/execution_state.py`.

**FACT — Raw artifact preservation.** Raw API responses are written to `FPL_RAW_DIR`, retained for inspection and replay.

**FACT — Documentation.** Well-covered: `docs/architecture/system-purpose.md`, `docs/architecture/architecture.md`, `docs/data-contract.md`, `docs/navigation-map.md`, `docs/adr/` (including ADR-001 on the SQLite storage choice), `docs/architecture/performance-assessment.md`, plus `CONTRIBUTING.md` and `SECURITY.md`.

**FACT — CI.** The strongest of the three repos: unit tests, integration tests, schema-contract artifact verification, and mypy, all as required steps.

## 2.3 Scheduling — the Azure gap, made concrete

**FACT** — `.github/workflows/scheduled_run.yml` is **live**, not a stub: `on.schedule.cron: "0 8 * * *"` plus `workflow_dispatch`. It checks out, `uv sync`s, runs `uv run fpl-ingest run`, then exports `_runs` to `_runs_audit.json`.

**FACT** — The workflow's own header comments identify the gap precisely: the GitHub runner is ephemeral, so `fpl.db` is discarded when the job ends. The comments propose uploading to "Azure Blob, S3, or a hosted database" and restoring at job start. Neither is implemented.

**INFERENCE** — The scheduled job therefore runs daily at 08:00 UTC and **produces no durable output**. It ingests into a container filesystem that is then destroyed. The only surviving artifact is the `_runs` audit JSON. The `fpl.db` that fpl-warehouse and fpl-intelligence actually read is the local one at `~/Documents/FPL/data/fpl/fpl.db`, last written 2026-04-13, produced by a manual run.

**OPEN QUESTION** — The daily scheduled run is currently pure waste: it consumes Actions minutes and hits the FPL API to produce nothing durable. Should it be disabled until blob persistence exists, or is blob persistence the immediate next piece of work?

**FACT** — This makes the local `fpl.db` the real source of truth for both downstream repos, refreshed manually, with no automation behind it anywhere in the system.

---

# 3. fpl-intelligence

Verification of the 2026-08-17 classification, plus extension.

## 3.1 The dal/ file classification — verified, still holds

**FACT** — All 42 files named in the prior investigation's classification are **still present at their stated paths** at HEAD `ec9c537`. Nothing has been moved, renamed, or deleted. The fpl-ingest-bound / domain split remains applicable as written.

**FACT** — `dal.pipeline.load()` still performs staging → intermediate → fct → feat → mart internally and returns a merged result. Confirmed from `dal/pipeline.py` imports (`load_staged_entities`, `get_player_fixture_base`, `build_player_gameweek_spine`, `build_player_gameweek_state`, `build_prepared_dataset`) and its module docstring.

**FACT** — The layer structure is enforced by tests, not just convention. `tests/test_dal_architecture.py` and `tests/test_layer_isolation.py` assert that the feature layer does not import from `staging`, `intermediate`, or `fct`, and that the validation layer does not import from `fct`.

## 3.2 Public API surface — **wider than the known context states**

The known context says: "Every production caller uses only `dal.pipeline.load`, `dal.config.DB_PATH`, `dal.mart.{POSITION_CODE_MAP, GOVERNED_SIGNAL_COLUMNS}`, `dal.exceptions`."

**FACT — This is now incomplete.** Three additional public entry points are called from outside `dal/`:

| Symbol | Called from | Kind |
|---|---|---|
| `dal.pipeline.run` | `examples/quickstart.py`; 14 notebooks under `model/eval/`, `research/foundation/`, `research/diagnostic/` | rebuild entry point |
| `dal.pipeline.load_fixture_map` | `model/terms/bonus/mechanistic_scoping.ipynb`; `tests/test_pipeline.py:256` | map accessor |
| `dal.pipeline.load_opponent_map` | `model/features/opp_xgc_scoping.ipynb`; `tests/test_pipeline.py:275` | map accessor |

**FACT** — The four originally-listed symbols remain the dominant surface. Production Python callers (`operational/recommend.py`, `operational/starting_xi.py`, `decisions/starting_xi/{harness,sampler}.py`, `research/families/*/validate/study.py`, `model/assemble/composition_study.py`) do use only `dal.pipeline.load` + `dal.config.DB_PATH`. `serve/input_contracts.py` uses `dal.mart.GOVERNED_SIGNAL_COLUMNS`; `research/registry/population_builder.py` uses `dal.mart.POSITION_CODE_MAP`.

**FACT** — The widening comes from notebooks (`run`, `load_fixture_map`, `load_opponent_map`). Whether notebooks count as "production callers" is a definitional question, but they are live, committed, non-archived call sites.

**FACT** — One test reaches deeper: `tests/test_domain_fpl_squad.py:23` imports `dal.staging.stg_entities.get_staged_element_types`. Test-only, but it is a coupling to a staging internal.

**OPEN QUESTION** — Do `run`, `load_fixture_map`, and `load_opponent_map` count as part of the committed public interface, or as notebook-only conveniences? This materially changes the extraction surface if dal/ is ever split.

## 3.3 No dead code — still holds

**FACT** — Confirmed. Every file in `dal/` has at least one live import path, traced through `dal/__init__.py`, the per-package `__init__.py` re-exports, and external call sites. The two files flagged ambiguous in the prior audit both have confirmed callers: `dal/validation/grain.py` is imported by `fct_gameweek_context`, `fct_player_gameweek`, `feat_player_gameweek`, `int_opponent_context`, `int_player_fixture`, and `mart_schema`; `dal/validation/joins.py` is imported by `fct_player_gameweek`, `int_fixture_context`, and `int_player_fixture`.

## 3.4 Extension — file storage, contracts, execution

**FACT — Storage.** `dal/pipeline.py` maintains a materialised mart cache beside the source database: a mart file (`_mart_path`), a temp path for atomic writes (`_mart_tmp_path`), and a JSON manifest (`_manifest_path`). Cache validity is decided by `_cache_valid()` from a source-database hash (`_hash_db`) plus a schema fingerprint (`_mart_schema_fingerprint`). `load()` raises `MartNotBuiltError` / `MartSchemaError` when the cache is absent or stale, and callers respond by calling `run(force=True)` — this rebuild-on-exception pattern is repeated across the notebooks.

**FACT — Reproducibility.** `dal/reproducibility.py` computes a spine fingerprint (`compute_spine_fingerprint`); the manifest records `source_db_hash` and `data_cutoff_gw`; `MartResult` carries both so consumers can detect staleness.

**FACT — Freshness gate.** `dal/staging/stg_freshness.py::validate_data_freshness(db_path, gw)` raises `DataFreshnessError` when no `player_histories` rows exist for `gw - 1`. This is a real gate; fpl-warehouse has no equivalent.

**FACT — Staging contracts.** Six YAML contracts under `dal/staging/contracts/` declare `source_table`, `pk_columns`, and per-column `source` → `canonical` renames with dtype and nullability. The declared source tables are `element_types`, `events`, `fixtures`, `player_histories`, `players`, `teams` — all six are fpl-ingest `PUBLIC_TABLES`. The rename layer is where FPL's raw vocabulary becomes canonical (`id` → `player_id`, `round` → `gw`, `element_id` → `player_id`).

**FACT — `data_cutoff_gw`.** Flagged ambiguous by the prior audit; now traced. It is a parameter of `pipeline.run()` defaulting to `None`, resolved at `pipeline.py:292` as `int(spine["gw"].max())` when not supplied, written into the manifest, and surfaced on `MartResult`. It is a mart-cache/PIT-boundary concept, not an FPL domain concept.

**FACT — No APIs called.** fpl-intelligence makes no network calls for data. It reads `fpl.db` only.

**FACT — Execution.** Manual, like the others. Entry points are `operational/recommend.py`, `operational/starting_xi.py`, and notebooks. No scheduler, no CI-driven build.

**FACT — Working tree state.** 30+ modified files uncommitted at audit time, spanning `docs/`, `model/`, `research/`, `domain/`, and `pyproject.toml`. This is the actively-developed repo.

---

# 4. Cross-repo: the overlap question

The brief asked whether the dal/ classification implies real duplication with fpl-warehouse. **Confirmed — and the duplication is worse than "two implementations of the same thing", because the two implementations disagree semantically.**

## 4.1 Both repos build a player × gameweek fact, from different source tables

**FACT:**

| | fpl-warehouse | fpl-intelligence |
|---|---|---|
| Output | `fact_player_gw` | `dal.fct.fct_player_gameweek` spine |
| Grain | `(fpl_id, round)` | `(player_id, gw)` |
| **Source table** | `fpl.db.gameweeks` | `fpl.db.player_histories` |
| Source grain | `(element_id, round)` | `(element_id, round, fixture)` |
| Source endpoint | event-live aggregate | element-summary history |
| Aggregation | none needed | `_aggregate_to_gw_grain` collapses fixtures → GW |
| Implementation | SQL | pandas |

**FACT** — These are **different fpl-ingest tables with different grains**. `gameweeks` is pre-aggregated to `(element_id, round)` by the FPL live endpoint. `player_histories` is per-fixture, so a double gameweek is two rows that fpl-intelligence must aggregate itself.

**INFERENCE** — This is the deeper problem. Because the warehouse takes the pre-aggregated live table, it inherits whatever the FPL API does about double gameweeks and never handles DGW/BGW explicitly at the fact layer. fpl-intelligence aggregates per-fixture rows itself and carries explicit `is_bgw` / `is_dgw` / `fixture_context ∈ {BGW, SGW, DGW}` semantics, validated by `dal/fct/validation/semantics.py` (`validate_bgw_correctness`, `validate_dgw_correctness`) and dedicated tests. The two are not guaranteed to agree on any DGW row, and nothing anywhere reconciles them.

**OPEN QUESTION** — Which source table is canonical for player-gameweek facts — `gameweeks` or `player_histories`? They are not interchangeable, and no document in any repo states a preference. This is the single most consequential unresolved question surfaced by this audit.

## 4.2 Both compute rolling windows — with opposite PIT conventions

**FACT** — Overlapping feature families:

| fpl-intelligence (`dal/feat/feat_schema.py`) | fpl-warehouse (`fact_player_availability_snapshot`) |
|---|---|
| `minutes_roll3`, `minutes_roll5`, `minutes_roll8` | `minutes_avg_last_3gws`, `minutes_avg_last_5gws` |
| `minutes_trend` | `minutes_avg_delta_last_3gws_vs_last_5gws` |
| `xgi_roll3`, `xgi_roll5` | (performance snapshot) |
| `xgc_roll3`, `xgc_roll5` | (performance snapshot) |
| `clean_sheets_roll3/5`, `goals_conceded_roll3/5` | (performance snapshot) |
| `fixture_context` (BGW/SGW/DGW) | `fact_team_fixture_snapshot` BGW/DGW flags |

**FACT — The window conventions are opposite, and this is the critical detail:**

- **fpl-intelligence** uses `x.shift(1).rolling(N, min_periods=1).mean()` (`dal/feat/feat_player_gameweek.py:98-106`). The lag-1 shift means the window covers **strictly prior gameweeks**. The comment is explicit: "Lag-1: prior GWs only." It also tracks `is_warmup_gw` for a player's first GW, where rolling signals are undefined.
- **fpl-warehouse** filters `rn_calendar <= 3` / `<= 5` where `rn_calendar = 1` is the most recent round `<= as_of_gw` (`src/models/availability/int_player_gw_base.sql`). The window is **inclusive of the as-of gameweek**.

So `minutes_roll3` and `minutes_avg_last_3gws` are **not the same quantity**. One answers "what was known before GW N was played" (prediction-safe); the other answers "what was true as of the end of GW N" (state-of-the-world).

**FACT** — Both are internally correct and both are labelled PIT-safe in their own repo's documentation. Both statements are true within their own convention. Neither repo acknowledges the other's convention exists.

**INFERENCE** — Any future attempt to substitute warehouse snapshots for dal features — or to join them — would silently introduce one-gameweek lookahead leakage into fpl-intelligence's models unless the convention difference is handled explicitly. The column names are similar enough to invite exactly that mistake.

**OPEN QUESTION** — Which PIT convention is canonical: lag-1 exclusive (prediction-time) or as-of inclusive (state-at-time)? Both are legitimate, and a system could reasonably need both — but then they need distinguishable names, which they currently do not have.

## 4.3 Both maintain a staging/canonicalisation layer over the same tables

**FACT** — Both read the same fpl-ingest tables and both rename FPL vocabulary to a canonical form:

- fpl-intelligence: six YAML contracts, declarative, `id` → `player_id`, `round` → `gw`.
- fpl-warehouse: SQL in `builders/`, imperative, `element_id` → `fpl_id`, `expected_goals` → `fpl_xg`.

They produce **different canonical vocabularies for the same underlying fields**. `fpl_id` vs `player_id`; `round` vs `gw`; `fpl_xg` vs the staged `expected_goals`.

**INFERENCE** — This is the duplication the prior investigation predicted when it classified `staging/*` and the six contract YAMLs as "fpl-ingest-bound (canonical/generic)". The prediction is confirmed: two independent canonicalisation layers over one source, disagreeing on names.

## 4.4 What is genuinely NOT duplicated

**FACT** — Worth stating precisely, because it bounds the problem:

- **Understat integration is warehouse-only.** Player matching (reep + fuzzy), the fixture bridge, `fact_shots`, `fact_match_stats`, and xG-chain/buildup enrichment exist only in fpl-warehouse. fpl-intelligence has no Understat access at all.
- **Modelling, decisions, and serving are intelligence-only.** `model/`, `decisions/`, `serve/`, `research/`, and the governed-signal promotion machinery have no warehouse counterpart.
- **API extraction, replay, and raw artifact retention are ingest-only.**

**INFERENCE** — The overlap is confined to one band: canonicalisation of fpl-ingest tables, the player-gameweek fact, and rolling-window feature derivation. Outside that band the three repos are cleanly separated.

## 4.5 Data-flow reality

**FACT** — Actual current flow, as opposed to any diagram in any repo:

```
FPL API ──> fpl-ingest ──> fpl.db ──┬──> fpl-warehouse ──> master.db (live) ──> fpl-advisor-api [contract broken]
                                    │         ^                  ^
Understat ──> understat-ingest ─────┼─────────┘                  └── fpl-decision-engine-src [also writes]
                  understat.db      │
reep CSV (github) ──────────────────┘
                                    │
                                    └──> fpl-intelligence (dal/) ──> mart cache ──> model/, decisions/, serve/
```

**FACT** — fpl.db has two independent downstream consumers that never meet. The warehouse is not on fpl-intelligence's path at any point.

---

# 5. Consolidated open questions

Ordered by consequence.

1. **Which fpl-ingest table is canonical for player-gameweek facts — `gameweeks` or `player_histories`?** Different grains, different DGW behaviour, no stated preference anywhere. (§4.1)
2. **Which PIT convention is canonical — lag-1 exclusive or as-of inclusive?** Both currently exist under near-identical column names; conflating them injects lookahead leakage. (§4.2)
3. **Is fpl-advisor-api still live?** It declares fpl-warehouse as a dependency and queries `fact_transfer_snapshot`, which the current warehouse does not produce. (§1.7)
4. **Is fpl-decision-engine-src still active, or superseded by fpl-intelligence?** It writes into `master.db`, breaking the warehouse's single-writer assumption. (§1.7)
5. **Should fpl-ingest's daily scheduled run be disabled until Azure Blob persistence exists?** It currently runs daily and produces nothing durable. (§2.3)
6. **Should the twice-daily warehouse rebuild be implemented, or the documentation corrected?** The cadence is documented in two places and implemented nowhere. (§1.8)
7. **Can the stale `~/Documents/FPL/data/warehouse/master.db` be deleted?** Depends on Q3 and Q4. Not safe to delete on current evidence. (§1.6)
8. **Should `~/Documents/FPL/.env` be replaced by tracked configuration?** It is untracked, machine-local, and load-bearing — it alone keeps the build writing to the live database. (§1.1)
9. **Should the reep CSV be vendored and pinned?** Unpinned third-party `main`-branch dependency on the critical build path. (§1.1)
10. **Do `pipeline.run`, `load_fixture_map`, and `load_opponent_map` count as dal's committed public API?** Changes the extraction surface. (§3.2)
11. **Is the mid-season transfer team-attribution defect acceptable?** `team_fpl_id` is build-time, not as-of-time; silent and worsening. (§1.3)
12. **Was the brief's "no documentation" premise about architecture docs specifically?** fpl-warehouse has 15 doc files and they are mostly accurate. (§1.0)

---

# 6. Audit coverage and limits

**Verified by execution:** fpl-warehouse test suite (161 passed); test collection counts for fpl-warehouse and fpl-ingest; live SQLite inventory of both `master.db` files and `understat.db`; crontab and launchd enumeration.

**Verified by reading:** all fpl-warehouse source and SQL models; fpl-warehouse `docs/` (spot-checked against code); fpl-ingest `schema/definition.py`, both workflows, `pyproject.toml`; fpl-intelligence `dal/` structure, `config.py`, `pipeline.py` signatures, `feat_schema.py`, staging contracts; consumer queries in fpl-advisor-api.

**Not verified:**
- fpl-ingest and fpl-intelligence test suites were **not executed** — counts for fpl-ingest come from `pytest --collect-only`, and no pass/fail claim is made for either repo.
- fpl-intelligence has 30+ uncommitted modified files; findings reflect the working tree, not a committed state.
- Whether fpl-advisor-api or fpl-decision-engine-src are deployed and running was not determined — only their source was read.
- The mypy-clean claim for fpl-ingest is reported from its CI configuration, not from a run performed here.
