# Warehouse Snapshot Contract

Version: 1.0.0

## Scope

This contract defines the warehouse outputs consumed by downstream feature engineering and modeling for prediction at `target_gw = as_of_gw + 1`.

Cross-cutting rules such as naming policy, feature-tier policy, PIT validation rules, join safety rules, and lineage requirements are governed by [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md).

Covered snapshots:

1. `fact_player_availability_snapshot`
2. `fact_player_performance_snapshot`
3. `fact_team_fixture_snapshot`
4. `fact_player_market_snapshot`
5. `fact_team_performance_context_snapshot`

This contract applies only to the warehouse layer. It does not define model features, scoring logic, or decision policies.

## Non-goals

The warehouse contract does not:

1. Compute expected points.
2. Join snapshots into one wide table.
3. Add model-specific heuristics.
4. Optimize feature sets for predictive performance.
5. Encode future outcomes from `target_gw` or later.

## Global guarantees

All snapshot outputs follow these rules.

1. `as_of_gw` means gameweek `N` is fully completed.
2. `target_gw` is deterministically defined as `as_of_gw + 1`, is a downstream consumption label, and is not persisted in warehouse outputs.
3. Every feature is computable from information available at or before `as_of_gw`.
4. Historical windows end at `as_of_gw` and never look forward.
5. Snapshot grain is unique and stable.
6. Raw source semantics are preserved. Derived fields are simple warehouse transforms, not model transforms.

## Row validity invariant

Each row represents a fully point-in-time consistent state at `as_of_gw`.

No column within a row may depend on information occurring after `as_of_gw`,
even if other columns in the same row do not.

## Window semantics

This contract supports both governed window types defined in [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md).

1. Calendar-GW windows use suffixes such as `last_gw`, `last_3gws`, and `last_5gws`.
2. Appearance windows use suffixes such as `last_3_apps`.
3. Calendar-GW windows are globally aligned by gameweek index.
4. Appearance windows are entity-local and exclude non-participation from the event sequence.
5. No field may be renamed between GW and appearance window forms without changing the underlying computation semantics.
6. Appearance-window features must not be used for cross-entity alignment or joins.
7. All joins must use snapshot keys based on `as_of_gw` and entity identifiers.
8. Team performance context windows in this contract use Calendar-GW framing and therefore use `*_last_<n>gws` suffixes.

## Time fields

Each snapshot is governed by the same time model.

1. `as_of_gw`: completed historical boundary used for feature computation.
2. `target_gw`: downstream prediction horizon label, always `as_of_gw + 1`.
3. `event_time`: validation-time concept, not a persisted snapshot column in v1.0.0.

Timestamp-aware PIT validation policy for logic using timestamped source fields is governed by [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md).

`event_time` is defined for audit purposes as the latest source timestamp permitted by the row contract.

1. `fact_player_availability_snapshot`: the latest finished fixture kickoff included in the player history up to `as_of_gw`.
2. `fact_player_performance_snapshot`: the latest finished fixture kickoff included in the player history up to `as_of_gw`.
3. `fact_team_fixture_snapshot`: the target fixture kickoff when `fixture_count = 1`, otherwise undefined.
4. `fact_player_market_snapshot`: market state reflects the latest available observation at or before `as_of_gw`.
5. `fact_team_performance_context_snapshot`: the latest finished fixture kickoff included in the team and opponent historical context windows up to `as_of_gw`.

## Snapshot responsibilities

### `fact_player_availability_snapshot`

Represents:

1. player participation behavior
2. minutes, starts, appearance frequency, and workload stability
3. player-level availability-adjacent history that is inferable from observed usage

Must not contain:

1. attacking or defensive output metrics
2. market state
3. fixture schedule or opponent context

Conditionally permitted:

1. historically snapshotted injury-state flags if a true historical source exists
2. squad-inclusion state if it is independently observed and PIT-safe

### `fact_player_performance_snapshot`

Represents:

1. player on-pitch output
2. normalized player performance rates, for example per90 metrics rather than cross-sectional normalization
3. explicit windowed performance outcomes
4. decomposed Tier 1 and Tier 2 performance inputs for downstream recomposition

Must not contain:

1. starts, minutes totals, or appearance-frequency proxies as availability signals
2. market state
3. fixture schedule or rest context

Conditionally permitted:

1. FPL-derived outcome metrics if explicitly windowed and normalized
2. FPL-derived metrics such as points may implicitly encode playing time and are therefore not pure performance signals.
3. additional Tier 1 or Tier 2 performance aggregates over explicit windows

### `fact_team_fixture_snapshot`

Represents:

1. exogenous schedule structure
2. home and away topology
3. fixture difficulty and opponent identity
4. rest and congestion

Must not contain:

1. team form
2. opponent form
3. player performance or player availability
4. market state

Conditionally permitted:

1. schedule-only DGW and BGW topology descriptors
2. fixture-order descriptors inside target-GW schedule if they do not encode outcomes

DGW and BGW constraints:

1. This snapshot remains team-grain at `as_of_gw` and does not expand to per-fixture row grain.
2. DGW and BGW behavior must reflect only source-supported and contract-supported aggregation at the declared snapshot grain.
3. When `fixture_count != 1`, opponent-specific fields are undefined unless an explicit aggregated contract field exists.
4. `fixture_difficulty` is only defined when `fixture_count = 1` and must be treated as undefined otherwise.
5. `opponent_team_fpl_id` must be `NULL` when `fixture_count != 1`.
6. No implicit aggregation is allowed.

### `fact_player_market_snapshot`

Represents:

1. ownership
2. transfer flow
3. price state and price movement

Must not contain:

1. player performance output
2. player availability behavior
3. fixture context

Conditionally permitted:

1. ownership percentage if a historical denominator exists
2. additional historical market deltas over explicit windows

### `fact_team_performance_context_snapshot`

Represents:

1. team recent performance context
2. opponent recent performance context for the target-GW opponent
3. decomposed team and opponent Tier 1 and Tier 2 context inputs for downstream recomposition

Must not contain:

1. exogenous schedule topology
2. player availability
3. player market state

Conditionally permitted:

1. additional atomic team and opponent aggregates over explicit historical windows
2. additional Tier 2 team and opponent aggregates over explicit historical windows

## Join graph contract

Primary keys:

1. Player snapshots use `(as_of_gw, fpl_id)`.
2. Team snapshots use `(as_of_gw, team_fpl_id)`.
3. `team_fpl_id` inside player snapshots is a foreign key into team-grain snapshots for the same `as_of_gw`.

Allowed joins:

1. `fact_player_availability_snapshot` ↔ `fact_player_performance_snapshot` on `(as_of_gw, fpl_id)`.
2. `fact_player_availability_snapshot` ↔ `fact_player_market_snapshot` on `(as_of_gw, fpl_id)`.
3. `fact_player_performance_snapshot` ↔ `fact_player_market_snapshot` on `(as_of_gw, fpl_id)`.
4. Any player snapshot ↔ `fact_team_fixture_snapshot` on `(as_of_gw, team_fpl_id)`.
5. Any player snapshot ↔ `fact_team_performance_context_snapshot` on `(as_of_gw, team_fpl_id)`.
6. `fact_team_fixture_snapshot` ↔ `fact_team_performance_context_snapshot` on `(as_of_gw, team_fpl_id)`.

Forbidden joins:

1. Any join that omits `as_of_gw`.
2. Any join that uses `target_gw` as the primary alignment key.
3. Any player-to-team join on current dimension tables instead of snapshot keys when a snapshot join is available.
4. Any join from player snapshots directly on `opponent_team_fpl_id` without first resolving the player’s own `team_fpl_id` at the same `as_of_gw`.
5. Any join from market directly to fixture or team context without `(as_of_gw, team_fpl_id)` mediation through a player snapshot.

## Feature hierarchy contract

### Tier 1. Atomic signals

Directly observed or directly anchored metrics, for example:

1. minutes
2. starts
3. xG
4. transfers_in
5. now_cost

### Tier 2. Windowed aggregates

Deterministic historical aggregations over explicit windows, for example:

1. `minutes_total_last_5gws`
2. `xgi_per90_last_5gws`
3. `points_avg_last_3_apps`

Allowed in warehouse scope:

1. Tier 1 atomic signals.
2. Tier 2 windowed aggregates.

### Tier 3. Compositional signals

Derived structured features built from Tier 1 and Tier 2 features are not persisted as warehouse outputs.

Examples:

1. `form_trajectory`
2. `role_change_flag`
3. `opponent_vulnerability_last_3`

Forbidden in warehouse scope:

1. Tier 3 compositional signals.

Composite handling rule:

1. every composite request must be decomposed into declared Tier 1 and Tier 2 warehouse features
2. retained composite columns are downstream-only and must not appear in warehouse snapshot schemas

## Snapshot schemas

### `fact_player_availability_snapshot`

1. `as_of_gw`
2. `fpl_id`
3. `team_fpl_id`
4. `minutes_last_gw`
5. `started_last_gw_flag`
6. `minutes_total_last_3gws`
7. `minutes_total_last_5gws`
8. `starts_count_last_3gws`
9. `starts_count_last_5gws`
10. `appearances_count_last_3gws`
11. `appearances_count_last_5gws`
12. `appearances_count_last_3_apps`
13. `minutes_avg_last_3gws`
14. `minutes_avg_last_5gws`
15. `minutes_std_last_5gws`
16. `minutes_max_last_5gws`
17. `minutes_min_when_in_squad_last_5gws`
18. `starts_rate_last_3gws`
19. `starts_rate_last_5gws`
20. `appearances_rate_last_5gws`
21. `starts_per_appearance_last_5gws`
22. `sub_appearances_count_last_5gws`
23. `sub_appearances_rate_last_5gws`
24. `minutes_avg_delta_last_3gws_vs_last_5gws`
25. `starts_rate_delta_last_3gws_vs_last_5gws`

### `fact_player_performance_snapshot`

1. `as_of_gw`
2. `fpl_id`
3. `team_fpl_id`
4. `xgi_per90_last_5gws`
5. `xg_per90_last_5gws`
6. `xa_per90_last_5gws`
7. `threat_per90_last_5gws`
8. `creativity_per90_last_5gws`
9. `ict_per90_last_5gws`
10. `cbi_per90_last_5gws`
11. `dc_per90_last_5gws`
12. `gc_per90_last_5gws`
13. `xgc_per90_last_5gws`
14. `clean_sheet_rate_last_5gws`
15. `bonus_per90_last_5gws`
16. `bps_per90_last_5gws`
17. `points_total_last_3_apps`
18. `points_avg_last_3_apps`
19. `points_std_last_3_apps`
20. `xgi_total_last_3_apps`
21. `threat_last_gw`
22. `creativity_last_gw`
23. `ict_last_gw`
24. `points_last_app`
25. `points_avg_prev_2_apps`
26. `threat_avg_last_3_apps`
27. `creativity_avg_last_3_apps`

### `fact_team_fixture_snapshot`

1. `as_of_gw`
2. `team_fpl_id`
3. `fixture_count`
4. `upcoming_dgw_flag`
5. `upcoming_bgw_flag`
6. `has_home_fixture_flag`
7. `has_away_fixture_flag`
8. `fixture_difficulty`
9. `opponent_team_fpl_id`
10. `days_since_last_fixture`
11. `matches_count_last_7d`
12. `matches_count_last_14d`
13. `days_until_next_fixture`
14. `days_between_last_and_next_fixture`
15. `midweek_turnaround_flag`

### `fact_player_market_snapshot`

1. `as_of_gw`
2. `fpl_id`
3. `now_cost`
4. `selected_by`
5. `transfers_in`
6. `transfers_out`
7. `transfers_net`
8. `price_delta_last_3gws`
9. `ownership_delta_last_3gws`

### `fact_team_performance_context_snapshot`

1. `as_of_gw`
2. `team_fpl_id`
3. `opponent_team_fpl_id`
4. `team_xg_total_last_3gws`
5. `team_xgc_total_last_3gws`
6. `team_ppda_avg_last_3gws`
7. `team_deep_total_last_3gws`
8. `team_sot_total_last_3gws`
9. `opponent_xg_total_last_3gws`
10. `opponent_xgc_total_last_3gws`
11. `opponent_xgc_avg_last_3gws`
12. `opponent_ppda_avg_last_3gws`
13. `opponent_sot_total_last_3gws`

## Feature lifecycle rules

1. Tier 1 atomic signals are the irreducible source-aligned concepts.
2. Tier 2 windowed aggregates must declare both aggregation type and window in the name.
3. Composite requests must be resolved into Tier 1 and Tier 2 fields before they enter the warehouse contract.
4. Downstream systems may recombine Tier 1 and Tier 2 features freely.
5. No Tier 2 feature may include implicit filters such as appearance-only or start-only logic unless the filter is encoded in the feature name.
6. If a downstream composite is expected, all required Tier 1 and Tier 2 inputs must already exist in the logical contract.

## Known limitations

1. `team_fpl_id` reflects the player's team at `as_of_gw` and is not historically versioned.
2. All joins using `team_fpl_id` assume current-team alignment at `as_of_gw`. No historical team inference is supported within this contract.
3. Historical injury news is not snapshot-backed, so warehouse availability remains usage-based rather than injury-feed-based.
4. Ownership percentage is unavailable because the total-manager denominator is not stored.
5. The original four-snapshot layout was not sufficient to preserve all valid signals while keeping fixture context pure, so the corrected contract requires `fact_team_performance_context_snapshot`.
6. This contract guarantees event-time PIT safety at `as_of_gw`, but it does not by itself guarantee reproducibility against later source corrections or backfills unless separate source-version or ingest-version controls exist.