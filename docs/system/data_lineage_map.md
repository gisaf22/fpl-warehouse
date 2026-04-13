# Data Lineage Map

This document defines where warehouse outputs come from and which persisted warehouse tables exist.

It maps source systems, source tables, and major transformation paths into warehouse tables and modeling snapshots.

It does not define snapshot semantics, admissibility policy, implementation rules, or validation requirements.

## Primary role

This document answers:

1. where each warehouse table originates
2. which upstream systems feed each snapshot family
3. which intermediate paths connect raw sources to snapshot outputs
4. what persisted warehouse tables are part of the physical warehouse inventory
5. where to investigate upstream drift when a warehouse field changes unexpectedly

## Does not own

This document does not define:

1. what a snapshot field means
2. whether a field is allowed in warehouse scope
3. how joins and windows must be implemented
4. how validation is enforced

Use these documents for those responsibilities:

1. [../contracts/snapshot_contract.md](../contracts/snapshot_contract.md)
2. [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md)
3. [build_transformation_spec.md](build_transformation_spec.md)
4. [../governance/validation_test_spec.md](../governance/validation_test_spec.md)

## Source systems

### FPL source

Database:

1. `fpl.db`

Primary source tables used in warehouse construction:

1. `teams`
2. `players`
3. `gameweeks`
4. `fixtures`
5. `events`

### Understat source

Database:

1. `understat.db`

Primary source tables used in warehouse construction:

1. `match_info`
2. `rosters`
3. `shots`

### Live API source

Used only for warehouse refresh paths that require live manager or bootstrap state.

Primary source endpoints used in warehouse construction:

1. bootstrap-static
2. manager entry
3. manager history
4. manager picks

## Physical warehouse inventory

Persisted warehouse tables currently owned by this repo:

1. `dim_teams`
2. `dim_players`
3. `dim_gameweeks`
4. `fact_player_gw`
5. `fact_shots`
6. `fact_fixtures`
7. `fact_match_stats`
8. `fact_manager_squad`
9. `fact_player_availability_snapshot`
10. `fact_player_performance_snapshot`
11. `fact_player_market_snapshot`
12. `fact_team_fixture_snapshot`
13. `fact_team_performance_context_snapshot`

Use the snapshot contract for the logical meaning and allowed contents of snapshot outputs. Use this document for physical inventory, source provenance, and major transformation paths.

Operational note:

1. `fact_manager_squad` is an optional user-specific operational table.
2. It is not part of the governed warehouse snapshot contract.
3. It may be removed in the future if downstream consumers rely directly on live API reads instead of persisted manager-state storage.

## Warehouse lineage by table family

### Dimensions

#### `dim_teams`

Sources:

1. FPL `teams`
2. approved FPL to Understat name mapping

Transformation path:

1. source extraction
2. team-name normalization and cross-source name mapping
3. persisted team dimension

#### `dim_players`

Sources:

1. FPL `players`
2. Understat `rosters`
3. approved manual overrides and matching rules

Transformation path:

1. source extraction
2. cross-source player matching
3. team resolution through `dim_teams`
4. persisted player dimension

#### `dim_gameweeks`

Sources:

1. FPL `events`

Transformation path:

1. source extraction
2. persisted gameweek dimension

### Base facts

#### `fact_player_gw`

Sources:

1. FPL `gameweeks`
2. Understat `rosters` for enrichment fields
3. fixture bridge derived from FPL fixtures and Understat match metadata

Transformation path:

1. FPL player-GW extraction
2. persisted player-GW fact
3. Understat enrichment through bridge to GW round

#### `fact_shots`

Sources:

1. Understat `shots`

Transformation path:

1. source extraction
2. normalized shot fact projection

#### `fact_fixtures`

Sources:

1. FPL `fixtures`

Transformation path:

1. source extraction
2. normalized fixture fact projection

#### `fact_match_stats`

Sources:

1. Understat `match_info`
2. fixture bridge derived from FPL fixtures and team/date matching

Transformation path:

1. source extraction
2. team-name resolution to FPL identifiers
3. fixture bridge join
4. normalized match stats fact projection

#### `fact_manager_squad`

Classification:

1. optional operational table
2. user-specific, not part of the core governed snapshot layer

Sources:

1. FPL live manager endpoints
2. warehouse player facts for purchase-price lookup

Transformation path:

1. live API fetch
2. manager context resolution
3. warehouse insertion at manager and GW grain

## Modeling snapshot lineage

### `fact_player_availability_snapshot`

Primary upstream tables:

1. `fact_player_gw`
2. `fact_fixtures`
3. `dim_players`
4. `dim_teams`

Primary transformation path:

1. `int_player_gw_base`
2. `fct_player_availability_features`
3. `fact_player_availability_snapshot`

### `fact_player_performance_snapshot`

Primary upstream tables:

1. `fact_player_gw`
2. `fact_fixtures`
3. `dim_players`
4. `dim_teams`

Primary transformation path:

1. `int_player_gw_base`
2. `fct_player_performance_features`
3. `fact_player_performance_snapshot`

### `fact_player_market_snapshot`

Primary upstream tables:

1. `fact_player_gw`
2. `fact_fixtures`
3. `dim_players`
4. `dim_teams`

Primary transformation path:

1. `int_player_gw_base`
2. `fct_player_market_features`
3. `fact_player_market_snapshot`

### `fact_team_fixture_snapshot`

Primary upstream tables:

1. `fact_fixtures`
2. `dim_teams`

Primary transformation path:

1. team and GW spine construction
2. `fct_team_fixture_features`
3. `fact_team_fixture_snapshot`

### `fact_team_performance_context_snapshot`

Primary upstream tables:

1. `fact_fixtures`
2. `fact_match_stats`
3. `dim_teams`

Primary transformation path:

1. `int_team_fixture_base`
2. `fct_team_performance_context_features`
3. `fact_team_performance_context_snapshot`

## Investigation guide

When a warehouse field drifts, inspect in this order:

1. source record correctness
2. bridge or entity resolution logic
3. intermediate view row inclusion
4. feature view aggregation logic
5. final fact projection and naming
