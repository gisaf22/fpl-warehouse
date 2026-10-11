# fpl-warehouse

A dbt-duckdb project that turns fpl-ingest's raw FPL captures in S3 into served
tables for fpl-intelligence. Every build rebuilds from the raw captures; nothing
is updated in place.

## Served tables

Published as parquet after every successful scheduled build (07:45 and 19:45
UTC), overwritten in place. Every table carries every season, with `season` as a
column: filter on it, because ids are reassigned each season.

| Table | One row per |
|---|---|
| `s3://fpl-data-safari/served/fct_player_fixture.parquet` | `(season, fpl_id, fixture_id)` |
| `s3://fpl-data-safari/served/fct_player_gameweek.parquet` | `(season, fpl_id, gameweek)` |
| `s3://fpl-data-safari/served/dim_team.parquet` | `(season, team_fpl_id)` |
| `s3://fpl-data-safari/served/dim_player.parquet` | `(season, fpl_id)` |
| `s3://fpl-data-safari/served/dim_fixture.parquet` | `(season, fixture_id)` |
| `s3://fpl-data-safari/served/dim_player_status_history.parquet` | `(season, fpl_id, valid_from)` |
| `s3://fpl-data-safari/served/fct_player_market_snapshot.parquet` | `(season, fpl_id, capture_key)` |

`s3://fpl-data-safari/served/_manifest.json` describes the current publish: row
counts per table and season, `contract_version`, and each table's columns.
Check `contract_version` before reading. Column definitions are in
`models/marts/schema.yml`.

## Running it

```bash
uv sync
uv run dbt deps

# Fast tiers: the checked-in fixture tree, no AWS session
uv run dbt seed --target fixtures
uv run dbt build --target fixtures --exclude tag:e2e
uv run pytest

# Live build against S3 (needs an AWS session)
eval "$(aws configure export-credentials --format env)"
uv run dbt build
```

## More

`CLAUDE.md` holds the project's rules and decisions: grain, capture dedup,
ratification, the served contract, the publish guards, CI and the scheduled
build. Design decisions are recorded in `docs/adr/`.
