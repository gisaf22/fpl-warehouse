-- Layer: fct
-- Tests: fct_manager_pick, fct_player_gameweek
-- Asserts: every pick from gameweek 3 on, bench included, has a
--          fct_player_gameweek row on (season, fpl_id, gameweek) whose
--          fixture_count_at_deadline is not NULL.
-- Origin: new in #221 (D6). A picked player was listed by FPL before the
--         deadline, so a NULL there is a defect. GW1-2 are exempt: no capture
--         precedes their deadlines (D4).
-- Tier: e2e. The fixture tree's players are six of the live season's, and a
--          real squad picks fifteen, so this runs against live S3 only (#216
--          D15): in the scheduled build and on live-tests dispatches, not on a
--          pull request.
{{ config(tags=['e2e'], meta={'covers': '#221 AC9'}) }}

-- The join is many-to-one: fct_player_gameweek is unique on the key, so a pick
-- matches at most one row. A pick that matches none fails as well.

select picks.season, picks.entry_id, picks.gameweek, picks.slot, picks.fpl_id,
    case when player_gameweek.fpl_id is null then 'no fct_player_gameweek row'
         else 'fixture_count_at_deadline is NULL'
    end as failure
from {{ ref('fct_manager_pick') }} as picks
left join {{ ref('fct_player_gameweek') }} as player_gameweek
    on player_gameweek.season = picks.season
   and player_gameweek.fpl_id = picks.fpl_id
   and player_gameweek.gameweek = picks.gameweek
where picks.gameweek >= 3
  and (player_gameweek.fpl_id is null
       or player_gameweek.fixture_count_at_deadline is null)
