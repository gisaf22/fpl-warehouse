-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_fixture
-- =============================================================================
--
-- Purpose:
--   Flattens fpl-ingest's raw fixtures captures into one row per fixture.
--   Typing and renaming only.
--
-- Grain:
--   One row per (season, fixture_id) *per captured object* — 1:1 with the raw
--   source, so each fixture contributes one row per fixtures run. Selecting a
--   single capture is the model layer's job, not staging's.
--
-- gameweek / kickoff_time:
--   Nullable and never coalesced. FPL withdraws both from a postponed or
--   unscheduled fixture and restores them when it is rescheduled, so a capture
--   taken in between reports the fixture with neither. It still exists.
--
-- fixture_id:
--   Reassigned every season (1-380 repeat), so it identifies a fixture only
--   together with season, which each row takes from the capture index.
-- =============================================================================

-- Fields come through declared_records, which selects only the columns
-- declared at `$[*]` in sources.yml (#115): an undeclared field fails the
-- build rather than escaping the presence test.
with raw as (

    {{ declared_records('fixtures', '$[*]') }}

)

select
    -- Capture identity, from the capture index (see int_admitted_capture)
    admitted.capture_key,
    admitted.season,
    admitted.extraction_date,
    admitted.run_id,
    admitted.extracted_at,
    admitted.observed_at,

    -- Keys
    cast(raw."id" as integer)                  as fixture_id,

    -- Schedule, null while unscheduled or postponed
    cast(raw."event" as integer)               as gameweek,
    cast(raw."kickoff_time" as timestamp)      as kickoff_time,

    -- Sides
    cast(raw."team_h" as integer)              as team_h_fpl_id,
    cast(raw."team_a" as integer)              as team_a_fpl_id,

    -- Result, null until the match is played
    cast(raw."team_h_score" as integer)        as team_h_score,
    cast(raw."team_a_score" as integer)        as team_a_score,
    cast(raw."finished" as boolean)            as finished,

    -- Difficulty, as it stood at this capture
    cast(raw."team_h_difficulty" as integer)   as team_h_difficulty,
    cast(raw."team_a_difficulty" as integer)   as team_a_difficulty

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
