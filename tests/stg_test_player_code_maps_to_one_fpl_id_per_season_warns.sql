-- Layer: stg
-- Tests: stg_player
-- Asserts: within a season, each player_code maps to one fpl_id. Player
--          status history is joined as of a time by (season, fpl_id), which
--          relies on that one-to-one (observed for all 209 captures to
--          2026-10-08, #123).
-- Origin: new in #126
-- Tier: integration. Warn severity: the build passes and the warning names
--       each code and its fpl_ids.
{{ config(group='warehouse_internal', tags=['integration'], severity='warn', meta={'covers': '#126 AC7'}) }}

select
    season,
    player_code,
    list(distinct fpl_id order by fpl_id) as fpl_ids,
    'player_code maps to more than one fpl_id' as warning
from {{ ref('stg_player') }}
group by season, player_code
having count(distinct fpl_id) > 1
