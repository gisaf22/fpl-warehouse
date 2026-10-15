-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_player_history_capture
-- =============================================================================
--
-- Purpose:
--   One row per admitted element-summary capture, holding its `history`
--   array whole and the array's entry count (#175 G7). This is the one read
--   of the element-summary source: stg_player_fixture unnests `history` from
--   this table rather than reading the source again, and
--   int_player_fixture_history_mismatch checks that it staged one row per
--   entry. A second scan only to count would double the element-summary
--   read, which is most of the build's time.
--
-- Grain:
--   One row per capture_key. A capture with an empty history[] (a player yet
--   to play) has a row here with history_count 0, where stg_player_fixture
--   has none.
--
-- Source:
--   fpl_raw.element_summary at the payload root, read through
--   declared_records (#115). `history` is a list holding only the fields
--   declared at `$.history[*]`, so nothing downstream can read an undeclared
--   one.
--
-- Capture identity:
--   As stg_player_fixture: every capture column comes from
--   int_admitted_capture (#104), so only admitted captures are staged.
-- =============================================================================

with raw as (

    {{ declared_records('element_summary', '$') }}

)

select
    admitted.capture_key,
    admitted.season,
    admitted.extraction_date,
    admitted.run_id,
    admitted.extracted_at,
    admitted.observed_at,
    len(raw."history")  as history_count,
    raw."history"       as history
from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
