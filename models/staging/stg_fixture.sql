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
--   together with season, which each row reads from its own key.
-- =============================================================================

select
    -- Capture identity (see stg_player_fixture for the key layout)
    {{ season_from_filename() }} as season,
    cast(str_split(filename, '/')[-3] as date) as extraction_date,
    str_split(filename, '/')[-2]               as run_id,
    strptime(
        split_part(str_split(filename, '/')[-2], '-', 1),
        '%Y%m%dT%H%M%SZ'
    )                                          as extracted_at,

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

from {{ source('fpl_raw', 'fixtures') }}
