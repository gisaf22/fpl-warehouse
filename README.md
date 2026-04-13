# fpl-warehouse

Merges FPL and Understat ingestion databases into a unified warehouse database.

## Start Here

If you are new to this repo, read documents in this order:

1. [docs/README.md](docs/README.md) for the documentation map.
2. [docs/contracts/snapshot_contract.md](docs/contracts/snapshot_contract.md) for the warehouse snapshot contract.
3. [docs/governance/warehouse_governance_spec.md](docs/governance/warehouse_governance_spec.md) for warehouse rules and validation policy.
4. [docs/system/data_lineage_map.md](docs/system/data_lineage_map.md) for physical warehouse inventory and upstream lineage.
5. [docs/governance/data_freshness_policy.md](docs/governance/data_freshness_policy.md) for refresh cadence, mutability, and rebuild policy.
6. [docs/system/architecture.md](docs/system/architecture.md) for build flow and system boundaries.

## What it does

1. **Team matching** — Maps FPL team names ↔ Understat team names
2. **Player matching** — Fuzzy-matches FPL players to Understat players using name + team
3. **Warehouse build** — Merges data from both sources into `master.db`:
   - `dim_teams` — unified team dimension
   - `dim_players` — unified player dimension with cross-source IDs
   - `fact_player_gw` — per-player per-gameweek stats from both FPL and Understat
   - `fact_fixtures` — fixture-level stats including xG, PPDA, deep completions
   - `fact_shots` — shot-level data linked to FPL player IDs

## Usage

```bash
fpl-warehouse              # Build/refresh the warehouse
fpl-warehouse --force      # Rebuild from scratch
fpl-warehouse --verbose    # Debug logging
```

## Data flow

```
fpl.db ──────┐
             ├──→ master.db
understat.db ┘
```

See [docs/system/architecture.md](docs/system/architecture.md) for workflow diagrams.

## Documentation

Use these files as the source of truth for different questions:

1. [docs/README.md](docs/README.md) for where to start and which document owns what.
2. [docs/contracts/snapshot_contract.md](docs/contracts/snapshot_contract.md) for modeling snapshot responsibilities, join rules, and naming.
3. [docs/governance/warehouse_governance_spec.md](docs/governance/warehouse_governance_spec.md) for naming rules, feature-tier policy, PIT checks, and join safety.
4. [docs/history/snapshot_audit.md](docs/history/snapshot_audit.md) for archived audit findings and migration rationale.
5. [docs/system/data_lineage_map.md](docs/system/data_lineage_map.md) for persisted warehouse tables and source-to-warehouse mapping.
6. [docs/governance/data_freshness_policy.md](docs/governance/data_freshness_policy.md) for refresh cadence, mutability, and rebuild expectations.
7. [docs/system/architecture.md](docs/system/architecture.md) for execution flow, package boundaries, and runtime orchestration.

## Prerequisites

Run both ingest pipelines first:
```bash
fpl-ingest
understat-ingest
```

## Notes

1. The warehouse contract, governance rules, and physical warehouse inventory are separate documents on purpose.
2. Contract changes should be made before implementation changes.
3. Governance should be checked before implementation changes.
4. Warehouse outputs should remain PIT-safe and semantically orthogonal.
5. The warehouse is currently operated as a twice-daily latest-reconstructed-truth rebuild, not a source-versioned historical archive.
