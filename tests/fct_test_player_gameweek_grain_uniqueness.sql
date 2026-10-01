-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: exactly one row exists per (season, fpl_id, gameweek), so a double
--          gameweek is one row with fixture_count 2 rather than two rows.
-- Origin: new in Phase 2
-- Tier: unit
{{ config(tags=['unit']) }}

-- fct_player_gameweek must hold exactly one row per (season, fpl_id, gameweek). A double
-- gameweek is two fixtures folded into one row with fixture_count = 2, never
-- two rows.

select
    season,
    fpl_id,
    gameweek,
    count(*) as row_count
from {{ ref('fct_player_gameweek') }}
group by season, fpl_id, gameweek
having count(*) > 1
