"""Shared harness for the publish_served.py tests.

Builds a small warehouse file holding just what publish_served.py reads
(staging for the expectation, the served tables for the export), stands a fake
S3 client in for boto3 that serves a chosen previous manifest, and runs main()
as the workflow does. "Refused" means exit 1 with nothing uploaded;
"published" means exit 0 with every served table and the manifest uploaded.

Not a test module: pytest collects only test_*.py.
"""

from __future__ import annotations

import io
import json
import sys

import duckdb
from botocore.exceptions import ClientError

import publish_served

CLOSED = "2025-26"
LIVE = "2026-27"
MANIFEST_KEY = "served/_manifest.json"

FACTS = ("fct_player_fixture", "fct_player_gameweek")
DIMENSIONS = ("dim_team", "dim_player", "dim_fixture")
HISTORY = ("dim_player_status_history",)
# Everything that should be served, stated here rather than read from
# publish_served.TABLES, so a table the script forgets to serve fails these
# tests instead of silently dropping out of them.
SERVED = FACTS + DIMENSIONS + HISTORY

# Every served table's columns in the harness build, as the manifest records
# them: [name, type] in order, read back from the exported parquet.
COLUMNS = "season varchar, row_number integer"
SHAPE = [["season", "VARCHAR"], ["row_number", "INTEGER"]]


class FakeS3:
    """Serves one previous manifest and records every upload."""

    def __init__(self, previous: dict | bytes | None) -> None:
        self.previous = previous
        self.uploads: dict[str, bytes] = {}

    def get_object(self, Bucket: str, Key: str) -> dict:  # noqa: N803 - boto3's names
        if Key != MANIFEST_KEY or self.previous is None:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "not found"}},
                "GetObject",
            )
        body = (
            self.previous
            if isinstance(self.previous, bytes)
            else json.dumps(self.previous).encode()
        )
        return {"Body": io.BytesIO(body)}

    def put_object(self, Bucket: str, Key: str, Body: bytes, **_: object) -> dict:  # noqa: N803
        self.uploads[Key] = Body
        return {}

    def published_manifest(self) -> dict:
        return json.loads(self.uploads[MANIFEST_KEY])


def season(
    players: int,
    finished_gameweeks: int,
    fixture: int | None = None,
    gameweek: int | None = None,
    *,
    teams: int = 20,
    fixtures: int = 380,
    team_rows: int | None = None,
    player_rows: int | None = None,
    fixture_rows: int | None = None,
    status_history_rows: int | None = None,
    player_fixture_rows: int = 1,
) -> dict:
    """One season's staging shape and served row counts.

    `players`, `finished_gameweeks`, `teams`, `fixtures` and
    `player_fixture_rows` shape staging: the players and finished gameweeks in
    bootstrap-static, the teams in its team list, the fixtures in the fixtures
    endpoint, and element-summary history rows. Served counts default to
    exactly what staging implies, which clears every table's floor: players x
    finished gameweeks for both facts, the staged teams, players and
    fixtures for the dimensions, and one status history row per staged
    player.
    """
    expected = players * finished_gameweeks
    return {
        "players": players,
        "finished_gameweeks": finished_gameweeks,
        "teams": teams,
        "fixtures": fixtures,
        "player_fixture_rows": player_fixture_rows,
        "fct_player_fixture": expected if fixture is None else fixture,
        "fct_player_gameweek": expected if gameweek is None else gameweek,
        "dim_team": teams if team_rows is None else team_rows,
        "dim_player": players if player_rows is None else player_rows,
        "dim_fixture": fixtures if fixture_rows is None else fixture_rows,
        "dim_player_status_history": (
            players if status_history_rows is None else status_history_rows
        ),
    }


def manifest(
    tables: tuple[str, ...] = SERVED,
    *,
    contract_version: int | None = None,
    columns: dict[str, list] | None = None,
    **by_season: dict,
) -> dict:
    """A previous manifest recording each season's served counts.

    `tables` names what that publish served. Pass FACTS for a manifest written
    before the dimensions were served, which is what the first publish after
    they are added reads.

    `contract_version` and `columns` are left out unless given, as in every
    manifest published before #74.
    """
    by_table = {
        table: {name: shape[table] for name, shape in by_season.items()}
        for table in tables
    }
    previous = {
        "run_id": "previous",
        "seasons": sorted(by_season),
        "row_counts": {
            table: sum(counts.values()) for table, counts in by_table.items()
        },
        "row_counts_by_season": by_table,
    }
    if contract_version is not None:
        previous["contract_version"] = contract_version
    if columns is not None:
        previous["columns"] = columns
    return previous


def make_publish(tmp_path, monkeypatch):
    """Return run(build, previous, args): build a warehouse, then run main().

    `version` is the build's served_contract_version var. `columns` overrides a
    served table's column DDL, {table: "name type, ..."}; every other table
    takes COLUMNS.
    """

    project = tmp_path / "dbt_project.yml"
    monkeypatch.setattr(publish_served, "PROJECT_FILE", project)
    monkeypatch.setattr(publish_served, "OUT_DIR", tmp_path / "served")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    def run(
        build: dict[str, dict],
        previous: dict | bytes | None,
        args: list[str] = (),
        *,
        version: int = 1,
        columns: dict[str, str] | None = None,
    ):
        project.write_text(
            f"vars:\n  season: '{LIVE}'\n  served_contract_version: {version}\n"
        )
        database = tmp_path / "warehouse.duckdb"
        database.unlink(missing_ok=True)
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                "create table stg_player (season varchar, fpl_id integer)"
            )
            connection.execute(
                "create table stg_gameweek (season varchar, run_id varchar, "
                "observed_at timestamp, gameweek integer, finished boolean)"
            )
            connection.execute(
                "create table stg_team (season varchar, team_fpl_id integer)"
            )
            connection.execute(
                "create table stg_fixture (season varchar, fixture_id integer)"
            )
            connection.execute(
                "create table stg_player_fixture (season varchar, fpl_id integer)"
            )
            for table in SERVED:
                ddl = (columns or {}).get(table, COLUMNS)
                connection.execute(f"create table {table} ({ddl})")
            for name, shape in build.items():
                for table, count in (
                    ("stg_player", shape["players"]),
                    ("stg_team", shape["teams"]),
                    ("stg_fixture", shape["fixtures"]),
                    ("stg_player_fixture", shape["player_fixture_rows"]),
                ):
                    connection.execute(
                        f"insert into {table} select ?, range from range(?)",
                        [name, count],
                    )
                connection.execute(
                    "insert into stg_gameweek select ?, 'run', timestamp '2026-09-27', "
                    "range + 1, true from range(?)",
                    [name, shape["finished_gameweeks"]],
                )
                for table in SERVED:
                    # Only season is filled, so an overridden shape keeps
                    # loading as long as it keeps that column.
                    connection.execute(
                        f"insert into {table} (season) select ? from range(?)",
                        [name, shape[table]],
                    )
        monkeypatch.setattr(publish_served, "DATABASE", database)

        s3 = FakeS3(previous)
        monkeypatch.setattr(publish_served.boto3, "client", lambda *_a, **_k: s3)
        monkeypatch.setattr(sys, "argv", ["publish_served.py", *args])
        return publish_served.main(), s3

    return run


def errors(captured: str) -> list[str]:
    """The ::error:: lines of a run's output."""
    return [line for line in captured.splitlines() if line.startswith("::error::")]


def assert_refused(result) -> None:
    code, s3 = result
    assert code == 1
    assert s3.uploads == {}


def assert_published(result) -> None:
    code, s3 = result
    assert code == 0
    assert set(s3.uploads) == {
        *(f"served/{table}.parquet" for table in SERVED),
        MANIFEST_KEY,
    }
