"""Fail CI when the publish path names a test-only var.

A test-only var narrows what a build reads: `capture_cutoff` (#190) stages only
captures dated before a date, for #183's memory experiments. Set on the
scheduled build, it would publish a truncated `served/`. So
`.github/workflows/scheduled_build.yml`, the one workflow that publishes, must
not name one at all, not even in a comment (#190 D3).

Run from the repo root: `python scripts/check_publish_path_vars.py`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PUBLISH_WORKFLOW = Path(".github/workflows/scheduled_build.yml")
TEST_ONLY_VARS = ("capture_cutoff",)


def problems(workflow_text: str) -> list[str]:
    return [
        f"{PUBLISH_WORKFLOW} names the test-only var {var}; it must never reach "
        "a build that publishes served/ (#190)"
        for var in TEST_ONLY_VARS
        if re.search(rf"\b{var}\b", workflow_text)
    ]


def main() -> int:
    found = problems(PUBLISH_WORKFLOW.read_text())
    for problem in found:
        print(f"::error::{problem}")
    if not found:
        print(f"{PUBLISH_WORKFLOW} names no test-only var")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
