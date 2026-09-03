-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_player
-- =============================================================================
--
-- Purpose:
--   Flattens the `elements` array of fpl-ingest's raw bootstrap-static
--   captures into one row per player. Typing and renaming only.
--
-- Grain:
--   One row per (fpl_id) *per captured object* — 1:1 with the raw source, so
--   a player contributes one row per bootstrap-static run. Selecting a single
--   capture is the served layer's job, not staging's.
--
-- Note:
--   `team` is deliberately not carried. Bootstrap-static states a player's
--   team as of the capture, and joining it onto historical fixtures at build
--   time is the known as-of bug this rebuild must not reintroduce.
-- =============================================================================

with raw as (

    select
        filename,
        unnest(elements) as e
    from {{ source('fpl_raw', 'bootstrap_static') }}

)

select
    -- Capture identity (see stg_player_fixture for the key layout)
    cast(str_split(filename, '/')[-3] as date) as extraction_date,
    str_split(filename, '/')[-2]               as run_id,
    strptime(
        split_part(str_split(filename, '/')[-2], '-', 1),
        '%Y%m%dT%H%M%SZ'
    )                                          as extracted_at,

    -- Keys
    cast(e.id as integer)                      as fpl_id,

    -- Identity
    cast(e.web_name as varchar)                as web_name

from raw
