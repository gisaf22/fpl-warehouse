"""Data contract validation for warehouse tables."""

from __future__ import annotations

import logging
import sqlite3
from typing import List

from .db import connect_db
from .schema_specs import (
    MinRowsSpec,
    SchemaSpec,
    TableContractSpec,
    PLAYER_AVAILABILITY_SCHEMA,
    PLAYER_PERFORMANCE_SCHEMA,
    PLAYER_MARKET_SCHEMA,
    TEAM_FIXTURE_SCHEMA,
    TEAM_PERFORMANCE_CONTEXT_SCHEMA,
)

logger = logging.getLogger(__name__)


def _count_table_rows(conn: sqlite3.Connection, table: str) -> int:
    """Return row count for a table, or 0 if the table is unavailable."""
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row and row[0] is not None else 0


def _count_finished_gameweeks(conn: sqlite3.Connection) -> int:
    """Return the number of finished gameweeks present in fact_fixtures."""
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT event) FROM fact_fixtures WHERE finished = 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0]) if row and row[0] is not None else 0


def _scaled_min_rows(
    conn: sqlite3.Connection,
    entity_table: str,
    coverage_ratio: float = 0.5,
) -> int:
    """Scale minimum rows by season progress and entity count.

    Early season tables should be much smaller than mid-season tables.
    Use a conservative lower bound of 50% entity coverage per finished GW.
    """
    finished_gws = _count_finished_gameweeks(conn)
    entity_count = _count_table_rows(conn, entity_table)
    per_gw_min = max(1, int(entity_count * coverage_ratio))
    return max(1, finished_gws * per_gw_min)


def _player_scaled_min_rows(conn: sqlite3.Connection) -> int:
    """Season-aware minimum row count for player-grain tables."""
    return _scaled_min_rows(conn, "dim_players")


def _team_scaled_min_rows(conn: sqlite3.Connection) -> int:
    """Season-aware minimum row count for team-grain tables."""
    return _scaled_min_rows(conn, "dim_teams")


def _resolve_min_rows(conn: sqlite3.Connection, min_rows: MinRowsSpec) -> int:
    """Resolve a fixed or computed min_rows contract into an integer."""
    return min_rows(conn) if callable(min_rows) else min_rows


def validate_table_contract(
    conn: sqlite3.Connection,
    table: str,
    required_cols: List[str],
    grain_cols: List[str],
    min_rows: int = 1,
    expected_schema: SchemaSpec | None = None,
) -> None:
    """Validate a warehouse table against its data contract.

    Checks: table exists, required columns present, exact schema alignment
    when provided, row count >= min_rows, grain is unique, and required
    columns contain no NULL values.

    Raises:
        ValueError: with a descriptive message if any check fails.
    """
    _check_exists(conn, table)
    table_info = _get_table_info(conn, table)
    _check_cols(table, table_info, required_cols)
    if expected_schema is not None:
        _check_exact_schema(table, table_info, expected_schema)
    _check_rows(conn, table, min_rows)
    _check_grain(conn, table, grain_cols)
    _check_nulls(conn, table, required_cols)


def _get_table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    """Return PRAGMA table_info rows for a table."""
    return conn.execute(f"PRAGMA table_info({table})").fetchall()


def _check_exists(conn: sqlite3.Connection, table: str) -> None:
    """Fail if the expected table does not exist."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if row is None:
        raise ValueError(f"Contract violation: table '{table}' does not exist")


def _check_cols(table: str, table_info: list[sqlite3.Row], required_cols: List[str]) -> None:
    """Fail if any required columns are missing from the table schema."""
    existing = {row[1] for row in table_info}
    missing = [c for c in required_cols if c not in existing]
    if missing:
        raise ValueError(
            f"Contract violation: '{table}' missing required columns: {missing}"
        )


def _check_exact_schema(
    table: str,
    table_info: list[sqlite3.Row],
    expected_schema: SchemaSpec,
) -> None:
    """Fail if column order or declared types diverge from the contract."""
    actual_schema = [(row[1], (row[2] or "").upper()) for row in table_info]
    normalized_expected = [(name, declared_type.upper()) for name, declared_type in expected_schema]
    if actual_schema != normalized_expected:
        raise ValueError(
            f"Contract violation: '{table}' schema does not match expected contract. "
            f"expected={normalized_expected}, actual={actual_schema}"
        )


def _check_rows(conn: sqlite3.Connection, table: str, min_rows: int) -> None:
    """Fail if the table row count is below the resolved threshold."""
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if count < min_rows:
        raise ValueError(
            f"Contract violation: '{table}' has {count} rows (min {min_rows})"
        )


def _check_grain(conn: sqlite3.Connection, table: str, grain_cols: List[str]) -> None:
    """Fail if the declared table grain is not unique."""
    cols_sql = ", ".join(grain_cols)
    dup_count = conn.execute(
        f"SELECT COUNT(*) FROM ("
        f"  SELECT {cols_sql} FROM {table}"
        f"  GROUP BY {cols_sql} HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    if dup_count > 0:
        raise ValueError(
            f"Contract violation: '{table}' has {dup_count} duplicate "
            f"grain combinations ({grain_cols})"
        )


def _check_nulls(conn: sqlite3.Connection, table: str, required_cols: List[str]) -> None:
    """Fail if any required column contains NULL values."""
    for col in required_cols:
        null_count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
        ).fetchone()[0]
        if null_count > 0:
            raise ValueError(
                f"Contract violation: '{table}'.{col} has {null_count} NULL rows"
            )


def build_contract_specs(
    player_scaled_min_rows: MinRowsSpec,
    team_scaled_min_rows: MinRowsSpec,
) -> list[TableContractSpec]:
    """Return the build-time contract registry for persisted warehouse tables."""
    return [
        TableContractSpec("dim_teams", ["fpl_id", "fpl_name"], ["fpl_id"], 20),
        TableContractSpec("dim_players", ["fpl_id", "web_name"], ["fpl_id"], 400),
        TableContractSpec(
            "fact_player_gw",
            ["fpl_id", "round", "total_points", "minutes"],
            ["fpl_id", "round"],
            player_scaled_min_rows,
        ),
        TableContractSpec(
            "fact_player_availability_snapshot",
            ["as_of_gw", "fpl_id", "team_fpl_id"],
            ["as_of_gw", "fpl_id"],
            player_scaled_min_rows,
            expected_schema=PLAYER_AVAILABILITY_SCHEMA,
        ),
        TableContractSpec(
            "fact_player_performance_snapshot",
            ["as_of_gw", "fpl_id", "team_fpl_id"],
            ["as_of_gw", "fpl_id"],
            player_scaled_min_rows,
            expected_schema=PLAYER_PERFORMANCE_SCHEMA,
        ),
        TableContractSpec(
            "fact_player_market_snapshot",
            ["as_of_gw", "fpl_id"],
            ["as_of_gw", "fpl_id"],
            player_scaled_min_rows,
            expected_schema=PLAYER_MARKET_SCHEMA,
        ),
        TableContractSpec(
            "fact_team_fixture_snapshot",
            ["as_of_gw", "team_fpl_id"],
            ["as_of_gw", "team_fpl_id"],
            team_scaled_min_rows,
            expected_schema=TEAM_FIXTURE_SCHEMA,
        ),
        TableContractSpec(
            "fact_team_performance_context_snapshot",
            ["as_of_gw", "team_fpl_id"],
            ["as_of_gw", "team_fpl_id"],
            team_scaled_min_rows,
            expected_schema=TEAM_PERFORMANCE_CONTEXT_SCHEMA,
        ),
    ]


def validate_build(warehouse_db: str) -> None:
    """Run all warehouse table contract checks after a full build.

    Uses fixed row-count thresholds for stable dimensions and season-aware
    thresholds for fact/snapshot tables whose size grows over time.
    """
    conn = connect_db(warehouse_db)
    try:
        for spec in build_contract_specs(_player_scaled_min_rows, _team_scaled_min_rows):
            min_rows = _resolve_min_rows(conn, spec.min_rows)
            validate_table_contract(
                conn,
                spec.table,
                spec.required_cols,
                spec.grain_cols,
                min_rows=min_rows,
                expected_schema=spec.expected_schema,
            )
    finally:
        conn.close()
    logger.info("All data contract checks passed")
