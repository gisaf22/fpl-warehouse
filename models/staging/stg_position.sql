-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_position
-- =============================================================================
--
-- Purpose:
--   Flattens the `element_types` array of fpl-ingest's raw bootstrap-static
--   captures into one row per position. Typing and renaming only.
--
-- Grain:
--   One row per (position_id) *per captured object* — 1:1 with the raw source,
--   so each position contributes one row per bootstrap-static run.
--
-- Naming:
--   FPL calls this entity an `element_type`; `position` is used throughout
--   this warehouse. stg_player.position_id refers to position_id here.
-- =============================================================================

with raw as (

    select
        filename,
        unnest(element_types) as p
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
    cast(p.id as integer)                      as position_id,

    -- Labels
    cast(p.singular_name as varchar)           as position_name,
    cast(p.singular_name_short as varchar)     as position_short_name

from raw
