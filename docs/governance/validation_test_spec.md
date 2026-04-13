# Validation And Test Spec

This document defines how warehouse correctness is enforced.

It specifies required validation classes, minimum coverage expectations, and failure conditions for warehouse implementations.

It does not redefine snapshot semantics or general admissibility policy.

## Primary role

This document answers:

1. what must be tested
2. where tests must exist
3. what must fail when implementation drifts
4. how PIT, structural, and semantic rules are operationalized

## Does not own

This document does not define:

1. snapshot field meaning or schema ownership
2. transformation admissibility policy
3. implementation layer responsibilities
4. source lineage inventory

Use these documents for those responsibilities:

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [warehouse_governance_spec.md](warehouse_governance_spec.md)
3. [../system/build_transformation_spec.md](../system/build_transformation_spec.md)

## Validation classes

Every warehouse change should be evaluated across the following classes.

### Structural validation

Checks:

1. required columns exist
2. primary key columns are not null
3. declared grain is unique
4. projected snapshot schema matches the approved contract

### Temporal validation

Checks:

1. no source contribution beyond `as_of_gw`
2. no realized target-GW outcomes used in warehouse features
3. explicit windows are bounded correctly
4. timestamp-aware PIT enforcement is tested where timestamped source fields are used
5. approved proxy PIT enforcement is tested where timestamps are unavailable or untrusted

### Semantic validation

Checks:

1. snapshot does not contain out-of-domain fields
2. fields remain in their owning snapshot
3. retained Tier 3 outputs do not appear in warehouse schemas
4. DGW and BGW behavior matches the approved contract where applicable

### Behavioral validation

Checks:

1. representative known-value cases produce expected outputs
2. edge cases such as BGW, DGW, zero-history, or sparse-history rows behave as approved
3. nullability behavior matches the contract and implementation notes

## Minimum layer coverage

For any snapshot or feature family with nontrivial logic, validation should cover all relevant layers.

### Intermediate layer

Must test:

1. grain
2. key non-nullness
3. PIT cutoff behavior
4. row inclusion boundaries

### Feature layer

Must test:

1. window behavior
2. aggregation correctness
3. normalization correctness
4. admissible null behavior
5. domain-specific invariants

### Fact snapshot layer

Must test:

1. final schema alignment with contract
2. grain uniqueness
3. key non-nullness
4. final projection behavior for critical fields

## Timestamp-aware versus proxy PIT coverage

### Timestamp-aware PIT tests are required when

1. logic uses fixture kickoff times
2. logic uses match datetimes
3. logic uses timestamp ordering or timestamp windows

These tests must prove:

1. contributing timestamps do not exceed the approved cutoff implied by `as_of_gw`
2. post-cutoff source records do not contribute to the result

### Proxy PIT tests are required when

1. logic relies on event or round boundaries only
2. no reliable timestamp exists
3. an approved event-based proxy is the intended cutoff mechanism

These tests must prove:

1. no row beyond the approved event boundary contributes
2. no later event leaks into a prior `as_of_gw`

## Required validation artifacts

Preferred validation surfaces are:

1. focused behavioral tests in Python
2. singular SQL tests for intermediate, feature, and fact layers
3. contract validation checks for table-level guarantees

Use singular SQL tests when a condition is best expressed as:

1. a set-based invariant
2. a row-level violation search
3. a schema or grain constraint

## Failure conditions

At minimum, validation must fail when any of the following occurs:

1. duplicate rows at declared grain
2. missing required columns
3. null primary-key columns
4. post-cutoff data contribution
5. target-GW realized outcome leakage
6. DGW or BGW fields violate contract behavior
7. cross-domain field leakage between snapshots
8. final fact schema diverges from the approved contract

## Minimum validation for a new snapshot

Before a new snapshot is considered implementation-complete, it should have:

1. at least one behavioral test using controlled fixture data
2. intermediate-layer SQL validation where an intermediate view exists
3. feature-layer SQL validation where a feature view exists
4. fact snapshot SQL validation for grain and keys
5. PIT validation using either timestamp-aware or proxy-aware checks, depending on the source boundary type

## Minimum validation for a new feature family

Before a new feature family is accepted, validation should prove:

1. the window is correct
2. the denominator or normalization is correct, if applicable
3. null behavior is deliberate
4. the feature does not violate its snapshot domain
5. PIT behavior is preserved

## Review rule

If a feature or snapshot cannot be validated in one of the required classes above, it is not review-complete.

## Current note

This document defines minimum enforcement expectations. It should remain concise and policy-like. Do not turn it into a test inventory or a dump of individual test cases.