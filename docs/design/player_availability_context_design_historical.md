# Player Availability Context Design Note (Historical)

## Status

Historical design note only.

This file is not the active warehouse contract.

## Current source of truth

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md)

## Original intent

This note proposed separating player availability and playing-time context into a reusable warehouse snapshot.

That high-level direction remains valid.

## What is outdated

1. The column names in this note predate the current naming policy.
2. This note predates the contract and governance split.
3. The note uses earlier field names such as `last_gw_minutes`, `last_gw_started`, `minutes_last_3gws`, and `minutes_volatility_5gws`.
4. The active contract now uses explicit naming and Tier 1 and Tier 2-only warehouse scope.

## Use this note for

1. historical rationale
2. migration context
3. understanding why availability was separated from performance and fixture context

## Do not use this note for

1. current schema definitions
2. current naming rules
3. implementation decisions without checking the active contract
