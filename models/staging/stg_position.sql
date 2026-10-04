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
        {{ capture_key_from_filename() }} as capture_key,
        unnest(element_types) as p
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
    cast(p.id as integer)                      as position_id,

    -- Labels
    cast(p.singular_name as varchar)           as position_name,
    cast(p.singular_name_short as varchar)     as position_short_name

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
