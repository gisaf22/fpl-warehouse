-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_entry_picks_settlement
-- =============================================================================
--
-- Purpose:
--   One row per picks settlement marker (GLOSSARY.md; #216 D2, D3): the
--   gameweek ingest vouches is captured for every panel manager.
--
-- Season (#216 D14):
--   The marker's key and body carry no season, so it is taken from the
--   marker's run: the season of that run's indexed entry-picks captures for
--   the gameweek. A run that indexed none gives a null season, and one that
--   indexed two seasons gives two rows; the not_null and unique tests on
--   (season, gameweek) fail the build on either. gisaf22/fpl-ingest#127 puts
--   the season in the key.
--
-- Not a capture: there is no capture_key, and CI's capture_key check exempts
-- this model by name (#216 AC21).
-- =============================================================================

with markers as (

    select
        cast("event" as integer)            as gameweek,
        cast(entries as integer)            as entries,
        run_id,
        cast(recorded_at as timestamp)      as recorded_at
    from {{ source('fpl_raw', 'entry_picks_settlement') }}

),

run_seasons as (

    select distinct
        run_id,
        cast(split_part(endpoint, '/', 3) as integer) as gameweek,
        season
    from {{ ref('base_capture_index') }}
    where split_part(endpoint, '/', 1) = 'entry-picks'

)

select
    run_seasons.season,
    markers.gameweek,
    markers.entries,
    markers.run_id,
    markers.recorded_at
from markers
left join run_seasons
    on run_seasons.run_id = markers.run_id
   and run_seasons.gameweek = markers.gameweek
