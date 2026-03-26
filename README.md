# fpl-warehouse

Merges FPL and Understat ingestion databases into a unified warehouse database.

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

## Prerequisites

Run both ingest pipelines first:
```bash
fpl-ingest
understat-ingest
```
