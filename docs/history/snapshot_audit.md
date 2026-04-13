# Archived Snapshot Audit

Version: 1.0.0

This document records the historical structural audit and correction history behind the current warehouse snapshot contract.

The active source of truth is [snapshot_contract.md](snapshot_contract.md).

Cross-cutting rules are defined in [../governance/warehouse_governance_spec.md](../governance/warehouse_governance_spec.md).

This document is archival context only. It should not be treated as an active contract or implementation guide.

## Legacy naming note

Some pre-correction column names did not encode the time window explicitly, for example `xgi_per90` where the corrected contract uses a last-5-GW window and therefore expects a name such as `xgi_per90_last_5gws`.

## Audit scope

Phase 1 identifies issues only. No changes are applied in this section.

Phase 1 audits the pre-correction warehouse layout. Because `fact_team_performance_context_snapshot` is introduced in the corrected contract, the structurally valid inventory below refers only to the four original persisted snapshot outputs.

## Phase 1. Structural audit

### A. Structurally valid

| Feature or family | Snapshot | Notes |
|---|---|---|
| Point-in-time anchors `as_of_gw`, legacy `target_gw`, entity ids | all snapshots | Pre-correction layout treated these as structural keys. In the active contract, `target_gw` remains downstream-only and is not persisted in warehouse outputs |
| Usage history families based on minutes, starts, appearances, averages, volatility | `fact_player_availability_snapshot` | Valid snapshot placement and no leakage detected |
| Exogenous schedule and congestion families based on fixture count, DGW/BGW, home/away, difficulty, rest gaps | `fact_team_fixture_snapshot` | Valid snapshot placement and no leakage detected |
| Current market state and market deltas | `fact_player_market_snapshot` | Valid snapshot placement and no leakage detected |
| Core player performance rate families based on xG, xA, xGI, threat, creativity, ICT, defensive rates | `fact_player_performance_snapshot` | Valid snapshot placement and no leakage detected |

### B. Misaligned

These features are mislocated in the pre-correction layout. Valid non-composite signals are relocated to the correct snapshot rather than dropped. Composite features are not retained as warehouse outputs in their original form and must instead be decomposed into Tier 1 and Tier 2 inputs.

| Current feature | Current snapshot | Recommended snapshot | Reason |
|---|---|---|---|
| `appearances_last_3_apps` | `fact_player_performance_snapshot` | `fact_player_availability_snapshot` | Participation volume is availability semantics, not player performance semantics |
| `team_xg_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Team form is valid but not exogenous fixture context |
| `team_xgc_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Team form is valid but not exogenous fixture context |
| `team_ppda_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Team form is valid but not exogenous fixture context |
| `team_deep_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Team form is valid but not exogenous fixture context |
| `team_sot_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Team form is valid but not exogenous fixture context |
| `opp_xg_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Opponent form is valid but not exogenous fixture context |
| `opp_xgc_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Opponent form is valid but not exogenous fixture context |
| `opp_ppda_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Opponent form is valid but not exogenous fixture context |
| `opp_sot_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Opponent form is valid but not exogenous fixture context |
| `opp_vulnerability_last_3` | `fact_team_fixture_snapshot` | `fact_team_performance_context_snapshot` | Composite opponent form belongs in team performance context, not fixture context |

### C. Ambiguous representation

| Feature or family | Issue | Correction required |
|---|---|---|
| Legacy names with implicit windows | Window boundary is documented in prose but not encoded in the name | Rename to explicit windowed names |
| `bonus_per90`, `bps_per90` | Valid normalized rates but naming omits the time window | Rename to `bonus_per90_last_5gws`, `bps_per90_last_5gws` |
| `pts_last_3_apps`, `avg_pts_last_3_apps`, `pts_std` | Valid outcome features but naming is inconsistent across total, average, and dispersion semantics | Rename to `points_total_last_3_apps`, `points_avg_last_3_apps`, `points_std_last_3_apps` |
| `xgi_last_3_apps` | Aggregate type is implicit | Rename to `xgi_total_last_3_apps` |
| `cs_pct` | Representation and window are implicit | Rename to `clean_sheet_rate_last_5gws` |
| `price_velocity_3gw`, `ownership_velocity_3gw` | Delta semantics and window naming are inconsistent with the naming standard | Rename to `price_delta_last_3gws`, `ownership_delta_last_3gws` |
| `last_gw_threat`, `last_gw_creativity`, `last_gw_ict` | Window is explicit but naming order is inconsistent with the preferred standard | Normalize to `threat_last_gw`, `creativity_last_gw`, `ict_last_gw` |

### D. Composite features requiring decomposition

| Original feature | Why composite | Required decomposition |
|---|---|---|
| `form_trajectory` | Mixes recent performance level and prior rolling baseline | `points_last_app`, `points_avg_prev_2_apps` |
| `role_change_flag` | Mixes last-GW state, rolling baseline, and threshold logic | `threat_last_gw`, `creativity_last_gw`, `threat_avg_last_3_apps`, `creativity_avg_last_3_apps` |
| `opp_vulnerability_last_3` | Mixes opponent concession and pressing into a single score | `opponent_xgc_avg_last_3gws`, `opponent_ppda_avg_last_3gws` |

### E. Temporal risk

| Feature or rule | Issue | Notes |
|---|---|---|
| `team_fpl_id` in player snapshots | Current-state team assignment is not guaranteed historical assignment | Semantic lineage risk, not future leakage |
| Legacy names without explicit windows | PIT-safe computation can still be hard to audit when the time scope is implicit | Naming correction required |
| Composite requests | Hidden thresholds or baselines can obscure PIT logic | Decomposition is required before warehouse inclusion |

### Phase 1 output summary

Join graph issues:

1. The original four-snapshot layout forced team and opponent performance into `fact_team_fixture_snapshot`, violating semantic orthogonality.
2. A distinct team-grain performance context output is required to preserve all valid signals without contaminating fixture context.

Decomposition candidates:

1. `form_trajectory`
2. `role_change_flag`
3. `opp_vulnerability_last_3`

## Phase 2. Contract correction

Phase 2 applies logical corrections only.

### Join graph rationale

1. `as_of_gw` is the PIT boundary and must anchor every join.
2. `target_gw` is a downstream label, not the historical feature anchor, and does not belong in the active warehouse snapshot schemas.
3. Team context must remain team-grain and be attached to players only through `team_fpl_id` at the same `as_of_gw`.

### Corrective operations applied

1. Relocate misaligned signals to the correct snapshot.
2. Normalize names so representation and time window are explicit.
3. Decompose composite requests into Tier 1 and Tier 2 warehouse outputs only.
4. Introduce `fact_team_performance_context_snapshot` to preserve valid team and opponent form signals.

## Change log

| Feature or family | Operation | Reason |
|---|---|---|
| Legacy historical feature names | normalize | Make window and representation explicit |
| `appearances_last_3_apps` | relocate | Availability semantics at player grain |
| Team and opponent performance features inside fixture snapshot | relocate | Preserve valid signals while keeping fixture context pure |
| `bonus_per90`, `bps_per90` | normalize | Retain valid signals with explicit time scope |
| `pts_last_3_apps`, `avg_pts_last_3_apps`, `pts_std`, `xgi_last_3_apps` | normalize | Retain valid outcome windows with explicit semantics |
| `form_trajectory` | decompose | Replace warehouse composite with Tier 1 and Tier 2 inputs |
| `role_change_flag` | decompose | Replace warehouse composite with Tier 1 and Tier 2 inputs |
| `opp_vulnerability_last_3` | relocate and decompose | Move the semantic family to team performance context and keep only Tier 1 and Tier 2 components in warehouse scope |
| `transfer_delta` | normalize | Make delta semantics explicit as `transfers_net` |
