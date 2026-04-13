"""FPL API client.

# WARNING: this module should not exist in the warehouse package. The warehouse
# must read from fpl.db only — no live API calls. get_bootstrap() is called by
# refresh_player_availability(), which is architectural debt. Once fpl.db ingestion
# persists chance_of_playing_next_round, news, and news_updated, this module and
# refresh_player_availability() can be removed.
# See docs/history/sources_refresh_debt.md.
"""

from __future__ import annotations

import requests

_BASE = "https://fantasy.premierleague.com/api"


def get_bootstrap() -> dict:
    """Fetch bootstrap-static (players, teams, events)."""
    resp = requests.get(f"{_BASE}/bootstrap-static/", timeout=15)
    resp.raise_for_status()
    return resp.json()
