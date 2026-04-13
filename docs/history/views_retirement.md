# Views Retirement

Version: 1.0.0

## What was retired

`warehouse/views.py` contained ten analytics views materialized on every warehouse build. The primary view was `v_decision_ready`, a monolithic feature derivation view that joined player availability, performance, market, and fixture context into a single wide output. Supporting views included `v_team_xg_gw` and `v_team_strength`.

These views were the original FPL decision feed, predating the governed snapshot architecture.

## Why they were retired

The views system had three structural problems.

First, semantic mixing. `v_decision_ready` combined features from four distinct semantic domains (availability, performance, market, fixture context) into one view. This made it impossible to validate grain, enforce PIT contracts, or evolve individual feature families independently.

Second, no contract enforcement. Views were materialized without schema validation, row count checks, or grain uniqueness checks. The governed snapshot pipeline introduced `contracts.py` with per-table validation at build time.

Third, duplication. By the time views were retired, every feature family had a corresponding governed snapshot table (`fact_player_availability_snapshot`, `fact_player_performance_snapshot`, `fact_player_market_snapshot`, `fact_team_fixture_snapshot`, `fact_team_performance_context_snapshot`). The views were recalculating derived state already held in validated snapshot tables.

## What replaced them

The five governed snapshot tables are the canonical warehouse outputs. Downstream consumers should join across snapshot tables at `(as_of_gw, fpl_id)` or `(as_of_gw, team_fpl_id)` rather than reading from a wide aggregation view.

The snapshot contract is defined in `docs/contracts/` and enforced at build time by `warehouse/contracts.py`.

## Removed artefacts

| Artefact | Type | Removed in |
|---|---|---|
| `warehouse/views.py` | Source module (458 lines, 10 views) | cleanup pass |
| `create_views()` call in `build.py` | Build step | cleanup pass |
| `"views"` key in `build_all()` return dict | Return value | cleanup pass |
| `tests/test_snapshot_dtypes.py` | Integration test (tested `fact_decision_snapshot`, a pre-contract table name) | cleanup pass |
| `TestSnapshotRenamed` in `test_team_normalization.py` | Test class | cleanup pass |
| `TestJoinPathIntegrity` in `test_team_normalization.py` | Test class (tested `v_team_xg_gw`, `v_team_strength`) | cleanup pass |
