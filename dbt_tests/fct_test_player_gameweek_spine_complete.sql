-- fct_player_gameweek must be exactly one row per spine key: no
-- (season, fpl_id, round)
-- missing, and none invented beyond the spine.
--
-- A missing row is the original bug this rebuild exists to fix — it silently
-- shifts every rolling window computed downstream, because the gap is
-- indistinguishable from a gameweek that never happened.

with spine as (

    select season, fpl_id, round from {{ ref('int_player_gameweek_spine') }}

),

agg as (

    select season, fpl_id, round from {{ ref('fct_player_gameweek') }}

)

select
    spine.season,
    spine.fpl_id,
    spine.round,
    'missing_from_fct' as failure
from spine
left join agg using (season, fpl_id, round)
where agg.fpl_id is null

union all

select
    agg.season,
    agg.fpl_id,
    agg.round,
    'not_in_spine' as failure
from agg
left join spine using (season, fpl_id, round)
where spine.fpl_id is null
