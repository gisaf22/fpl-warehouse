-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: per-fixture binary measures — starts and clean_sheets — never exceed
--          the round's fixture_count, and no count measure is negative.
-- Origin: ported from tests/availability/sql/fct_test_monotonicity.sql
--         (supersedes tests/availability/sql/fct_test_starts_lte_appearances.sql
--          and tests/performance/sql/fct_test_cs_pct_range.sql, which asserted
--          the same ceiling against the retired feature tables)
-- Tier: unit
{{ config(tags=['unit']) }}

-- The original expressed the ceiling as starts <= appearances, with the
-- appearance count a derived feature. At this grain fixture_count *is* the
-- appearance count and is itself asserted against the real fixture rows by
-- fct_test_player_gameweek_fixture_count_matches, so the invariant becomes
-- starts <= fixture_count and holds across a double gameweek unchanged.
--
-- clean_sheets is the same shape: FPL states it 0 or 1 per fixture, so summing
-- across a round cannot exceed the number of fixtures. The retired
-- fct_test_cs_pct_range asserted this as a [0, 1] bound on a ratio whose
-- denominator was the same count.
--
-- The non-negativity clause replaces the original's sub_appearances >= 0
-- check: the derived sub-appearance column is gone, but a negative sum in a
-- count measure signals the same class of arithmetic or join fault.
--
-- total_points is deliberately NOT in that clause. FPL scoring is signed — a
-- yellow card is -1, an own goal or missed penalty -2, a red card -3, and
-- goals conceded -1 per 2 for defenders and keepers — so a player can finish a
-- round below zero without anything being wrong. This assertion originally
-- included it and failed on 6 legitimate rows on 2026-09-07: fpl_id 37 round 1
-- played 90 minutes (+2), conceded 4 (-2) and scored an own goal (-2) for -2.
-- Verified against fct_player_fixture, where 7 rows are negative and the
-- minimum is -2. The bound was wrong, not the data.

select
    season,
    fpl_id,
    round,
    fixture_count,
    starts,
    clean_sheets,
    minutes,
    total_points
from {{ ref('fct_player_gameweek') }}
where starts > fixture_count
   or clean_sheets > fixture_count
   or starts < 0
   or clean_sheets < 0
   or minutes < 0
