-- Layer: int
-- Tests: int_manager_gameweek_status, stg_entry_picks_settlement
-- Asserts: for every marked gameweek, the grid holds exactly as many managers
--          as the marker's `entries`: the managers ingest vouched for are the
--          managers the warehouse accounts for.
-- Origin: new in #216 (D2, D11)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC2'}) }}

select
    markers.season,
    markers.gameweek,
    markers.entries                 as marker_entries,
    count(distinct grid.entry_id)   as grid_managers
from {{ ref('stg_entry_picks_settlement') }} as markers
left join {{ ref('int_manager_gameweek_status') }} as grid
    on grid.season = markers.season
   and grid.gameweek = markers.gameweek
group by markers.season, markers.gameweek, markers.entries
having count(distinct grid.entry_id) <> markers.entries
