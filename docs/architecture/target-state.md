# FPL Data Platform — Target Architecture

**Deliverable 2.** Canonical location: `fpl-warehouse/docs/architecture/target-state.md`.
Referenced, not copied, from `fpl-ingest` and `fpl-intelligence`.

Built directly on `docs/architecture/current-state.md` (2026-08-24 audit). Where this doc
states a decision, it is a decision Fred made explicitly during the architecture review —
not a recommendation being proposed for the first time here.

---

## 1. Layer diagram

```
SOURCE SYSTEMS
  FPL API            Understat            (future sources)
        \                  |                    /
         \                 |                   /
INGESTION  (fpl-ingest + understat-ingest — same pattern)
  - call source APIs, handle rate limits/retries
  - validate SOURCE SHAPE only (not business logic)
  - NO flattening, NO fact/dim tables, NO analytical logic
        |
        v
RAW STORAGE  (S3, one bucket, source/endpoint-keyed)
  s3://bucket/raw/{source}/{endpoint}/{extraction_date}/{run_id}/payload.json
  - immutable, replayable, append-only
        |
        v
WAREHOUSE  (fpl-warehouse, dbt)
  sources (raw S3 JSON)
    -> staging (structural normalization, canonical renames)
    -> intermediate
    -> facts / dimensions   <- fact_player_gw sourced from player_histories (per-fixture),
    |                          NOT from gameweeks (pre-aggregated)
    -> analytical marts / snapshots
        |
        v
FPL INTELLIGENCE  (fpl-intelligence)
  - consumes warehouse marts only
  - owns: lag-1 feature derivation, research, modeling, decisions, serving
        |
        v
RESEARCH / MODELS / DECISIONS
```

---

## 2. Ingestion boundary

**Owner:** `fpl-ingest` (FPL) and `understat-ingest` (Understat), same pattern, same target shape.
Future sources follow the identical pattern — this is the one abstraction judged genuinely
useful now rather than premature generalization (per the original scoping doc's own test).

**Responsibilities:**
- Call source APIs/scrapers/files. Retries, rate limiting, backoff.
- Validate that a response has the *shape* the source contract expects (e.g. "bootstrap-static
  returned a JSON object with an `elements` array"), not that its *content* is analytically
  correct.
- Write raw payloads to S3, unmodified, one object per (source, endpoint, extraction run).
- Run metadata, lineage, idempotency, replayability — same concepts as today, now pointed at
  S3 rather than SQLite.

**Explicitly NOT ingestion's job (moved out, relative to current fpl-ingest):**
- Flattening payloads into structured tables (`transform/`'s current role).
- Writing structured rows to any database (`load/`'s current SQLite-writer role).
- The `PUBLIC_TABLES` schema contract — no fixed table list. Ingestion's contract is
  "raw object per source/endpoint/run," not a table schema.
- Any concept of grain, fact, or dimension. Ingestion does not know what `player_histories`
  or `fact_player_gw` are.

**What survives from current fpl-ingest unchanged:** `extract/` (API clients, rate limiting),
raw-shape validation, replay command, run/audit metadata — same code, redirected to write S3
objects instead of SQLite rows.

---

## 3. Raw storage boundary

**Owner:** shared infrastructure (S3), not owned by any one repo's code — but the *layout
convention* is owned jointly by ingestion (writer) and warehouse (reader).

**Decision:** S3, source/endpoint-keyed, not table-keyed.

```
s3://<bucket>/raw/{source}/{endpoint}/{extraction_date}/{run_id}/payload.json
```

- `source=fpl, endpoint=bootstrap-static`
- `source=fpl, endpoint=element-summary/{player_id}`
- `source=understat, endpoint=match_info`
- future: `source=<new>, endpoint=<new>` — no ingestion code change required to add a source
  once a source's client exists; no warehouse code assumes a fixed source list either, though
  a new source does require a new staging model.

**Properties:** immutable, append-only, replayable without re-calling the source API,
identifiable by source/endpoint/extraction/run. No expensive infrastructure (no Kubernetes, no
streaming) — this is the "complexity proportional to value" principle from the original scoping
doc, applied.

---

## 4. Warehouse boundary

**Owner:** `fpl-warehouse`. This boundary absorbs more responsibility than fpl-warehouse
currently has, because flattening/structuring — previously split between fpl-ingest's
`transform/`+`load/` and fpl-warehouse's own `builders/` — now belongs entirely here.

**Responsibilities:**
- `sources`: dbt sources pointed at raw S3 JSON (replacing today's direct SQLite reads of
  `fpl.db`/`understat.db`).
- `staging`: parse raw JSON into structured rows, canonical renames (today's dal-side and
  warehouse-side canonicalization layers both collapse into this one place — no more `fpl_id`
  vs `player_id` disagreement).
- `intermediate` / `facts` / `dimensions`: **`fact_player_gw` is sourced from `player_histories`
  (per-fixture grain), never from `gameweeks` (pre-aggregated).** DGW/BGW handling is explicit
  and owned here, not inherited silently from a source API's own aggregation.
- `marts`: governed, stable analytical outputs — the only thing fpl-intelligence is allowed to
  depend on.
- Snapshots stay state-of-truth / as-of-inclusive (`round <= as_of_gw`). This is warehouse's
  correct convention and does not change.

**Naming fix required, not architectural:** rename warehouse's `minutes_avg_last_Ngws`-style
columns to make clear they are as-of-inclusive, distinct from any lag-1 feature dal computes
downstream — prevents the accidental-join/leakage risk flagged in the current-state audit.

**Dropped from warehouse's scope:** `fact_transfer_snapshot` — its only consumer,
`fpl-advisor-api`, is confirmed not running. Not carried into target state.

---

## 5. Intelligence boundary

**Owner:** `fpl-intelligence`. Unaffected in shape by today's decisions — it already consumes
via `dal.pipeline.load()` and should continue to, just pointed at warehouse marts instead of
`fpl.db` directly once the warehouse is producing them.

**Responsibilities (unchanged):**
- Lag-1 / prediction-safe feature derivation (`.shift(1).rolling(N)`) — this is explicitly a
  feature-store concern, owned here, not by the warehouse. Warehouse gives state-of-truth;
  intelligence derives prediction-safe views from it.
- Research, modeling, decision logic (Starting XI slice, captaincy, etc.), serving.
- Governed signal promotion, evaluation.

**Not warehouse's job to replicate.** The warehouse should not build a second lag-1 feature
layer — that would recreate exactly the two-implementations-disagreeing problem this whole
audit surfaced.

---

## 6. Data contracts (boundary-to-boundary)

| Contract | Between | Shape |
|---|---|---|
| Source contract | source API → ingestion | raw shape validation only (schema exists, required top-level keys present) |
| Raw contract | ingestion → warehouse | S3 object key convention (`source/endpoint/date/run_id`), immutable |
| Warehouse contract | warehouse internal | dbt source/staging/intermediate/fact/mart layering, tested (uniqueness, not-null, relationships, PIT no-future-data) |
| Mart contract | warehouse → intelligence | governed marts only, `dal.pipeline.load()`-equivalent single entry point, no direct read of warehouse internals |

No layer reaches past its immediate neighbor. Intelligence never reads raw S3. Ingestion never
knows what a fact table is.

---

## 7. Season strategy

- **Historical season** (existing `fpl.db`): explicitly NOT raw. It is a controlled historical
  source, entering the warehouse via its own legacy/reconstruction path, not pretending to be
  S3-raw. Original API payloads for that season are not recoverable and this is stated, not
  hidden.
- **Current season**: raw S3 objects from live ingestion → warehouse, same pipeline as any
  future season.
- Both must land in the same warehouse fact/dim shape (`fact_player_gw` at
  `(player_id, gw)`) even though their raw representations differ — this is staging's job to
  reconcile, and is exactly the "source evolution, schema normalization, historical backfill"
  demonstration the original scoping doc asked the two-season milestone to prove.

## 8. Multi-source strategy

- `understat-ingest` moves to the same raw-capture pattern as `fpl-ingest` — same S3 layout,
  same "no shaping" boundary. This was previously a separate, differently-shaped repo; it is
  now the second proof point (after FPL) that the ingestion pattern generalizes, rather than
  being FPL-specific machinery with Understat bolted on.
- Adding a new source later means: a new API client under `extract/`, a new `source=` prefix in
  S3, a new warehouse staging model. No change to ingestion's core mechanics, no change to
  intelligence at all.

---

## 9. What this resolves from the current-state audit

- Q1 (canonical player-gw source) — resolved: `player_histories`.
- Q2 (PIT convention conflict) — resolved: warehouse owns as-of-inclusive, intelligence owns
  lag-1; both correct, now explicitly non-competing, naming fix pending.
- Q3 (fpl-advisor-api) — confirmed down; `fact_transfer_snapshot` dropped from scope.
- Q9 (reep CSV vendoring), Q11 (mid-season transfer attribution) — unresolved, out of scope for
  this doc, carried into Deliverable 5 (warehouse strategy) as concrete build items.
- Q4 (fpl-decision-engine-src) — deliberately deferred, not blocking.

## 10. What this doc does not do

Does not specify dbt model names, migration phases, or which existing warehouse SQL survives
verbatim — that is Deliverable 5. Does not specify fpl-ingest's exact S3 client implementation
or what happens to existing `fpl.db` during transition — that is Deliverable 4. This doc fixes
the shape; the next two fix the path to it.