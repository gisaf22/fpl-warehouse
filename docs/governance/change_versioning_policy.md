# Change And Versioning Policy

This document defines how warehouse contracts and governing documents evolve.

It specifies what counts as a breaking change, how versions should advance, and how deprecated or historical documents should be handled.

It does not define snapshot semantics or implementation details.

## Primary role

This document answers:

1. how to change warehouse contracts safely
2. what counts as breaking versus non-breaking
3. when version numbers should change
4. when a historical or audit document can be archived or deleted

## Does not own

This document does not define:

1. current snapshot schemas
2. admissibility rules
3. implementation construction rules
4. validation requirements

Use these documents for those responsibilities:

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [warehouse_governance_spec.md](warehouse_governance_spec.md)
3. [../system/build_transformation_spec.md](../system/build_transformation_spec.md)
4. [validation_test_spec.md](validation_test_spec.md)
5. [data_freshness_policy.md](data_freshness_policy.md)

## Versioned documents

The following documents are version-governed:

1. snapshot contract
2. governance spec
3. validation and test spec
4. build and transformation spec
5. change and versioning policy

Supporting documents such as lineage maps, architecture notes, and planning notes may remain unversioned unless they become externally consumed interfaces.

## Change classes

### Breaking change

A change is breaking if it does any of the following:

1. removes a contract field
2. renames a contract field
3. changes the meaning, boundary, or computation semantics of an existing field
4. changes declared snapshot grain
5. changes allowed join assumptions in a way that can alter downstream results

### Non-breaking change

A change is non-breaking if it does any of the following without altering existing semantics:

1. adds a new optional field
2. clarifies wording without changing meaning
3. strengthens validation or test coverage without changing output semantics
4. adds supporting documentation or lineage notes

## Version advancement

Use simple semantic advancement for governed documents.

### Major version

Increment the major version when a breaking change is introduced.

Examples:

1. field rename
2. snapshot grain change
3. semantic reinterpretation of an existing feature

### Minor version

Increment the minor version when a non-breaking functional addition is introduced.

Examples:

1. new field added without changing existing fields
2. new governed validation requirement
3. new implementation-layer construction rule that preserves existing semantics

### Patch version

Increment the patch version for editorial or clarifying changes that do not change contract or policy meaning.

Examples:

1. wording clarification
2. typo correction
3. link or reference cleanup

## Change procedure

Apply changes in this order.

1. revise the owning spec or contract first
2. update dependent specs if boundaries or responsibilities changed
3. update implementation
4. update validation where required
5. update historical or audit documents only if they still need to explain the transition

## Deprecation policy

When a field or document is being phased out:

1. mark it as deprecated in the owning document
2. state the replacement explicitly
3. define whether the deprecation is temporary or permanent
4. remove it only after downstream dependency risk is understood

## Historical and audit documents

Historical documents should not remain co-equal sources of truth.

### Keep a historical document when

1. it explains a recent migration still relevant to active implementation
2. it preserves rationale for a change likely to be revisited
3. it records a correction sequence not yet stabilized in practice

### Archive a historical document when

1. the active contract and validation suite are stable
2. the historical document no longer guides implementation decisions
3. the rationale remains useful but should not appear as active guidance

### Delete a historical document when

1. it no longer contains unique information
2. the replacement source of truth is stable
3. the same information is already preserved elsewhere with less ambiguity

## Current guidance for `history/snapshot_audit.md`

`history/snapshot_audit.md` should remain historical only.

It may be archived or deleted once:

1. the warehouse contract is considered stable
2. the implementation is aligned and validated
3. the document no longer contributes unique migration rationale

## Current guidance for pointer documents

Top-level pointer documents that exist only to redirect readers to canonical locations should be treated as temporary migration aids.

These documents should be removed once:

1. internal references have been updated to the canonical locations
2. external workflow dependence on the old paths is no longer expected
3. removing them will reduce ambiguity rather than create navigation risk

## Current documentation follow-up

One planned documentation addition remains outside the current core framework.

1. Write a downstream data-consumption document covering `target_gw` derivation, consumption-time labeling, and downstream feature-assembly assumptions.

## Review rule

If a proposed change cannot be classified clearly as breaking or non-breaking, treat it as breaking until clarified.
