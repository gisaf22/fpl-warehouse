"""The publish is refused when a season shrinks against the previous publish.

Each test builds a small warehouse file holding just what publish_served.py
reads (staging for the expectation, the two fct tables for the export), stands
a fake S3 client in for boto3 that serves a chosen previous manifest, and runs
main() as the workflow does. "Refused" means exit 1 with nothing uploaded;
"proceeds" means exit 0 with both tables and the manifest uploaded.
"""

from __future__ import annotations

import io
import json
import sys

import duckdb
import pytest
from botocore.exceptions import ClientError

import publish_served

CLOSED = "2025-26"
LIVE = "2026-27"
MANIFEST_KEY = "served/_manifest.json"


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
    players: int, rounds: int, fixture: int | None = None, gameweek: int | None = None
) -> dict:
    """One season's staging shape and served row counts.

    Served counts default to exactly the staging expectation (players x
    rounds), which clears the per-season floor in both tables.
    """
    expected = players * rounds
    return {
        "players": players,
        "rounds": rounds,
        "fct_player_fixture": expected if fixture is None else fixture,
        "fct_player_gameweek": expected if gameweek is None else gameweek,
    }


def manifest(**by_season: dict) -> dict:
    """A previous manifest recording each season's served counts."""
    by_table = {
        table: {name: shape[table] for name, shape in by_season.items()}
        for table in publish_served.TABLES
    }
    return {
        "run_id": "previous",
        "seasons": sorted(by_season),
        "row_counts": {
            table: sum(counts.values()) for table, counts in by_table.items()
        },
        "row_counts_by_season": by_table,
    }


@pytest.fixture
def publish(tmp_path, monkeypatch):
    """Build a warehouse from `build`, then run main() against `previous`."""

    project = tmp_path / "dbt_project.yml"
    project.write_text(f"vars:\n  season: '{LIVE}'\n")
    monkeypatch.setattr(publish_served, "PROJECT_FILE", project)
    monkeypatch.setattr(publish_served, "OUT_DIR", tmp_path / "served")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    def run(
        build: dict[str, dict], previous: dict | bytes | None, args: list[str] = ()
    ):
        database = tmp_path / "warehouse.duckdb"
        database.unlink(missing_ok=True)
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                "create table stg_player (season varchar, fpl_id integer)"
            )
            connection.execute(
                "create table stg_gameweek (season varchar, run_id varchar, "
                "extracted_at timestamp, round integer, finished boolean)"
            )
            for table in publish_served.TABLES:
                connection.execute(
                    f"create table {table} (season varchar, row_number integer)"
                )
            for name, shape in build.items():
                connection.execute(
                    "insert into stg_player select ?, range from range(?)",
                    [name, shape["players"]],
                )
                connection.execute(
                    "insert into stg_gameweek select ?, 'run', timestamp '2026-09-27', "
                    "range + 1, true from range(?)",
                    [name, shape["rounds"]],
                )
                for table in publish_served.TABLES:
                    connection.execute(
                        f"insert into {table} select ?, range from range(?)",
                        [name, shape[table]],
                    )
        monkeypatch.setattr(publish_served, "DATABASE", database)

        s3 = FakeS3(previous)
        monkeypatch.setattr(publish_served.boto3, "client", lambda *_a, **_k: s3)
        monkeypatch.setattr(sys, "argv", ["publish_served.py", *args])
        return publish_served.main(), s3

    return run


def assert_refused(result) -> None:
    code, s3 = result
    assert code == 1
    assert s3.uploads == {}


def assert_published(result) -> None:
    code, s3 = result
    assert code == 0
    assert set(s3.uploads) == {
        "served/fct_player_fixture.parquet",
        "served/fct_player_gameweek.parquet",
        MANIFEST_KEY,
    }


# AC1 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC1")
def test_a_season_lost_upstream_of_staging_is_refused(publish, capsys):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38)}, previous)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    for table in publish_served.TABLES:
        assert any(
            table in line and LIVE in line and "40" in line and " 0 " in line
            for line in errors
        ), f"no error names {table}, {LIVE}, the previous 40 and the new 0: {errors}"


@pytest.mark.unit
@pytest.mark.covers("#63 AC1")
def test_a_season_that_loses_some_rows_while_clearing_its_floor_is_refused(
    publish, capsys
):
    # A round of captures vanished upstream: staging expects 3 rounds, not 4,
    # so the floor passes at 30 while the last publish served 40.
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 3)}, previous)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any(
        "fct_player_gameweek" in line and LIVE in line and "40" in line and "30" in line
        for line in errors
    ), errors


@pytest.mark.unit
@pytest.mark.covers("#63 AC1")
def test_a_closed_season_that_shrinks_is_refused(publish, capsys):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    # One row fewer in one table, well inside that table's 15% floor.
    result = publish(
        {CLOSED: season(10, 38, fixture=379), LIVE: season(10, 4)}, previous
    )

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any(
        "fct_player_fixture" in line
        and CLOSED in line
        and "380" in line
        and "379" in line
        for line in errors
    ), errors


# AC2 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC2")
def test_a_named_restatement_lets_that_season_shrink_and_is_recorded(publish, capsys):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 3)}, previous, ["--restate", LIVE]
    )

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["restated_seasons"] == [LIVE]
    log = capsys.readouterr().out
    assert any(
        "restate" in line.lower() and LIVE in line for line in log.splitlines()
    ), log


@pytest.mark.unit
@pytest.mark.covers("#63 AC2")
def test_a_restatement_does_not_cover_a_season_it_does_not_name(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish(
        {CLOSED: season(10, 38, fixture=379), LIVE: season(10, 3)},
        previous,
        ["--restate", LIVE],
    )

    assert_refused(result)


@pytest.mark.unit
@pytest.mark.covers("#63 AC2")
def test_a_publish_without_a_restatement_records_none(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["restated_seasons"] == []


# AC3 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC3")
def test_a_season_published_for_the_first_time_is_not_held_to_a_previous_count(publish):
    previous = manifest(**{CLOSED: season(10, 38)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 1)}, previous)

    assert_published(result)


@pytest.mark.unit
@pytest.mark.covers("#63 AC3")
def test_a_season_published_for_the_first_time_is_still_held_to_its_floor(publish):
    previous = manifest(**{CLOSED: season(10, 38)})

    # 30 of an expected 40 is 25% short, below fct_player_gameweek's 2% floor.
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4, gameweek=30)}, previous
    )

    assert_refused(result)


# AC4 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_a_missing_previous_manifest_is_refused_and_named(publish, capsys):
    result = publish({CLOSED: season(10, 38), LIVE: season(10, 4)}, None)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any("manifest" in line and "NoSuchKey" in line for line in errors), errors


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
@pytest.mark.parametrize(
    "body",
    [b"not json", json.dumps({"run_id": "previous"}).encode()],
    ids=["not JSON", "no per-season counts"],
)
def test_an_unreadable_previous_manifest_is_refused_and_named(publish, capsys, body):
    result = publish({CLOSED: season(10, 38), LIVE: season(10, 4)}, body)

    assert_refused(result)
    errors = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("::error::")
    ]
    assert any("manifest" in line for line in errors), errors


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_publishing_without_a_baseline_proceeds_when_explicitly_overridden(publish):
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4)}, None, ["--without-baseline"]
    )

    assert_published(result)


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_publishing_without_a_baseline_is_recorded_in_the_manifest_and_log(
    publish, capsys
):
    result = publish(
        {CLOSED: season(10, 38), LIVE: season(10, 4)}, None, ["--without-baseline"]
    )

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["published_without_baseline"] is True
    log = capsys.readouterr().out
    assert any("without-baseline" in line for line in log.splitlines()), log


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_a_publish_with_a_baseline_records_no_baseline_override(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)
    _, s3 = result
    assert s3.published_manifest()["published_without_baseline"] is False


@pytest.mark.unit
@pytest.mark.covers("#63 AC4")
def test_a_previous_manifest_written_before_restatements_existed_is_accepted(publish):
    # Today's published manifest: per-season counts, no restated_seasons or
    # published_without_baseline keys. The first publish after this change
    # reads exactly this shape.
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})
    assert "restated_seasons" not in previous

    result = publish({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)


# AC5 -------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.covers("#63 AC5")
def test_a_build_where_every_season_grows_or_holds_proceeds(publish):
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = publish({CLOSED: season(10, 38), LIVE: season(11, 5)}, previous)

    assert_published(result)
