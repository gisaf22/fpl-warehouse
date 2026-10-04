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
        {{ capture_key_from_filename() }} as capture_key,
        unnest(teams) as t
    from {{ source('fpl_raw', 'bootstrap_static') }}

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
    cast(t.id as integer)                      as team_fpl_id,

    -- Identity
    cast(t.code as integer)                    as team_code,
    cast(t.name as varchar)                    as team_name,
    cast(t.short_name as varchar)              as team_short_name,

    -- Rating, null where the source reports none
    cast(t.strength as integer)                as strength

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
