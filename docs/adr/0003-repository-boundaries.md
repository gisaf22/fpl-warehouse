# 0003. Repository boundaries: ingest captures, the warehouse structures, intelligence decides

- Status: accepted
- Date: 2026-10-09
- Decided on: #131, carrying forward §2–6 of the former target architecture document
  (removed by #131; in git history before it) and superseding its feature rule

## Context

Three repos share one pipeline: fpl-ingest captures FPL's API into S3, fpl-warehouse
turns the captures into served tables, and fpl-intelligence reads those tables to
model and decide. Before the dbt migration the work was split differently. Ingest
flattened payloads into SQLite tables, the warehouse read SQLite and also called the
live API, and both the warehouse and intelligence computed rolling features over the
same tables, with opposite point-in-time conventions.

The target architecture document fixed the boundaries for the rebuild. Its rule that
every feature belongs to fpl-intelligence no longer matches how the work is split, and
is replaced here.

## Decision

- **fpl-ingest captures, and checks shape only.** It writes each payload to S3
  unmodified, and checks only that the response has the shape the source contract
  expects. It never flattens, models or knows about facts and dimensions.
- **Raw captures are immutable and append-only.** A capture is never rewritten, so
  the warehouse can always be rebuilt from them (ADR 0001 relies on this).
- **fpl-warehouse owns all structuring, from raw to served.** It reads raw captures
  and their records (run manifests, the backfill catalog) from S3, and the checked-in
  seeds. It makes no live API calls.
- **No layer reads past its neighbour.** fpl-intelligence reads only the served
  tables, never raw captures or staging (CLAUDE.md, "Served contract"). fpl-ingest
  never depends on what the warehouse builds.
- **A new source arrives the same way:** as raw captures written by an ingest repo,
  with its own staging model in the warehouse. Nothing downstream changes.
- **Features are split by kind.**
  - **The warehouse owns deterministic, stable, SQL-expressible features.** Each is
    as-of keyed and tested. A feature is promoted into the warehouse when a decision's
    evaluation cites it. `player_status_as_of` (#128) is an example.
  - **fpl-intelligence owns everything else:** fitted models (`p_play`, priors,
    forecasts), experiments, composites and decisions.

This supersedes the target architecture document's rule that features belong to
intelligence and that the warehouse builds no feature layer.

## Rejected

| Option | Why rejected |
|---|---|
| Ingest shapes payloads into tables (the pre-migration split) | Two places structured the same data and disagreed (`fpl_id` vs `player_id`). Captures would stop being replayable source data. |
| The warehouse calls the live API for fresh fields | Creates an undeclared runtime dependency on the API, and gives those fields no capture behind them. Freshness belongs to ingest's capture cadence. |
| Every feature in fpl-intelligence (target architecture §5) | Superseded. A stable, deterministic feature that a decision relies on belongs where it is tested on every build and served to every consumer, not reimplemented per experiment. |
| Fitted models or composites in the warehouse | They change with each experiment and are not deterministic SQL. They would make served data depend on modelling choices. |
| Recording Understat as a planned second source | Nothing for it exists in this repo. The general new-source rule covers it if it returns. |

## Consequences

- Rebuilding the warehouse needs only S3 and the repo, never the FPL API.
- A served feature carries the warehouse's guarantees: as-of keyed, tested on every
  build, and covered by the served contract and its version.
- Moving a feature from intelligence into the warehouse is a deliberate promotion,
  triggered by a decision's evaluation citing it, not by convenience.
