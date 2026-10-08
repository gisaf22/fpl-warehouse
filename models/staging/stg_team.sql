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

-- Fields come through declared_records, which selects only the columns
-- declared at `$.teams[*]` in sources.yml (#115): an undeclared field fails
-- the build rather than escaping the presence test.
with raw as (

    {{ declared_records('bootstrap_static', '$.teams[*]') }}

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
    cast(raw."id" as integer)                  as team_fpl_id,

    -- Identity
    cast(raw."code" as integer)                as team_code,
    cast(raw."name" as varchar)                as team_name,
    cast(raw."short_name" as varchar)          as team_short_name,

    -- Rating, null where the source reports none
    cast(raw."strength" as integer)            as strength

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
