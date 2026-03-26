"""Smoke tests for refresh_manager_squad and fetch_manager_context.

Requires live FPL API access and TEAM_ID env var.

Run:
    TEAM_ID=<your_id> python -m pytest projects/fpl-warehouse/tests/test_smoke_manager.py -v -s
"""

from __future__ import annotations

import os
import sqlite3

import pytest

pytestmark = pytest.mark.smoke

_SKIP = pytest.mark.skipif(
    not os.environ.get("TEAM_ID"),
    reason="Set TEAM_ID env var to run warehouse smoke tests",
)

DEFAULT_WAREHOUSE_DB = str(
    __import__("pathlib").Path.home()
    / "Documents/FPL/data/warehouse/master.db"
)


@_SKIP
def test_fetch_manager_context_smoke() -> None:
    """fetch_manager_context() returns a valid context dict from live API."""
    from fpl_warehouse.build import fetch_manager_context

    team_id = int(os.environ["TEAM_ID"])
    ctx = fetch_manager_context(team_id)

    assert isinstance(ctx["gw"], int), "gw must be int"
    assert 1 <= ctx["gw"] <= 38, f"gw out of range: {ctx['gw']}"
    assert isinstance(ctx["bank"], float), "bank must be float"
    assert ctx["bank"] >= 0.0, f"bank negative: {ctx['bank']}"
    assert ctx["free_transfers"] in (0, 1, 2, 99), (
        f"unexpected FT value: {ctx['free_transfers']}"
    )
    if ctx["free_transfers"] == 99:
        assert ctx["chip_active"] in ("wildcard", "freehit")
    else:
        assert ctx["chip_active"] is None

    print(f"\nContext: {ctx}")


@_SKIP
def test_refresh_manager_squad_smoke() -> None:
    """refresh_manager_squad() populates fact_manager_squad with 15 rows."""
    from fpl_warehouse.build import fetch_manager_context, refresh_manager_squad

    team_id = int(os.environ["TEAM_ID"])

    ctx = fetch_manager_context(team_id)
    gw = ctx["gw"]

    refresh_manager_squad(team_id, warehouse_db=DEFAULT_WAREHOUSE_DB)

    conn = sqlite3.connect(DEFAULT_WAREHOUSE_DB)
    try:
        rows = conn.execute(
            "SELECT COUNT(*) FROM fact_manager_squad WHERE team_id = ? AND gw = ?",
            (team_id, gw),
        ).fetchone()[0]
    finally:
        conn.close()

    assert rows == 15, f"Expected 15 squad rows, got {rows}"
    print(f"\nSquad refreshed: {rows} rows for team {team_id} GW {gw}")
