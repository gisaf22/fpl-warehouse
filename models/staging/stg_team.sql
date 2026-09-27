-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_team
-- =============================================================================
--
-- Purpose:
--   Flattens the `teams` array of fpl-ingest's raw bootstrap-static captures
--   into one row per team. Typing and renaming only.
--
-- Grain:
--   One row per (team_fpl_id) *per captured object* — 1:1 with the raw source,
--   so each team contributes one row per bootstrap-static run. Selecting a
--   single capture is the dimension's job, not staging's.
--
-- team_code:
--   FPL's `code`, the club's identifier across seasons — `id` is reassigned
--   every season. Carried as a plain column, like stg_player.player_code.
--
-- strength:
--   Nullable, and deliberately not coalesced: 2026-27 reports it null for
--   every team, and a 0 would read as a real rating. Staged, not served
--   (decision 4 on #32).
-- =============================================================================

with raw as (

    select
        filename,
        unnest(teams) as t
    from {{ source('fpl_raw', 'bootstrap_static') }}

)

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
    cast(t.id as integer)                      as team_fpl_id,

    -- Identity
    cast(t.code as integer)                    as team_code,
    cast(t.name as varchar)                    as team_name,
    cast(t.short_name as varchar)              as team_short_name,

    -- Rating, null where the source reports none
    cast(t.strength as integer)                as strength

from raw
