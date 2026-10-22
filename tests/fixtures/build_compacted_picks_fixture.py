#!/usr/bin/env python
"""Write tests/fixtures/compacted/fpl/entry-picks/ from the checked-in picks (#216 AC16).

Runs the real writer, scripts/compact_entry_picks.py, on tests/fixtures/raw
with a local destination, for two of the four marked gameweeks only: 2026-27
gameweeks 1 and 3. Gameweeks 2 and 4 (marked) and 5 (unmarked) stay in the raw
tail, so a fixture build reads entry-picks from both parquet and raw, and
stg_test_entry_picks_compacted_read_matches_raw compares the two.

Gameweek 3 holds 10187394's automatic subs, so the parquet carries a non-empty
`automatic_subs`; gameweek 1 holds only empty ones.

No S3: everything it reads and writes is under tests/fixtures. Run from the
repository root after build_manager_fixtures.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from compact_entry_picks import compact_gameweek  # noqa: E402

RAW = "tests/fixtures/raw"
DEST = "tests/fixtures/compacted"
SEASON = "2026-27"
COMPACTED = (1, 3)


def main() -> None:
    for gameweek in COMPACTED:
        result = compact_gameweek(SEASON, gameweek, RAW, DEST)
        if not result.ok:
            sys.exit(f"gameweek {gameweek}: {result.reason}")
        print(f"compacted {SEASON} gameweek {gameweek}")


if __name__ == "__main__":
    main()
