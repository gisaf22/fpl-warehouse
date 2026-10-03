"""The published manifest keeps its shape: every field present, of its type.

The manifest is part of the served contract, and a consumer reads it without
reading the parquet. #76 was a field that silently changed shape — `seasons`
published as [season, count] pairs — which no test saw because none looked at
it. The harness is shared: see publish_harness.py.
"""

from __future__ import annotations

import pytest

from publish_harness import (
    CLOSED,
    LIVE,
    assert_published,
    make_publish,
    manifest,
    season,
)


@pytest.fixture
def published_manifest(tmp_path, monkeypatch) -> dict:
    """The manifest a normal two-season publish writes."""
    run = make_publish(tmp_path, monkeypatch)
    previous = manifest(**{CLOSED: season(10, 38), LIVE: season(10, 4)})

    result = run({CLOSED: season(10, 38), LIVE: season(10, 5)}, previous)

    assert_published(result)
    _, s3 = result
    return s3.published_manifest()


def is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def is_count(value) -> bool:
    # bool is an int subclass in Python; a count is never true or false.
    return isinstance(value, int) and not isinstance(value, bool)


# The whole manifest, field by field. A field added, removed or changed in
# shape must change this table in the same pull request — that edit is the
# review point for a change to the served contract.
FIELDS = {
    "run_id": lambda v: isinstance(v, str),
    "built_at": lambda v: isinstance(v, str),
    "git_sha": lambda v: isinstance(v, str),
    "seasons": is_str_list,
    "row_counts": lambda v: isinstance(v, dict)
    and all(isinstance(t, str) and is_count(n) for t, n in v.items()),
    "row_counts_by_season": lambda v: isinstance(v, dict)
    and all(
        isinstance(t, str)
        and isinstance(by_season, dict)
        and all(isinstance(s, str) and is_count(n) for s, n in by_season.items())
        for t, by_season in v.items()
    ),
    "restated_seasons": is_str_list,
    "published_without_baseline": lambda v: isinstance(v, bool),
    "contract_version": is_count,
    "columns": lambda v: isinstance(v, dict)
    and all(
        isinstance(t, str)
        and isinstance(cols, list)
        and all(
            isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) for x in c)
            for c in cols
        )
        for t, cols in v.items()
    ),
}


# AC1 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#76 AC1")
def test_the_manifest_seasons_are_the_plain_list_of_season_strings(
    published_manifest,
):
    assert published_manifest["seasons"] == [CLOSED, LIVE]


# AC2 -------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("#76 AC2")
def test_the_manifest_has_exactly_its_fields(published_manifest):
    assert set(published_manifest) == set(FIELDS)


@pytest.mark.integration
@pytest.mark.covers("#76 AC2")
@pytest.mark.parametrize("field", list(FIELDS))
def test_every_manifest_field_has_its_type(published_manifest, field):
    value = published_manifest[field]
    assert FIELDS[field](value), f"{field} has the wrong shape: {value!r}"

