# Player Performance Context Design Note (Historical)

## Status

Historical design note only.

This file is not the active warehouse contract.

## Current source of truth

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md)

## Original intent

This note proposed a reusable player performance snapshot separated from availability and market signals.

That separation remains valid.

## What is outdated

1. The note predates the Tier 1 and Tier 2-only warehouse policy.
2. It contains legacy names such as `xgi_per90`, `bonus_per_app`, `cs_pct`, and `pts_last_3`.
3. It references role signals and similar concepts that are no longer warehouse outputs under the active governance rules.
4. The active contract now excludes retained Tier 3 composites from warehouse scope.

## Use this note for

1. historical rationale
2. migration context
3. understanding why player performance is a distinct warehouse domain

## Do not use this note for

1. current performance schema definitions
2. current naming policy
3. current warehouse scope decisions
