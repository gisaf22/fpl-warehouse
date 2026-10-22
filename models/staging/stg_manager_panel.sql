-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_manager_panel
-- =============================================================================
--
-- Purpose:
--   One row per manager on a season's panel, with their cohort (#216 D10,
--   O5), from fpl-ingest's panel file. `joined_gw` is not read: it is 1 for
--   every manager, and the join week comes from picks (D6).
--
-- Not a capture: there is no capture_key, and CI's capture_key check exempts
-- this model by name (#216 AC21).
-- =============================================================================

with panels as (

    select season, unnest(entries) as entry
    from {{ source('fpl_raw', 'manager_panel') }}

)

select
    cast(season as varchar)          as season,
    cast(entry.entry_id as integer)  as entry_id,
    cast(entry.cohort as varchar)    as cohort
from panels
