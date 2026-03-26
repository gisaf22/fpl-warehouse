"""Tests for fact_manager_squad and player availability warehouse functions."""

from __future__ import annotations

import sqlite3
from unittest.mock import patch, MagicMock

import pytest

pytestmark = pytest.mark.unit

from fpl_warehouse.build import (
    FACT_MANAGER_SQUAD_DDL,
    DIM_PLAYERS_DDL,
    FACT_PLAYER_GW_DDL,
    build_fact_manager_squad,
    refresh_player_availability,
    fetch_manager_context,
    _POSITION_MAP,
    _compute_free_transfers,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def conn():
    """In-memory SQLite with dim_players seeded."""
    db = sqlite3.connect(":memory:")
    db.execute(DIM_PLAYERS_DDL)
    db.execute(FACT_MANAGER_SQUAD_DDL)
    db.execute(FACT_PLAYER_GW_DDL)
    # Seed 15 players (2 GKP, 5 DEF, 5 MID, 3 FWD)
    players = []
    for i in range(1, 16):
        if i <= 2:
            etype = 1
        elif i <= 7:
            etype = 2
        elif i <= 12:
            etype = 3
        else:
            etype = 4
        players.append((i, f"Player{i}", etype))
    db.executemany(
        "INSERT INTO dim_players (fpl_id, web_name, element_type) VALUES (?, ?, ?)",
        players,
    )
    # Seed fact_player_gw with value for round 30
    for i in range(1, 16):
        db.execute(
            "INSERT INTO fact_player_gw (fpl_id, round, value, minutes, total_points) "
            "VALUES (?, 30, ?, 90, 5)",
            (i, 50 + i),
        )
    db.commit()
    yield db
    db.close()


def _mock_picks_response(team_id: int, gw: int) -> list[dict]:
    """15 picks matching the seeded dim_players."""
    return [
        {
            "element": i,
            "element_type": 1 if i <= 2 else (2 if i <= 7 else (3 if i <= 12 else 4)),
            "is_captain": i == 12,
            "is_vice_captain": i == 11,
            "multiplier": 2 if i == 12 else 1,
            "position": i,
        }
        for i in range(1, 16)
    ]


def _mock_bootstrap_response() -> dict:
    """Minimal bootstrap-static response."""
    elements = []
    for i in range(1, 16):
        elements.append({
            "id": i,
            "now_cost": 50 + i,
            "web_name": f"Player{i}",
            "element_type": 1 if i <= 2 else (2 if i <= 7 else (3 if i <= 12 else 4)),
            "chance_of_playing_next_round": None if i != 5 else 75,
            "news": "" if i != 5 else "Hamstring concern",
            "news_added": "" if i != 5 else "2026-03-22T10:00:00Z",
        })
    return {"elements": elements}


# ---------------------------------------------------------------------------
# Tests — build_fact_manager_squad
# ---------------------------------------------------------------------------


class TestManagerSquad:
    @patch("fpl_warehouse.build.requests.get")
    def test_manager_squad_15_rows(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"picks": _mock_picks_response(1, 30)}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        count = build_fact_manager_squad(conn, team_id=1, gw=30)
        assert count == 15

        rows = conn.execute(
            "SELECT COUNT(*) FROM fact_manager_squad WHERE team_id = 1 AND gw = 30"
        ).fetchone()[0]
        assert rows == 15

    @patch("fpl_warehouse.build.requests.get")
    def test_manager_squad_positions_valid(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"picks": _mock_picks_response(1, 30)}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        build_fact_manager_squad(conn, team_id=1, gw=30)

        positions = [
            r[0] for r in conn.execute(
                "SELECT position FROM fact_manager_squad WHERE team_id = 1 AND gw = 30"
            ).fetchall()
        ]
        valid = {"GKP", "DEF", "MID", "FWD"}
        assert all(p in valid for p in positions)

    @patch("fpl_warehouse.build.requests.get")
    def test_manager_squad_grain_unique(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"picks": _mock_picks_response(1, 30)}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        build_fact_manager_squad(conn, team_id=1, gw=30)

        # Attempt duplicate insert — should replace cleanly
        build_fact_manager_squad(conn, team_id=1, gw=30)
        rows = conn.execute(
            "SELECT COUNT(*) FROM fact_manager_squad WHERE team_id = 1 AND gw = 30"
        ).fetchone()[0]
        assert rows == 15

    @patch("fpl_warehouse.build.requests.get")
    def test_manager_squad_captain_flag(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"picks": _mock_picks_response(1, 30)}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        build_fact_manager_squad(conn, team_id=1, gw=30)

        captains = conn.execute(
            "SELECT fpl_id FROM fact_manager_squad "
            "WHERE team_id = 1 AND gw = 30 AND is_captain = 1"
        ).fetchall()
        assert len(captains) == 1
        assert captains[0][0] == 12

    @patch("fpl_warehouse.build.requests.get")
    def test_manager_squad_purchase_price(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"picks": _mock_picks_response(1, 30)}
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        build_fact_manager_squad(conn, team_id=1, gw=30)

        prices = conn.execute(
            "SELECT fpl_id, purchase_price FROM fact_manager_squad "
            "WHERE team_id = 1 AND gw = 30 ORDER BY fpl_id"
        ).fetchall()
        # purchase_price derived from fact_player_gw.value (50+i) / 10
        for fpl_id, pp in prices:
            expected = (50 + fpl_id) / 10.0
            assert pp == expected, f"fpl_id {fpl_id}: {pp} != {expected}"


# ---------------------------------------------------------------------------
# Tests — refresh_player_availability
# ---------------------------------------------------------------------------


class TestAvailability:
    @patch("fpl_warehouse.build.requests.get")
    def test_availability_null_is_1(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_bootstrap_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        refresh_player_availability(conn)

        row = conn.execute(
            "SELECT chance_of_playing_next_round FROM dim_players WHERE fpl_id = 1"
        ).fetchone()
        # NULL in API → NULL in DB (NULL means fully fit by convention)
        assert row[0] is None

    @patch("fpl_warehouse.build.requests.get")
    def test_availability_range_valid(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_bootstrap_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        refresh_player_availability(conn)

        row = conn.execute(
            "SELECT chance_of_playing_next_round FROM dim_players WHERE fpl_id = 5"
        ).fetchone()
        assert row[0] == 0.75  # 75 / 100 = 0.75
        assert 0.0 <= row[0] <= 1.0

    @patch("fpl_warehouse.build.requests.get")
    def test_availability_news_stored(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_bootstrap_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        refresh_player_availability(conn)

        row = conn.execute(
            "SELECT news FROM dim_players WHERE fpl_id = 5"
        ).fetchone()
        assert row[0] == "Hamstring concern"

    @patch("fpl_warehouse.build.requests.get")
    def test_now_cost_refreshed(self, mock_get, conn):
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_bootstrap_response()
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        refresh_player_availability(conn)

        # Check that fact_player_gw.value was updated for round 30
        row = conn.execute(
            "SELECT value FROM fact_player_gw WHERE fpl_id = 1 AND round = 30"
        ).fetchone()
        assert row[0] == 51  # now_cost from bootstrap: 50 + 1 = 51


# ---------------------------------------------------------------------------
# Tests — _compute_free_transfers (pure unit, no HTTP)
# ---------------------------------------------------------------------------


def _make_gw(event: int, transfers: int, cost: int) -> dict:
    return {"event": event, "event_transfers": transfers, "event_transfers_cost": cost}


class TestComputeFreeTransfers:
    def test_one_ft_used_one_gives_one_ft_next(self):
        """Manager had 1 FT and used it — next GW = 1 FT."""
        history = [_make_gw(1, 1, 0)]
        ft, chip = _compute_free_transfers(history, {}, started_event=1)
        assert ft == 1
        assert chip is None

    def test_one_ft_used_zero_gives_two_fts_next(self):
        """Manager had 1 FT and rolled it — next GW = 2 FTs."""
        history = [_make_gw(1, 0, 0)]
        ft, chip = _compute_free_transfers(history, {}, started_event=1)
        assert ft == 2
        assert chip is None

    def test_two_fts_used_zero_capped_at_two(self):
        """Two consecutive 0-transfer GWs — FTs capped at 2."""
        history = [_make_gw(1, 0, 0), _make_gw(2, 0, 0)]
        ft, chip = _compute_free_transfers(history, {}, started_event=1)
        assert ft == 2

    def test_two_fts_used_two_gives_one_ft_next(self):
        """Manager had 2 FTs and used both — next GW = 1 FT."""
        history = [_make_gw(1, 0, 0), _make_gw(2, 2, 0)]
        ft, chip = _compute_free_transfers(history, {}, started_event=1)
        assert ft == 1

    def test_hit_taken_does_not_reduce_ft_bank(self):
        """1 FT + 1 hit (2 transfers, cost=4) → ft_used=1, next GW = 1 FT."""
        history = [_make_gw(1, 2, 4)]
        ft, chip = _compute_free_transfers(history, {}, started_event=1)
        assert ft == 1

    def test_wildcard_last_gw_returns_sentinel(self):
        """Wildcard in latest GW → 99 sentinel and chip_active flagged."""
        history = [_make_gw(1, 5, 0)]
        chip_map = {1: "wildcard"}
        ft, chip = _compute_free_transfers(history, chip_map, started_event=1)
        assert ft == 99
        assert chip == "wildcard"

    def test_wildcard_resets_ft_bank_to_one(self):
        """Wildcard in GW 1 resets FT bank; GW 2 used 0 → FTs = 2."""
        history = [_make_gw(1, 5, 0), _make_gw(2, 0, 0)]
        chip_map = {1: "wildcard"}
        ft, chip = _compute_free_transfers(history, chip_map, started_event=1)
        assert ft == 2
        assert chip is None

    def test_freehit_last_gw_returns_sentinel(self):
        """Freehit in latest GW → 99 sentinel."""
        history = [_make_gw(3, 15, 0)]
        chip_map = {3: "freehit"}
        ft, chip = _compute_free_transfers(history, chip_map, started_event=1)
        assert ft == 99
        assert chip == "freehit"

    def test_empty_history_returns_one_ft(self):
        """No history → default 1 FT."""
        ft, chip = _compute_free_transfers([], {}, started_event=1)
        assert ft == 1
        assert chip is None

    def test_started_event_filters_prior_gws(self):
        """GWs before started_event are ignored."""
        history = [_make_gw(1, 0, 0), _make_gw(2, 0, 0), _make_gw(3, 1, 0)]
        # Manager started at GW 3, used their 1 FT
        ft, chip = _compute_free_transfers(history, {}, started_event=3)
        assert ft == 1


# ---------------------------------------------------------------------------
# Tests — fetch_manager_context (mocked HTTP)
# ---------------------------------------------------------------------------


def _make_entry_response(current_event: int, bank_tenths: int, started_event: int = 1) -> dict:
    return {
        "current_event": current_event,
        "last_deadline_bank": bank_tenths,
        "started_event": started_event,
    }


def _make_history_response(
    gw_rows: list[dict],
    chips: list[dict] | None = None,
) -> dict:
    return {"current": gw_rows, "chips": chips or [], "past": []}


def _mock_two_responses(mock_get, entry: dict, history: dict) -> None:
    """Wire mock_get.side_effect to return entry then history responses."""
    entry_mock = MagicMock()
    entry_mock.json.return_value = entry
    entry_mock.raise_for_status = MagicMock()

    history_mock = MagicMock()
    history_mock.json.return_value = history
    history_mock.raise_for_status = MagicMock()

    mock_get.side_effect = [entry_mock, history_mock]


class TestFetchManagerContext:
    @patch("fpl_warehouse.build.requests.get")
    def test_bank_converted_from_tenths(self, mock_get):
        """last_deadline_bank=15 (tenths) → bank=1.5 (£m)."""
        _mock_two_responses(
            mock_get,
            entry=_make_entry_response(current_event=30, bank_tenths=15),
            history=_make_history_response([_make_gw(30, 0, 0)]),
        )
        ctx = fetch_manager_context(team_id=999)
        assert ctx["bank"] == 1.5

    @patch("fpl_warehouse.build.requests.get")
    def test_gw_returned_from_current_event(self, mock_get):
        """current_event=31 → gw=31 in returned context."""
        _mock_two_responses(
            mock_get,
            entry=_make_entry_response(current_event=31, bank_tenths=10),
            history=_make_history_response([_make_gw(31, 1, 0)]),
        )
        ctx = fetch_manager_context(team_id=999)
        assert ctx["gw"] == 31

    @patch("fpl_warehouse.build.requests.get")
    def test_normal_week_one_ft(self, mock_get):
        """Used 1 FT last GW → 1 FT available next."""
        _mock_two_responses(
            mock_get,
            entry=_make_entry_response(current_event=31, bank_tenths=10),
            history=_make_history_response([_make_gw(31, 1, 0)]),
        )
        ctx = fetch_manager_context(team_id=999)
        assert ctx["free_transfers"] == 1
        assert ctx["chip_active"] is None

    @patch("fpl_warehouse.build.requests.get")
    def test_rolled_ft_gives_two(self, mock_get):
        """Rolled FT last GW → 2 FTs available next."""
        _mock_two_responses(
            mock_get,
            entry=_make_entry_response(current_event=31, bank_tenths=10),
            history=_make_history_response([_make_gw(30, 0, 0), _make_gw(31, 0, 0)]),
        )
        ctx = fetch_manager_context(team_id=999)
        assert ctx["free_transfers"] == 2
        assert ctx["chip_active"] is None

    @patch("fpl_warehouse.build.requests.get")
    def test_wildcard_last_gw_returns_99_and_chip(self, mock_get):
        """Wildcard in most recent GW → 99 sentinel + chip_active set."""
        _mock_two_responses(
            mock_get,
            entry=_make_entry_response(current_event=31, bank_tenths=10),
            history=_make_history_response(
                [_make_gw(31, 10, 0)],
                chips=[{"event": 31, "name": "wildcard", "time": "2026-03-20T10:00:00Z"}],
            ),
        )
        ctx = fetch_manager_context(team_id=999)
        assert ctx["free_transfers"] == 99
        assert ctx["chip_active"] == "wildcard"

    @patch("fpl_warehouse.build.requests.get")
    def test_zero_ft_used_then_one_available(self, mock_get):
        """2 FTs, used 2 last GW → 1 FT next."""
        _mock_two_responses(
            mock_get,
            entry=_make_entry_response(current_event=31, bank_tenths=10),
            history=_make_history_response([_make_gw(30, 0, 0), _make_gw(31, 2, 0)]),
        )
        ctx = fetch_manager_context(team_id=999)
        assert ctx["free_transfers"] == 1
