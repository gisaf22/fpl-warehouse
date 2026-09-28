"""The Python test harness collects and runs a traced, tiered test."""

import pytest


@pytest.mark.unit
@pytest.mark.covers("#64 AC1")
def test_a_traced_unit_test_runs():
    assert True
