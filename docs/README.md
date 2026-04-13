# fpl-warehouse Documentation Guide

This page is the entry point for project documentation.

Conceptually, this repo sits in the warehouse and data-modeling layer between cleaned source-aligned inputs and downstream feature engineering or modeling.

## Read This First

Start with the document that matches your task.

1. Use [contracts/snapshot_contract.md](contracts/snapshot_contract.md) when defining or reviewing snapshot responsibilities, feature placement, join rules, naming, or PIT correctness for modeling snapshots.
2. Use [governance/warehouse_governance_spec.md](governance/warehouse_governance_spec.md) when you need naming rules, feature-tier policy, PIT validation, join safety, or lineage requirements.
3. Use [governance/validation_test_spec.md](governance/validation_test_spec.md) when you need required validation classes, layer coverage expectations, or PIT test requirements.
4. Use [system/build_transformation_spec.md](system/build_transformation_spec.md) when you need implementation-layer construction rules, transformation boundaries, or materialization responsibilities.
5. Use [system/data_lineage_map.md](system/data_lineage_map.md) when you need upstream origin tracing for warehouse tables or snapshot families.
6. Use [governance/data_freshness_policy.md](governance/data_freshness_policy.md) when you need refresh cadence, mutability rules, or reproducibility expectations.
7. Use [governance/change_versioning_policy.md](governance/change_versioning_policy.md) when you need breaking versus non-breaking change rules, deprecation handling, or document lifecycle guidance.
8. Use [history/snapshot_audit.md](history/snapshot_audit.md) when you need archived structural audit context or migration rationale.
9. For a broad warehouse table inventory or source-to-warehouse mapping, see the Data Lineage Map and snapshot contract.
10. Use [system/architecture.md](system/architecture.md) when you need build flow, package boundaries, orchestration, or runtime dependencies.
11. Use [design/README.md](design/README.md) only for historical design notes and migration context.

Core scope note:

1. the governed warehouse contract covers shared PIT-safe snapshot outputs
2. operational helper tables such as `fact_manager_squad` are outside that core contract unless explicitly promoted into governed scope

## Layer Position

Think about the end-to-end pipeline like this:

1. ingestion lands raw source data
2. staging normalizes source-aligned structures
3. warehouse modeling in this repo creates PIT-safe, business-ready outputs
4. downstream feature engineering combines or recomposes those outputs
5. modeling and decision systems consume downstream features

This documentation framework belongs to step 3.

## Document Ownership

Each document has a different responsibility.

### Snapshot Contract

File: [contracts/snapshot_contract.md](contracts/snapshot_contract.md)

Owns:

1. snapshot responsibilities
2. grain definitions
3. allowed and forbidden fields
4. join graph rules
5. time semantics for snapshots
6. logical snapshot schemas

Does not own:

1. low-level SQL
2. DDL details
3. build orchestration
4. full warehouse table inventory
5. cross-cutting naming policy

### Governance

File: [governance/warehouse_governance_spec.md](governance/warehouse_governance_spec.md)

Owns:

1. naming rules
2. feature-tier policy
3. allowed and forbidden transformations
4. PIT validation rules
5. join safety rules
6. lineage requirements
7. review criteria

Does not own:

1. snapshot-specific field ownership
2. final logical snapshot schemas
3. SQL or DDL details
4. minimum test coverage policy

### Validation And Test Spec

File: [governance/validation_test_spec.md](governance/validation_test_spec.md)

Owns:

1. required validation classes
2. minimum validation coverage by layer
3. timestamp-aware versus proxy PIT test expectations
4. required failure conditions
5. minimum validation expectations for new snapshots and feature families

Does not own:

1. snapshot semantics
2. admissibility policy
3. implementation construction rules

### Data Freshness And Mutability Policy

File: [governance/data_freshness_policy.md](governance/data_freshness_policy.md)

Owns:

1. refresh cadence guidance
2. latest-truth versus reproducibility expectations
3. mutable live-state handling rules
4. rebuild-versus-refresh operating policy

Does not own:

1. snapshot semantics
2. logical snapshot schemas
3. implementation construction details

### Build And Transformation Spec

File: [system/build_transformation_spec.md](system/build_transformation_spec.md)

Owns:

1. implementation layer responsibilities
2. approved transformation boundaries by layer
3. materialization sequence
4. construction rules for joins, windows, filtering, and PIT enforcement
5. snapshot implementation template

Does not own:

1. logical snapshot schemas
2. cross-cutting policy rules
3. validation coverage requirements

### Data Lineage Map

File: [system/data_lineage_map.md](system/data_lineage_map.md)

Owns:

1. source-system to warehouse-table mapping
2. major transformation paths from raw sources to snapshot families
3. investigation path for upstream drift
4. physical warehouse table inventory

Does not own:

1. snapshot semantics
2. admissibility policy
3. construction rules
4. validation requirements

Operational note:

1. this document may include optional operational tables such as `fact_manager_squad`
2. presence in the physical inventory does not mean the table is part of the governed snapshot contract

### Change And Versioning Policy

File: [governance/change_versioning_policy.md](governance/change_versioning_policy.md)

Owns:

1. breaking versus non-breaking change rules
2. version advancement rules
3. deprecation policy
4. lifecycle guidance for historical and audit documents

Does not own:

1. current contract content
2. current governance policy details
3. implementation design



### Archived Audit

File: [history/snapshot_audit.md](history/snapshot_audit.md)

Owns:

1. structural audit findings
2. migration rationale
3. correction history
4. decomposition and rename rationale

Does not own:

1. active snapshot schemas
2. active naming policy
3. enforceable warehouse rules

### Architecture

File: [system/architecture.md](system/architecture.md)

Owns:

1. system boundaries
2. execution flow
3. runtime orchestration diagrams
4. dependency diagrams

Does not own:

1. snapshot field semantics
2. source-of-truth naming rules
3. implementation construction sequence

### Historical Design Notes

File: [design/README.md](design/README.md)

Owns:

1. historical design rationale
2. migration context
3. superseded design notes

Does not own:

1. active snapshot schemas
2. active naming policy
3. implementation decisions

## Recommended Reading Paths

### For contract design

1. [contracts/snapshot_contract.md](contracts/snapshot_contract.md)
2. [governance/warehouse_governance_spec.md](governance/warehouse_governance_spec.md)
3. [governance/validation_test_spec.md](governance/validation_test_spec.md)
4. [governance/data_freshness_policy.md](governance/data_freshness_policy.md)
5. [governance/change_versioning_policy.md](governance/change_versioning_policy.md)
6. [system/data_lineage_map.md](system/data_lineage_map.md) and [contracts/snapshot_contract.md](contracts/snapshot_contract.md)
7. [system/architecture.md](system/architecture.md)

### For implementation work

1. [contracts/snapshot_contract.md](contracts/snapshot_contract.md)
2. [governance/warehouse_governance_spec.md](governance/warehouse_governance_spec.md)
3. [governance/validation_test_spec.md](governance/validation_test_spec.md)
4. [governance/data_freshness_policy.md](governance/data_freshness_policy.md)
5. [system/build_transformation_spec.md](system/build_transformation_spec.md)
6. [system/data_lineage_map.md](system/data_lineage_map.md)
7. [system/architecture.md](system/architecture.md)
8. relevant files in `src/fpl_warehouse/builders/`, `src/fpl_warehouse/warehouse/`, and `src/models/`

### For review work

1. [contracts/snapshot_contract.md](contracts/snapshot_contract.md)
2. [governance/warehouse_governance_spec.md](governance/warehouse_governance_spec.md)
3. [governance/validation_test_spec.md](governance/validation_test_spec.md)
4. [governance/data_freshness_policy.md](governance/data_freshness_policy.md)
5. [governance/change_versioning_policy.md](governance/change_versioning_policy.md)
6. [system/data_lineage_map.md](system/data_lineage_map.md) and [contracts/snapshot_contract.md](contracts/snapshot_contract.md)
7. [system/architecture.md](system/architecture.md)

## Working Rules

1. Change the contract before changing implementation.
2. Check governance before changing implementation.
3. Keep snapshot semantics and warehouse inventory/lineage documentation separate.
4. Keep time boundaries explicit: `as_of_gw` is the historical boundary and `target_gw` is the downstream next-GW label, not a persisted warehouse field.
5. Prefer updating the owning document instead of duplicating the same rule in multiple places.
