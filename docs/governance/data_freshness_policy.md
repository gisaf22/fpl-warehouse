# Data Freshness And Mutability Policy

This document defines how mutable source data is handled operationally.

It specifies refresh cadence, rebuild behavior, and the boundary between historical warehouse outputs and live current-state fields.

It does not redefine snapshot semantics, logical schemas, or implementation-layer construction rules.

## Primary role

This document answers:

1. how often source data is refreshed
2. which warehouse paths are rebuilt from current source state
3. which fields are treated as mutable live state
4. what the warehouse guarantees about PIT safety versus reproducibility

## Operating model

The current warehouse uses a latest-reconstructed-truth model.

Rules:

1. source data is refreshed in full on each scheduled pipeline run
2. the warehouse is rebuilt from current ingested source state rather than incrementally patched
3. snapshots remain PIT-safe relative to `as_of_gw`
4. historical outputs are not versioned by ingest batch or source revision
5. historical outputs may change across runs if upstream data is corrected or backfilled

Current recommended cadence:

1. refresh sources twice daily
2. rebuild warehouse facts and snapshots after each refresh

## Source mutability classes

### Stable event data

Usually stable once the relevant event has completed.

Examples:

1. finished fixtures
2. match-level stats
3. player minutes and realized outputs

### Correctable historical data

Historical rows may still change if an upstream source corrects or backfills data after the event.

Examples:

1. corrected player stats
2. corrected fixture metadata
3. corrected Understat aggregates

### Live mutable state

Continuously changing source state that is useful operationally but should not overwrite historical warehouse facts in place.

Examples:

1. `chance_of_playing_next_round`
2. `news`
3. `news_updated`
4. live market state such as current price or transfer pulse

## Warehouse guarantees

The warehouse guarantees:

1. point-in-time correctness relative to `as_of_gw`
2. deterministic outputs given an identical set of ingested source data
3. rebuild consistency when the full warehouse is recomputed from refreshed sources

The warehouse does not currently guarantee:

1. reproducibility against prior runs
2. preservation of earlier upstream errors once corrected upstream
3. source-versioned historical reconstruction

## Time model clarification

The system distinguishes between:

1. event time: when the underlying real-world event occurred
2. ingestion time: when the data was retrieved from the source

All PIT guarantees are defined strictly in terms of event time, not ingestion time.

## Temporal cutoff rule

All warehouse computations must enforce a strict temporal cutoff at `as_of_gw`.

Rules:

1. only source records with event timestamps less than or equal to the approved cutoff for `as_of_gw` may be included
2. late-arriving data must still satisfy the same event-time constraint to be eligible for inclusion
3. ingestion time must not replace the governed event-time cutoff for PIT inclusion decisions

## Refresh and rebuild rules

### Historical warehouse path

Historical warehouse facts and snapshots are rebuild-owned.

Rules:

1. refresh upstream sources first
2. rebuild warehouse tables and snapshots from refreshed source state
3. do not patch historical warehouse fact rows in place from live API responses

### Live mutable fields

Live mutable fields such as `chance_of_playing_next_round`, `news`, and `news_updated` are
owned by the FPL ingestion layer. The ingestion layer is responsible for keeping them current
in `fpl.db`. The warehouse reads them from `fpl.db` during the standard build, the same as
every other source field.

Rules:

1. the warehouse must not make live API calls. it reads `fpl.db` and `understat.db` only.
2. live mutable fields must not be updated inside the warehouse by calling an external API.
3. freshness of live mutable fields is governed by the FPL ingestion cadence, not by a
   warehouse refresh path.
4. no warehouse table may mix fields anchored at `as_of_gw` with fields reflecting
   post-`as_of_gw` live state.

Note: the warehouse currently violates rule 1 and 2 via `refresh_player_availability` in
`builders/snapshots.py` and the `sources/` package. This is tracked as architectural debt
in `docs/history/sources_refresh_debt.md`.

## Current implementation guidance

For the current system:

1. run full source refresh and warehouse rebuild twice daily
2. treat market and availability values in snapshots as functions of the latest ingested source state that is valid at or before `as_of_gw`
3. keep live current-state refreshes separate from historical market anchors

## Future evolution

If stronger reproducibility is needed later, add one or more of the following:

1. `ingested_at` on source-aligned tables
2. ingest batch identifiers
3. source-version snapshots
4. dedicated current-state tables for live mutable domains
