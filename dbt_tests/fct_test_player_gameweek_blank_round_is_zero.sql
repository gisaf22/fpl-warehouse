-- A gameweek in which a player has no fixture must appear as a row with
-- fixture_count = 0 — never as an absent row.
--
-- This is the blank-gameweek invariant stated directly, rather than inferred
-- from the spine-completeness and fixture_count tests. It holds for a true
-- blank gameweek (the player's team has no fixture in the round) and for the
-- mechanically identical case of a player carrying no history row for a round
-- they were not registered for.
--
-- Fails with one row per spine key that has no fixtures and is either absent
-- from the aggregate or present with a non-zero count.

with blank_keys as (

    select
        spine.season,
        spine.fpl_id,
        spine.round
    from {{ ref('int_player_gameweek_spine') }} as spine
    left join {{ ref('fct_player_fixture') }} as fct
        on fct.season = spine.season
       and fct.fpl_id = spine.fpl_id
       and fct.round  = spine.round
    group by spine.season, spine.fpl_id, spine.round
    having count(fct.fixture_id) = 0

)

select
    blank_keys.season,
    blank_keys.fpl_id,
    blank_keys.round,
    agg.fixture_count
from blank_keys
left join {{ ref('fct_player_gameweek') }} as agg using (season, fpl_id, round)
where agg.fpl_id is null
   or agg.fixture_count <> 0
