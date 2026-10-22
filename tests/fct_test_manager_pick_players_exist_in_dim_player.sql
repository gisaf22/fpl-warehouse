-- Layer: fct
-- Tests: fct_manager_pick
-- Asserts: every picked player is in dim_player for the same season.
-- Origin: new in #216 (D11)
-- Tier: e2e. The fixture tree's players are six of the live season's, and a
--          real squad picks fifteen, so this runs against live S3 only (#216
--          open decision on the fixture's player scope).
{{ config(tags=['e2e'], meta={'covers': '#216 AC12'}) }}

select picks.season, picks.entry_id, picks.gameweek, picks.slot, picks.fpl_id
from {{ ref('fct_manager_pick') }} as picks
left join {{ ref('dim_player') }} as players
    on players.season = picks.season
   and players.fpl_id = picks.fpl_id
where players.fpl_id is null
