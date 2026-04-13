# Build And Transformation Spec

This document defines how approved warehouse contracts are implemented.

It specifies layer responsibilities, transformation boundaries, canonical materialization sequence, and construction rules.

It does not redefine snapshot semantics, admissibility policy, or validation policy.

## Primary role

This document answers:

1. how warehouse outputs are constructed from source data
2. which layer owns which transformation step
3. where joins, windows, filtering, and PIT enforcement happen
4. how approved contract fields map into implementation layers

## Does not own

This document does not define:

1. snapshot field ownership or logical schemas
2. naming standards
3. Tier 1, Tier 2, or Tier 3 admissibility policy
4. validation requirements or test coverage policy
5. contract change or versioning rules

Use these documents for those responsibilities:

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md)
3. [../governance/validation_test_spec.md](../governance/validation_test_spec.md)

## Implementation layers

The warehouse implementation uses the following layers.

### Source layer

Owns:

1. external reads from upstream source databases or APIs
2. source-specific identifiers and raw source semantics
3. source extraction only

Does not own:

1. warehouse feature derivation
2. contract interpretation
3. cross-source semantic correction beyond explicitly approved mappings

### Integration layer

Owns:

1. cross-source entity matching
2. source name resolution
3. bridge logic needed before warehouse construction

Does not own:

1. snapshot feature engineering
2. warehouse contract semantics

### Builder layer

Owns:

1. orchestration of table builds and snapshot materialization
2. ordered execution of schema, facts, views, and snapshots
3. non-SQL support logic that cannot reasonably live in model SQL

Does not own:

1. redefining approved field semantics
2. hidden feature logic that should live in model SQL

### Intermediate SQL layer

Owns:

1. PIT-safe spines
2. normalized row-level joins
3. source reshaping needed before aggregation
4. explicit timestamp or event cutoff enforcement when required

Does not own:

1. final snapshot projection
2. composite downstream features

### Feature SQL layer

Owns:

1. explicit windowed aggregation
2. explicit deterministic normalization such as totals, averages, rates, standard deviations, deltas, and per-90 values
3. decomposition of approved warehouse outputs into Tier 1 and Tier 2 implementations

Does not own:

1. hidden thresholds
2. hidden filters
3. composite scoring logic
4. final contract projection order

### Fact snapshot SQL layer

Owns:

1. final projection into contract-aligned snapshot columns
2. contract-aligned naming and column ordering
3. no-op projection from feature views into the materialized table shape

Does not own:

1. new feature derivation
2. semantic reinterpretation of feature columns

## Construction rules

### Rule 1. Contract before implementation

Implementation must follow the approved logical contract.

If implementation and contract differ, the contract wins unless the contract is explicitly revised.

### Rule 2. Keep semantic logic in SQL close to the field it defines

1. intermediate views prepare PIT-safe input rows
2. feature views define deterministic warehouse features
3. fact snapshot SQL only projects approved fields

Builder code should orchestrate, not silently redefine semantics that belong in SQL.

### Rule 3. Keep PIT enforcement at the earliest reliable boundary

1. use timestamp cutoffs where reliable source timestamps exist
2. otherwise use the approved event or finished-fixture proxy boundary
3. do not postpone PIT enforcement to downstream layers if it can be enforced earlier

### Rule 4. Make windows explicit in implementation

All historical windows must be explicit in:

1. ordering logic
2. inclusion boundaries
3. partition keys
4. output naming

### Rule 5. No implicit source filtering

Any filter that changes meaning must be explicit in either:

1. the contract field definition
2. the feature name
3. the approved implementation notes for the snapshot

## Approved materialization sequence

The warehouse should be built in this order.

1. create schema objects
2. build dimensions
3. build base facts
4. create shared analytical views if required
5. materialize snapshot intermediates and feature views
6. materialize final snapshot tables
7. run contract and validation checks

Use [architecture.md](architecture.md) for runtime system flow and orchestration diagrams.

## Snapshot construction checklist

Each snapshot implementation should document:

1. source tables used
2. approved join path
3. PIT boundary type: timestamp or proxy
4. window definitions and ordering logic
5. required filters
6. intermediate views used
7. feature view used
8. final fact projection used

## Snapshot implementation template

Use this template when adding or revising a snapshot.

### Snapshot

Name:

### Sources

1. source table
2. source table

### Join path

1. join step
2. join step

### PIT boundary

1. timestamp cutoff or approved proxy boundary

### Windows

1. explicit window definition
2. explicit ordering rule

### Filters

1. finished fixture only, if applicable
2. event cutoff, if applicable

### SQL ownership

1. intermediate view name
2. feature view name
3. fact snapshot name

## Current gaps

This spec is intentionally lean. If future implementation drift appears, expand this document with per-snapshot construction notes rather than moving semantic rules out of the contract or governance documents.
