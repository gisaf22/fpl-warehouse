"""DDL strings for all warehouse tables.

Base table DDL is read from base_tables/*.sql files.
Snapshot table DDL is generated from schema_specs column definitions.
"""

from __future__ import annotations

from pathlib import Path

from .schema_specs import (
    PLAYER_AVAILABILITY_SCHEMA,
    PLAYER_MARKET_SCHEMA,
    PLAYER_PERFORMANCE_SCHEMA,
    SchemaSpec,
    TEAM_FIXTURE_SCHEMA,
    TEAM_PERFORMANCE_CONTEXT_SCHEMA,
)

_SCHEMA_DIR = Path(__file__).resolve().parents[1] / "base_tables"


def _read_schema(file_name: str) -> str:
    """Read one schema SQL file into a reusable DDL string."""
    return (_SCHEMA_DIR / file_name).read_text()


def render_create_table_ddl(
    table: str,
    schema: SchemaSpec,
    primary_key_cols: tuple[str, ...]
) -> str:
    """Render a CREATE TABLE statement from a canonical schema spec."""
    primary_key_set = set(primary_key_cols)
    column_lines = []
    for name, declared_type in schema:
        suffix = " NOT NULL" if name in primary_key_set else ""
        column_lines.append(f"    {name:<35} {declared_type}{suffix}")

    pk_sql = ", ".join(primary_key_cols)
    columns_sql = ",\n".join(column_lines)
    return (
        f"CREATE TABLE IF NOT EXISTS {table} (\n"
        f"{columns_sql},\n"
        f"    PRIMARY KEY ({pk_sql})\n"
        f")"
    )


# Base tables — DDL sourced from base_tables/*.sql
DIM_TEAMS_DDL = _read_schema("01_dim_teams.sql")
DIM_PLAYERS_DDL = _read_schema("02_dim_players.sql")
FACT_PLAYER_GW_DDL = _read_schema("04_fact_player_gw.sql")
FACT_FIXTURES_DDL = _read_schema("06_fact_fixtures.sql")
FACT_MATCH_STATS_DDL = _read_schema("07_fact_match_stats.sql")

# Snapshot tables — DDL generated from schema_specs column definitions
FACT_PLAYER_AVAILABILITY_SNAPSHOT_DDL = render_create_table_ddl(
    "fact_player_availability_snapshot",
    PLAYER_AVAILABILITY_SCHEMA,
    ("as_of_gw", "fpl_id"),
)
FACT_PLAYER_PERFORMANCE_SNAPSHOT_DDL = render_create_table_ddl(
    "fact_player_performance_snapshot",
    PLAYER_PERFORMANCE_SCHEMA,
    ("as_of_gw", "fpl_id"),
)
FACT_PLAYER_MARKET_SNAPSHOT_DDL = render_create_table_ddl(
    "fact_player_market_snapshot",
    PLAYER_MARKET_SCHEMA,
    ("as_of_gw", "fpl_id"),
)
FACT_TEAM_FIXTURE_SNAPSHOT_DDL = render_create_table_ddl(
    "fact_team_fixture_snapshot",
    TEAM_FIXTURE_SCHEMA,
    ("as_of_gw", "team_fpl_id"),
)
FACT_TEAM_PERFORMANCE_CONTEXT_SNAPSHOT_DDL = render_create_table_ddl(
    "fact_team_performance_context_snapshot",
    TEAM_PERFORMANCE_CONTEXT_SCHEMA,
    ("as_of_gw", "team_fpl_id"),
)

__all__ = [
    "DIM_PLAYERS_DDL",
    "DIM_TEAMS_DDL",
    "FACT_FIXTURES_DDL",
    "FACT_MATCH_STATS_DDL",
    "FACT_PLAYER_AVAILABILITY_SNAPSHOT_DDL",
    "FACT_PLAYER_GW_DDL",
    "FACT_PLAYER_MARKET_SNAPSHOT_DDL",
    "FACT_PLAYER_PERFORMANCE_SNAPSHOT_DDL",
    "FACT_TEAM_FIXTURE_SNAPSHOT_DDL",
    "FACT_TEAM_PERFORMANCE_CONTEXT_SNAPSHOT_DDL",
]
