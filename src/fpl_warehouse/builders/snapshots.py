"""Snapshot materializers and live player availability refresh."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from ..sources import fpl
from ..sql_runner import create_view
from ..warehouse.db import connect_db, connect_warehouse
from ..warehouse.ddl import (
    FACT_PLAYER_AVAILABILITY_SNAPSHOT_DDL,
    FACT_PLAYER_MARKET_SNAPSHOT_DDL,
    FACT_PLAYER_PERFORMANCE_SNAPSHOT_DDL,
    FACT_TEAM_FIXTURE_SNAPSHOT_DDL,
    FACT_TEAM_PERFORMANCE_CONTEXT_SNAPSHOT_DDL,
)

logger = logging.getLogger(__name__)

_MODELS = Path(__file__).resolve().parents[2] / "models"
_AVAILABILITY = _MODELS / "availability"
_PERFORMANCE = _MODELS / "performance"
_MARKET = _MODELS / "market"
_TEAM_FIXTURE = _MODELS / "team_fixture"
_TEAM_PERFORMANCE_CONTEXT = _MODELS / "team_performance_context"


@dataclass
class SnapshotSpec:
    table: str
    ddl: str
    int_views: List[Path]
    fact_sql: Path
    indexes: List[Tuple[str, str]]


_SPECS: List[SnapshotSpec] = [
    SnapshotSpec(
        table="fact_player_availability_snapshot",
        ddl=FACT_PLAYER_AVAILABILITY_SNAPSHOT_DDL,
        # int_player_gw_base is the shared player-grain intermediate used by
        # availability, performance, and market snapshots.
        int_views=[
            _AVAILABILITY / "int_player_gw_base.sql",
            _AVAILABILITY / "fct_player_availability_features.sql",
        ],
        fact_sql=_AVAILABILITY / "fact_player_availability_snapshot.sql",
        indexes=[
            ("idx_availability_snapshot_gw", "as_of_gw"),
            ("idx_availability_snapshot_player", "fpl_id"),
        ],
    ),
    SnapshotSpec(
        table="fact_player_performance_snapshot",
        ddl=FACT_PLAYER_PERFORMANCE_SNAPSHOT_DDL,
        # int_player_gw_base lives in availability/ and is shared here.
        int_views=[
            _AVAILABILITY / "int_player_gw_base.sql",
            _PERFORMANCE / "fct_player_performance_features.sql",
        ],
        fact_sql=_PERFORMANCE / "fact_player_performance_snapshot.sql",
        indexes=[
            ("idx_performance_snapshot_gw", "as_of_gw"),
            ("idx_performance_snapshot_player", "fpl_id"),
        ],
    ),
    SnapshotSpec(
        table="fact_player_market_snapshot",
        ddl=FACT_PLAYER_MARKET_SNAPSHOT_DDL,
        # int_player_gw_base lives in availability/ and is shared here.
        int_views=[
            _AVAILABILITY / "int_player_gw_base.sql",
            _MARKET / "fct_player_market_features.sql",
        ],
        fact_sql=_MARKET / "fact_player_market_snapshot.sql",
        indexes=[
            ("idx_market_snapshot_gw", "as_of_gw"),
            ("idx_market_snapshot_player", "fpl_id"),
        ],
    ),
    SnapshotSpec(
        table="fact_team_fixture_snapshot",
        ddl=FACT_TEAM_FIXTURE_SNAPSHOT_DDL,
        int_views=[
            _TEAM_FIXTURE / "fct_team_fixture_features.sql",
        ],
        fact_sql=_TEAM_FIXTURE / "fact_team_fixture_snapshot.sql",
        indexes=[
            ("idx_team_fixture_snapshot_gw", "as_of_gw"),
            ("idx_team_fixture_snapshot_team", "team_fpl_id"),
        ],
    ),
    SnapshotSpec(
        table="fact_team_performance_context_snapshot",
        ddl=FACT_TEAM_PERFORMANCE_CONTEXT_SNAPSHOT_DDL,
        # int_team_fixture_base lives in team_fixture/ and is shared here.
        int_views=[
            _TEAM_FIXTURE / "int_team_fixture_base.sql",
            _TEAM_PERFORMANCE_CONTEXT / "fct_team_performance_context_features.sql",
        ],
        fact_sql=_TEAM_PERFORMANCE_CONTEXT / "fact_team_performance_context_snapshot.sql",
        indexes=[
            ("idx_team_performance_context_snapshot_gw", "as_of_gw"),
            ("idx_team_performance_context_snapshot_team", "team_fpl_id"),
        ],
    ),
]


def materialize_snapshot(warehouse_db: str, spec: SnapshotSpec) -> int:
    """Rebuild a snapshot table from its SQL spec. Returns row count."""
    check_conn = connect_db(warehouse_db)
    has_finished = check_conn.execute(
        "SELECT COUNT(*) FROM fact_fixtures WHERE finished = 1"
    ).fetchone()[0]
    check_conn.close()
    if not has_finished:
        logger.warning("No finished GWs — skipping %s materialization", spec.table)
        return 0

    conn = connect_warehouse(warehouse_db)

    for view_path in spec.int_views:
        create_view(conn, view_path)

    conn.execute(f"DROP TABLE IF EXISTS {spec.table}")
    conn.execute(spec.ddl)
    for idx_name, col in spec.indexes:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {spec.table}({col})")

    fact_sql = spec.fact_sql.read_text()
    cursor = conn.execute(f"INSERT INTO {spec.table}\n{fact_sql}")
    total = cursor.rowcount

    conn.commit()
    conn.close()
    logger.info("Materialized %s: %d total rows", spec.table, total)
    return total


def materialize_all_snapshots(warehouse_db: str) -> dict[str, int]:
    """Materialize all snapshot tables. Returns table to row count."""
    return {spec.table: materialize_snapshot(warehouse_db, spec) for spec in _SPECS}


def materialize_player_availability_snapshot(warehouse_db: str) -> int:
    return materialize_snapshot(warehouse_db, _SPECS[0])


def materialize_player_performance_snapshot(warehouse_db: str) -> int:
    return materialize_snapshot(warehouse_db, _SPECS[1])


def materialize_player_market_snapshot(warehouse_db: str) -> int:
    return materialize_snapshot(warehouse_db, _SPECS[2])


def materialize_team_fixture_snapshot(warehouse_db: str) -> int:
    return materialize_snapshot(warehouse_db, _SPECS[3])


def materialize_team_performance_context_snapshot(warehouse_db: str) -> int:
    return materialize_snapshot(warehouse_db, _SPECS[4])


def refresh_player_availability(conn) -> int:
    """Fetch bootstrap-static and update live availability fields on dim_players.

    # WARNING: architectural debt. The warehouse must not call the FPL API directly.
    # chance_of_playing_next_round, news, and news_updated belong in fpl.db, owned
    # by the FPL ingestion layer. This function and the --refresh-availability CLI
    # flag should be removed once fpl.db ingestion persists those fields.
    # See docs/history/sources_refresh_debt.md.
    """
    data = fpl.get_bootstrap()
    elements = data["elements"]

    existing = {r[1] for r in conn.execute("PRAGMA table_info(dim_players)").fetchall()}
    for col, typ in [
        ("chance_of_playing_next_round", "REAL"),
        ("news", "TEXT"),
        ("news_updated", "TEXT"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE dim_players ADD COLUMN {col} {typ}")

    count = 0
    for element in elements:
        fpl_id = element["id"]
        raw = element.get("chance_of_playing_next_round")
        availability = raw / 100.0 if raw is not None else None
        result = conn.execute(
            """UPDATE dim_players
               SET chance_of_playing_next_round = ?,
                   news = ?,
                   news_updated = ?
               WHERE fpl_id = ?""",
            (availability, element.get("news", ""), element.get("news_added", ""), fpl_id),
        )
        if result.rowcount > 0:
            count += 1

    conn.commit()
    logger.info("Player availability refreshed: %d players updated", count)
    return count
