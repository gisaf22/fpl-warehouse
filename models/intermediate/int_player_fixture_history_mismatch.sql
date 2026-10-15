-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_player_fixture_history_mismatch
-- =============================================================================
--
-- Purpose:
--   Element-summary captures whose staged row count in stg_player_fixture
--   differs from their payload's history[] entry count (#175 G7).
--   int_test_player_fixture_history_mismatch_fails_hard fails the build on
--   any row.
--
-- Grain:
--   One row per mismatched capture_key: expected_rows is the payload's
--   history[] entry count, staged_rows its stg_player_fixture rows.
--
-- Rule:
--   An empty history[] expects 0 rows and passes, with no special case. A
--   full drop (entries, no rows) and a partial drop (some rows lost) are both
--   listed. #167's int_unstaged_admitted_capture sees only the first: a
--   capture that kept any row reads as staged there.
--
-- Not covered:
--   A capture with no payload, or one that does not parse, never reaches
--   stg_player_history_capture. int_unstaged_admitted_capture lists it.
-- =============================================================================

with staged as (

    select capture_key, count(*) as staged_rows
    from {{ ref('stg_player_fixture') }}
    group by capture_key

)

select
    captures.season,
    captures.run_id,
    captures.capture_key,
    captures.observed_at,
    captures.history_count               as expected_rows,
    coalesce(staged.staged_rows, 0)      as staged_rows
from {{ ref('stg_player_history_capture') }} as captures
left join staged
    on staged.capture_key = captures.capture_key
where captures.history_count is distinct from coalesce(staged.staged_rows, 0)
