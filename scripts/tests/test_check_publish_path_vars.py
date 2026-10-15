"""CI fails when the publish path names a test-only var.

`problems` is the pure core of scripts/check_publish_path_vars.py: given the
text of scheduled_build.yml, it returns one message per test-only var the file
names, and CI's validate job fails when the list is non-empty (#190 D3). A
test-only var, such as `capture_cutoff`, narrows what a build reads; set on the
scheduled build, it would publish a truncated `served/`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from check_publish_path_vars import problems

REPO = Path(__file__).resolve().parents[2]

CLEAN = """\
      - name: Build, test and publish
        run: >-
          uv run dbt build
          --vars "{history_root: '$HISTORY_ROOT'}"
"""
WITH_CUTOFF = """\
      - name: Build, test and publish
        run: >-
          uv run dbt build
          --vars "{history_root: '$HISTORY_ROOT', capture_cutoff: '2026-09-15'}"
"""


@pytest.mark.unit
@pytest.mark.covers("#190 AC1")
def test_a_workflow_without_a_test_only_var_passes():
    assert problems(CLEAN) == []


@pytest.mark.unit
@pytest.mark.covers("#190 AC1")
def test_a_workflow_naming_the_cutoff_var_fails_naming_it():
    found = problems(WITH_CUTOFF)
    assert len(found) == 1
    assert "capture_cutoff" in found[0]


@pytest.mark.integration
@pytest.mark.covers("#190 AC1")
def test_the_scheduled_build_names_no_test_only_var():
    result = subprocess.run(
        [sys.executable, "scripts/check_publish_path_vars.py"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
