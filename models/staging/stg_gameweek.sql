-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_gameweek
-- =============================================================================
--
-- Purpose:
--   Flattens the `events` array of fpl-ingest's raw bootstrap-static captures
--   into one row per gameweek. Typing and renaming only.
--
-- Grain:
--   One row per (gameweek) *per captured object* — 1:1 with the raw source, so
--   each of the 38 gameweeks contributes one row per bootstrap-static run.
--   A gameweek's `finished` / `data_checked` flags therefore differ between
--   captures; that is the point, and resolving to one capture is the served
--   layer's job.
--
-- Naming:
--   FPL calls this entity an `event`; the per-fixture history rows call the
--   same number `round`. This warehouse calls it `gameweek` from staging onward
--   (#89, #101).
-- =============================================================================

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(events) as ev
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
    cast(ev.id as integer)                     as gameweek,

    -- Calendar
    cast(ev.deadline_time as timestamp)        as deadline_time,

    -- Lifecycle
    cast(ev.finished as boolean)               as finished,
    cast(ev.data_checked as boolean)           as data_checked,
    cast(ev.is_current as boolean)             as is_current

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
