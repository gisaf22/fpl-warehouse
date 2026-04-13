# Team Fixture Context Design Note (Historical)

## Status

Historical design note only.

This file is not the active warehouse contract.

## Current source of truth

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md)

## Original intent

This note proposed a team-grain fixture context snapshot to avoid duplicating team-level data across player rows.

That grain decision remains valid.

## What is outdated

1. The note mixes fixture context with team and opponent performance context in one snapshot.
2. The active contract now separates pure fixture context from team performance context.
3. The note uses legacy field names such as `has_home_fixture`, `opp_team_fpl_id`, `team_xg_last_3`, and `opp_vulnerability_last_3`.
4. The note includes heuristic framing that is outside the current warehouse scope discipline.

## Use this note for

1. historical rationale
2. migration context
3. understanding why team-grain context exists at all

## Do not use this note for

1. current fixture schema definitions
2. current team performance context schema definitions
3. current field ownership across snapshots
