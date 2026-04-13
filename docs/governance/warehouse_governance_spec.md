# Warehouse Governance Spec v1.0.0

## Purpose

This document defines the governance layer for the warehouse.

It specifies the cross-cutting rules that constrain the contract layer and the implementation layer.

It does not define snapshot semantics directly, and it does not define SQL or DDL.

## Layer Boundaries

The warehouse uses three layers.

### Contract layer

Owns:

1. snapshot responsibilities
2. grain definitions
3. allowed and forbidden fields
4. logical feature schemas
5. join graph definitions
6. time semantics for snapshot outputs

Primary document:

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)

### Governance layer

Owns:

1. naming standards
2. allowed feature tiers
3. allowed transformation types
4. PIT validation rules
5. join safety rules
6. lineage requirements
7. review and audit criteria

Primary document:

1. [warehouse_governance_spec.md](warehouse_governance_spec.md)

### Implementation layer

Owns:

1. SQL
2. DDL
3. builders and materialization logic
4. implementation tests

Primary locations:

1. `src/fpl_warehouse/warehouse/`
2. `src/fpl_warehouse/builders/`
3. `src/models/`
4. `tests/`

## Governing Principles

1. The warehouse is a deterministic, time-anchored truth layer.
2. The warehouse is not a modeling or scoring layer.
3. Warehouse outputs must be semantically orthogonal.
4. All warehouse outputs must be point-in-time safe at `as_of_gw`.
5. Warehouse design must not use usefulness reasoning.

## Feature Tier Policy

Allowed in warehouse scope:

1. Tier 1 atomic signals
2. Tier 2 explicit windowed aggregates

Forbidden in warehouse scope:

1. Tier 3 compositional signals
2. heuristics
3. latent constructs
4. usefulness-driven features
5. hidden thresholds and hidden denominators

If a requested feature is composite:

1. decompose it into Tier 1 and Tier 2 fields for warehouse scope
2. or reject it as downstream-only

## Warehouse modeling boundary

This repo builds warehouse-modeled snapshots, not downstream feature-engineering outputs.

Rules:

1. `int_` layers may prepare PIT-safe input rows and reusable join-ready spines
2. `fct_` layers may derive only Tier 1 and Tier 2 warehouse-approved features
3. `fact_` layers may only project approved warehouse features into final snapshot tables
4. Tier 3 compositional features, model heuristics, feature selection logic, and prediction-oriented recomposition belong downstream of this repo

## Naming Rules

Preferred pattern:

`<metric>_<representation>_<window>`

Rules:

1. All non-state historical features must encode the window in the name.
2. Window naming must use only explicit forms such as `last_gw`, `last_3gws`, `last_5gws`, `last_10gws`, or `last_3_apps`.
3. Binary indicators must end in `_flag`.
4. Counts should end in `_count` unless the domain term is inherently count-like.
5. Totals, averages, rates, standard deviations, per-90 values, and deltas must be named explicitly.

## Window Type Classification

Every windowed feature has a governed window type and alignment class.

Classification fields:

1. `window_type`: `calendar_gw` or `event_app`
2. `alignment`: `global` or `entity_local`

Definitions:

### `calendar_gw`

1. Uses fixed intervals based on gameweek index.
2. Includes non-events and non-participation inside the gameweek window.
3. Is globally aligned across entities at the same `as_of_gw`.
4. Must use suffix forms such as `last_gw`, `last_3gws`, `last_5gws`, or `last_10gws`.

### `event_app`

1. Uses an entity-specific appearance sequence.
2. Excludes non-participation gameweeks from the event sequence.
3. Is entity-local rather than globally aligned.
4. Must use suffix forms such as `last_3_apps`.

Hard rules:

1. Window type must be encoded in the feature name and must not be inferred from prose.
2. No implicit conversion between `calendar_gw` and `event_app` windows is allowed.
3. No feature may be renamed from an appearance window to a gameweek window, or the reverse, without changing the underlying computation semantics.
4. Mixed window types must not be silently combined inside the same derived feature family.
5. Cross-entity joins, alignment, and grouping must rely on `as_of_gw` and globally aligned keys, not on appearance-window sequences.
6. `event_app` features are restricted to entity-local interpretation and must not be treated as join keys, alignment mechanisms, or time anchors.
7. `event_app` features are descriptive entity-level features only.

## Allowed Transformation Types

Allowed:

1. pass-through from source-aligned fields
2. deterministic joins on approved keys
3. explicit windowed aggregation
4. explicit normalization such as per-90, rate, avg, std, total, or delta
5. relocation of a field to the correct snapshot during contract correction
6. decomposition of composite requests into Tier 1 and Tier 2 outputs

Forbidden:

1. hidden aggregation logic
2. hidden thresholds
3. hidden denominator logic
4. composite scoring fields in warehouse outputs
5. business or model reasoning embedded in SQL comments or warehouse logic
6. implicit Tier 2 filters such as appearance-only or start-only logic unless the filter is encoded in the feature name

## PIT Rules

1. `as_of_gw` is the closed historical boundary.
2. `target_gw` is always `as_of_gw + 1` and is a label, not the historical source boundary.
3. Historical windows must end at `as_of_gw`.
4. No warehouse feature may depend on realized outcomes after `as_of_gw`.
5. `target_gw` may be used for schedule definition only, never for realized target-GW outcomes.
6. When a source exposes a reliable event or observation timestamp, PIT validation must prove that the source timestamp is at or before the cutoff implied by `as_of_gw`.
7. When a source does not expose a reliable timestamp, PIT validation must enforce an equivalent source-aligned proxy boundary, such as finished fixture kickoff or `round <= as_of_gw`.
8. PIT safety is defined against event-valid information available by the row cutoff. Historical reproducibility against later source corrections or backfills requires separate source-version or ingest-version controls.

### Timestamp-aware PIT enforcement

Any warehouse logic that uses timestamp-based source fields must include timestamp-aware PIT validation in addition to gameweek-based boundary checks.

Rules:

1. The maximum source timestamp contributing to a row must be less than or equal to the approved cutoff implied by `as_of_gw`.
2. No source record with a timestamp after that cutoff may contribute to the result.

Testing expectations:

1. Assert that contributing timestamps fall within the valid PIT boundary for each `as_of_gw`.
2. Fail if any post-cutoff timestamp contributes to feature computation.
3. Keep these checks alongside the relevant snapshot or intermediate validation tests.

Scope:

1. logic using fixture kickoff times
2. logic using match datetimes
3. logic using timestamp-ordered historical windows

Limitation:

1. These checks validate event-time PIT safety only. They do not by themselves guarantee reproducibility against later source corrections, late-arriving records, or backfills unless separate source-version or ingest-version controls exist.

## Join Safety Rules

1. Every cross-snapshot join must include `as_of_gw`.
2. Player-grain joins use `(as_of_gw, fpl_id)`.
3. Team-grain joins use `(as_of_gw, team_fpl_id)`.
4. Cross-grain joins are allowed only through declared snapshot keys.
5. Current-state dimensions must not override snapshot-era keys when a snapshot join exists.
6. Direct player-to-opponent joins are forbidden without team mediation.

## Lineage Requirements

Every warehouse feature must be traceable to:

1. source table or source tables
2. transformation type
3. governing time boundary
4. target snapshot

If a feature cannot be traced, it is not implementation-ready.

## Validation Requirements

This section defines validation policy only.

Use [validation_test_spec.md](validation_test_spec.md) for operational coverage expectations, required test surfaces, and minimum enforcement patterns.

Structural validation:

1. no null values in primary-key columns
2. no duplicate rows at declared grain
3. feature names conform to governance naming rules

Temporal validation:

1. no source contribution from beyond `as_of_gw`
2. no target-GW realized outcomes in warehouse features
3. all windows are explicit and auditable
4. use source timestamps for PIT validation when available, otherwise require an approved proxy boundary
5. distinguish event-time PIT safety from source-revision reproducibility

Semantic validation:

1. no cross-domain overlap between snapshots
2. no retained Tier 3 fields in warehouse schemas
3. all fields have a single owning snapshot

## Review Criteria

A warehouse change is acceptable only if:

1. the contract layer remains semantically clear
2. the governance rules are satisfied
3. the implementation does not introduce new semantics
4. the resulting outputs remain PIT-safe and orthogonal

## Change Order

Every warehouse change should follow this order.

1. update contract if semantics change
2. verify governance compliance
3. update implementation
4. validate tests and review findings
