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
--   One row per (round) *per captured object* — 1:1 with the raw source, so
--   each of the 38 gameweeks contributes one row per bootstrap-static run.
--   A round's `finished` / `data_checked` flags therefore differ between
--   captures; that is the point, and resolving to one capture is the served
--   layer's job.
--
-- Naming:
--   FPL calls this entity an `event`; the per-fixture history rows call the
--   same number `round`. `round` is used throughout this warehouse.
-- =============================================================================

with raw as (

    select
        filename,
        unnest(events) as ev
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
    cast(ev.id as integer)                     as round,

    -- Calendar
    cast(ev.deadline_time as timestamp)        as deadline_time,

    -- Lifecycle
    cast(ev.finished as boolean)               as finished,
    cast(ev.data_checked as boolean)           as data_checked,
    cast(ev.is_current as boolean)             as is_current

from raw
