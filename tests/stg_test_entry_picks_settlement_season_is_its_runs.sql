-- Layer: stg
-- Tests: stg_entry_picks_settlement
-- Asserts: each marker's season is the one season of the entry-picks captures
--          its run indexed for that gameweek. The marker's key and body carry
--          no season, so this is where a marker is placed in its season.
-- Origin: new in #216 (D2)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC7'}) }}

with run_seasons as (

    select
        run_id,
        cast(split_part(endpoint, '/', 3) as integer) as gameweek,
        list(distinct season order by season)         as seasons
    from {{ ref('base_capture_index') }}
    where split_part(endpoint, '/', 1) = 'entry-picks'
    group by run_id, gameweek

)

select markers.season, markers.gameweek, markers.run_id, run_seasons.seasons
from {{ ref('stg_entry_picks_settlement') }} as markers
left join run_seasons
    on run_seasons.run_id = markers.run_id
   and run_seasons.gameweek = markers.gameweek
where run_seasons.seasons is distinct from [markers.season]
