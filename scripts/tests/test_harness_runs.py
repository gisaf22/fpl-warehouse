"""The Python test harness collects and runs a traced, tiered test."""

import pytest


@pytest.mark.unit
def test_a_traced_unit_test_runs():
    assert True
