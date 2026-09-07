-- fct_player_gameweek must hold exactly one row per (season, fpl_id, round). A double
-- gameweek is two fixtures folded into one row with fixture_count = 2, never
-- two rows.

select
    season,
    fpl_id,
    round,
    count(*) as row_count
from {{ ref('fct_player_gameweek') }}
group by season, fpl_id, round
having count(*) > 1
