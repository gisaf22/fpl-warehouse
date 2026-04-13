"""Warehouse build orchestrator.

Delegates to focused modules; contains no data logic.
"""

from __future__ import annotations

import logging
from typing import Dict

from .builders.dimensions import build_dim_gameweeks, build_dim_players, build_dim_teams
from .builders.facts import (
    build_fact_fixtures,
    build_fact_match_stats,
    build_fact_player_gw,
    build_fact_shots,
    build_fixture_bridge,
    enrich_xg_chain_buildup,
)
from .builders.snapshots import materialize_all_snapshots
from .warehouse.contracts import validate_build
from .warehouse.schema import create_schema

logger = logging.getLogger(__name__)


def build_all(
    fpl_db: str, understat_db: str, warehouse_db: str,
    threshold: int = 75,
) -> Dict[str, int]:
    """Run full warehouse build pipeline. Returns table → row count."""
    create_schema(warehouse_db)

    team_lookup = build_dim_teams(fpl_db, warehouse_db)
    gw_count = build_dim_gameweeks(fpl_db, warehouse_db)
    matched = build_dim_players(fpl_db, understat_db, warehouse_db, team_lookup, threshold)

    bridge = build_fixture_bridge(fpl_db, understat_db)

    player_gw_count = build_fact_player_gw(fpl_db, warehouse_db)
    shots_count = build_fact_shots(understat_db, warehouse_db)
    fixtures_count = build_fact_fixtures(fpl_db, warehouse_db)
    match_stats_count = build_fact_match_stats(fpl_db, understat_db, warehouse_db, bridge)
    xg_enriched = enrich_xg_chain_buildup(understat_db, warehouse_db, bridge)

    snapshot_counts = materialize_all_snapshots(warehouse_db)

    validate_build(warehouse_db)

    return {
        "dim_teams": len(team_lookup),
        "dim_gameweeks": gw_count,
        "dim_players_matched": matched,
        "fact_player_gw": player_gw_count,
        "fact_player_gw_xg_enriched": xg_enriched,
        "fact_shots": shots_count,
        "fact_fixtures": fixtures_count,
        "fact_match_stats": match_stats_count,
        "fixture_bridge": len(bridge),
        **snapshot_counts,
    }
