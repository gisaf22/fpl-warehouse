# Player Market Context Design Note (Historical)

## Status

Historical design note only.

This file is not the active warehouse contract.

## Current source of truth

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md)

## Original intent

This note proposed separating player market state from player performance and availability.

That separation remains valid.

## What is outdated

1. The note uses legacy names such as `transfer_delta`, `price_velocity_3gw`, and `ownership_velocity_3gw`.
2. The active contract now uses normalized names such as `transfers_net`, `price_delta_last_3gws`, and `ownership_delta_last_3gws`.
3. The note predates the explicit contract, governance, and implementation layer split.

## Use this note for

1. historical rationale
2. migration context
3. understanding why market signals are a distinct warehouse domain

## Do not use this note for

1. current field names
2. current implementation decisions
3. validation rules or PIT policy beyond what the active governance doc states
