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

select
    -- Capture identity, from the capture index (see int_admitted_capture)
    admitted.capture_key,
    admitted.season,
    admitted.extraction_date,
    admitted.run_id,
    admitted.extracted_at,
    admitted.observed_at,

    -- Keys
    cast(id as integer)                        as fixture_id,

    -- Schedule, null while unscheduled or postponed
    cast(event as integer)                     as gameweek,
    cast(kickoff_time as timestamp)            as kickoff_time,

    -- Sides
    cast(team_h as integer)                    as team_h_fpl_id,
    cast(team_a as integer)                    as team_a_fpl_id,

    -- Result, null until the match is played
    cast(team_h_score as integer)              as team_h_score,
    cast(team_a_score as integer)              as team_a_score,
    cast(finished as boolean)                  as finished,

    -- Difficulty, as it stood at this capture
    cast(team_h_difficulty as integer)         as team_h_difficulty,
    cast(team_a_difficulty as integer)         as team_a_difficulty

from (
    select {{ capture_key_from_filename() }} as capture_key, *
    from {{ source('fpl_raw', 'fixtures') }}
) as raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
