"""CI's validate job exempts exactly the non-capture staging models (#216 AC21).

Every payload staging model must declare a relationships test from capture_key
to int_admitted_capture. Three staging models are built from files that are not
captures and have no capture_key: stg_run (run manifests), and
stg_entry_picks_settlement and stg_manager_panel (the picks settlement marker
and the manager panel file, #216 D2, D10). They are exempt by name, and nothing
else is.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github/workflows/ci.yml"
STEP = "Check every staging model tests capture_key against admission"


def exempt_set() -> set[str]:
    for job in yaml.safe_load(WORKFLOW.read_text())["jobs"].values():
        for step in job.get("steps", []):
            if step.get("name") == STEP:
                match = re.search(r"^\s*EXEMPT = (\{.*\})\s*$", step["run"], re.MULTILINE)
                assert match, f"no EXEMPT set in {STEP!r}"
                return ast.literal_eval(match.group(1))
    raise AssertionError(f"no step named {STEP!r} in {WORKFLOW.name}")


@pytest.mark.unit
@pytest.mark.covers("#216 AC21")
def test_exactly_the_non_capture_staging_models_are_exempt():
    assert exempt_set() == {"stg_run", "stg_entry_picks_settlement", "stg_manager_panel"}
