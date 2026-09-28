"""Collection-time rules every Python test must meet, or the run fails.

Each test declares exactly one tier (`unit` or `integration`) and at least one
`covers("#<issue> AC<n>")` marker tracing it to the acceptance criterion it
proves. These mirror the dbt suite: CI's tier-tag check rejects a dbt test with
no tier or two, and a test with no trace proves nothing anyone asked for.

`strict_markers` in pyproject.toml already rejects a misspelled marker name.
This hook covers what that cannot see: a marker that is absent, or a `covers`
whose argument is malformed.
"""

from __future__ import annotations

import re

import pytest

TIERS = ("unit", "integration")
COVERS_FORMAT = re.compile(r"#\d+ AC\d+")


def _problems(item: pytest.Item) -> list[str]:
    problems = []

    tiers = [tier for tier in TIERS if item.get_closest_marker(tier)]
    if len(tiers) != 1:
        problems.append(
            f"has tier markers {tiers or 'none'}; expected exactly one of "
            f"{' / '.join(TIERS)}"
        )

    covers = list(item.iter_markers("covers"))
    if not covers:
        problems.append('has no covers("#<issue> AC<n>") marker')
    for marker in covers:
        if (
            len(marker.args) != 1
            or marker.kwargs
            or not isinstance(marker.args[0], str)
            or not COVERS_FORMAT.fullmatch(marker.args[0])
        ):
            given = ", ".join(
                [repr(a) for a in marker.args]
                + [f"{k}={v!r}" for k, v in marker.kwargs.items()]
            )
            problems.append(
                f'has covers({given}); expected covers("#<issue> AC<n>"), '
                f'e.g. covers("#64 AC1")'
            )

    return problems


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    errors = [
        f"{item.nodeid} {problem}"
        for item in items
        for problem in _problems(item)
    ]
    if errors:
        raise pytest.UsageError(
            "tests fail the tracing/tier rules:\n  " + "\n  ".join(errors)
        )
