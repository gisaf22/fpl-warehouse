---
description: "Use when working on the FPL warehouse contract, snapshot schema design, PIT-safe warehouse SQL, snapshot joins, warehouse reviews, or any warehouse-layer refactor. Enforces Tier 1 and Tier 2 only, orthogonality, PIT correctness, and no usefulness reasoning."
---
# Warehouse Architecture Guardrails

- The warehouse is a deterministic, time-anchored truth layer.
- Warehouse scope is limited to Tier 1 atomic signals and Tier 2 explicit windowed aggregates.
- Do not create or retain Tier 3 composite features, heuristics, latent constructs, or usefulness-driven features in warehouse outputs.
- If a requested feature is composite, decompose it into Tier 1 and Tier 2 warehouse features or mark it as downstream-only.
- `as_of_gw` is the closed historical boundary for all warehouse features.
- `target_gw` is a label and schedule anchor only. It must not be used as the historical source boundary.
- All joins must include `as_of_gw`.
- Player-grain joins use `(as_of_gw, fpl_id)`.
- Team-grain joins use `(as_of_gw, team_fpl_id)`.
- Do not use current-state dimensions to override snapshot-era keys when a snapshot join exists.
- Snapshots must remain semantically orthogonal: availability, performance, market, fixture, and team performance context are separate domains.
- Do not mix contract semantics with implementation details.
- In design-only tasks, do not produce SQL, DDL, or implementation code.
- In implementation tasks, do not redefine snapshot semantics. Implement the approved contract only.
