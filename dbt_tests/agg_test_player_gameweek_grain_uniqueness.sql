-- agg_player_gameweek must hold exactly one row per (fpl_id, round). A double
-- gameweek is two fixtures folded into one row with fixture_count = 2, never
-- two rows.

select
    fpl_id,
    round,
    count(*) as row_count
from {{ ref('agg_player_gameweek') }}
group by fpl_id, round
having count(*) > 1
