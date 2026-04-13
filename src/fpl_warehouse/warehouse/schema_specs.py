"""Canonical structural specs for contract-governed warehouse tables.

Pure constants and type definitions. No runtime logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, TypeAlias

import sqlite3


MinRowsSpec: TypeAlias = int | Callable[[sqlite3.Connection], int]
SchemaSpec: TypeAlias = Sequence[tuple[str, str]]


@dataclass(frozen=True)
class TableContractSpec:
    """Static contract definition for one warehouse table."""

    table: str
    required_cols: list[str]
    grain_cols: list[str]
    min_rows: MinRowsSpec
    expected_schema: SchemaSpec | None = None



PLAYER_AVAILABILITY_SCHEMA: SchemaSpec = [
    ("as_of_gw", "INTEGER"),
    ("fpl_id", "INTEGER"),
    ("team_fpl_id", "INTEGER"),
    ("minutes_last_gw", "INTEGER"),
    ("started_last_gw_flag", "INTEGER"),
    ("minutes_total_last_3gws", "INTEGER"),
    ("minutes_total_last_5gws", "INTEGER"),
    ("starts_count_last_3gws", "INTEGER"),
    ("starts_count_last_5gws", "INTEGER"),
    ("appearances_count_last_3gws", "INTEGER"),
    ("appearances_count_last_5gws", "INTEGER"),
    ("appearances_count_last_3_apps", "INTEGER"),
    ("minutes_avg_last_3gws", "REAL"),
    ("minutes_avg_last_5gws", "REAL"),
    ("minutes_std_last_5gws", "REAL"),
    ("minutes_max_last_5gws", "INTEGER"),
    ("minutes_min_when_in_squad_last_5gws", "INTEGER"),
    ("starts_rate_last_3gws", "REAL"),
    ("starts_rate_last_5gws", "REAL"),
    ("appearances_rate_last_5gws", "REAL"),
    ("starts_per_appearance_last_5gws", "REAL"),
    ("sub_appearances_count_last_5gws", "INTEGER"),
    ("sub_appearances_rate_last_5gws", "REAL"),
    ("minutes_avg_delta_last_3gws_vs_last_5gws", "REAL"),
    ("starts_rate_delta_last_3gws_vs_last_5gws", "REAL"),
]

PLAYER_PERFORMANCE_SCHEMA: SchemaSpec = [
    ("as_of_gw", "INTEGER"),
    ("fpl_id", "INTEGER"),
    ("team_fpl_id", "INTEGER"),
    ("xgi_per90_last_5gws", "REAL"),
    ("xg_per90_last_5gws", "REAL"),
    ("xa_per90_last_5gws", "REAL"),
    ("threat_per90_last_5gws", "REAL"),
    ("creativity_per90_last_5gws", "REAL"),
    ("ict_per90_last_5gws", "REAL"),
    ("cbi_per90_last_5gws", "REAL"),
    ("dc_per90_last_5gws", "REAL"),
    ("gc_per90_last_5gws", "REAL"),
    ("xgc_per90_last_5gws", "REAL"),
    ("clean_sheet_rate_last_5gws", "REAL"),
    ("bonus_per90_last_5gws", "REAL"),
    ("bps_per90_last_5gws", "REAL"),
    ("points_total_last_3_apps", "REAL"),
    ("points_avg_last_3_apps", "REAL"),
    ("points_std_last_3_apps", "REAL"),
    ("xgi_total_last_3_apps", "REAL"),
    ("threat_last_gw", "REAL"),
    ("creativity_last_gw", "REAL"),
    ("ict_last_gw", "REAL"),
    ("points_last_app", "REAL"),
    ("points_avg_prev_2_apps", "REAL"),
    ("threat_avg_last_3_apps", "REAL"),
    ("creativity_avg_last_3_apps", "REAL"),
]

PLAYER_MARKET_SCHEMA: SchemaSpec = [
    ("as_of_gw", "INTEGER"),
    ("fpl_id", "INTEGER"),
    ("now_cost", "REAL"),
    ("selected_by", "INTEGER"),
    ("transfers_in", "INTEGER"),
    ("transfers_out", "INTEGER"),
    ("transfers_net", "INTEGER"),
    ("price_delta_last_3gws", "REAL"),
    ("ownership_delta_last_3gws", "INTEGER"),
]

TEAM_FIXTURE_SCHEMA: SchemaSpec = [
    ("as_of_gw", "INTEGER"),
    ("team_fpl_id", "INTEGER"),
    ("fixture_count", "INTEGER"),
    ("upcoming_dgw_flag", "INTEGER"),
    ("upcoming_bgw_flag", "INTEGER"),
    ("has_home_fixture_flag", "INTEGER"),
    ("has_away_fixture_flag", "INTEGER"),
    ("fixture_difficulty", "INTEGER"),
    ("opponent_team_fpl_id", "INTEGER"),
    ("days_since_last_fixture", "INTEGER"),
    ("matches_count_last_7d", "INTEGER"),
    ("matches_count_last_14d", "INTEGER"),
    ("days_until_next_fixture", "INTEGER"),
    ("days_between_last_and_next_fixture", "INTEGER"),
    ("midweek_turnaround_flag", "INTEGER"),
]

TEAM_PERFORMANCE_CONTEXT_SCHEMA: SchemaSpec = [
    ("as_of_gw", "INTEGER"),
    ("team_fpl_id", "INTEGER"),
    ("opponent_team_fpl_id", "INTEGER"),
    ("team_xg_total_last_3gws", "REAL"),
    ("team_xgc_total_last_3gws", "REAL"),
    ("team_ppda_avg_last_3gws", "REAL"),
    ("team_deep_total_last_3gws", "INTEGER"),
    ("team_sot_total_last_3gws", "INTEGER"),
    ("opponent_xg_total_last_3gws", "REAL"),
    ("opponent_xgc_total_last_3gws", "REAL"),
    ("opponent_xgc_avg_last_3gws", "REAL"),
    ("opponent_ppda_avg_last_3gws", "REAL"),
    ("opponent_sot_total_last_3gws", "INTEGER"),
]


__all__ = [
    "MinRowsSpec",
    "SchemaSpec",
    "TableContractSpec",
    "PLAYER_AVAILABILITY_SCHEMA",
    "PLAYER_PERFORMANCE_SCHEMA",
    "PLAYER_MARKET_SCHEMA",
    "TEAM_FIXTURE_SCHEMA",
    "TEAM_PERFORMANCE_CONTEXT_SCHEMA",
]
