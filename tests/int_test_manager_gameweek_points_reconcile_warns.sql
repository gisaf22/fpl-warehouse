-- Layer: int
-- Tests: int_manager_gameweek_points
-- Asserts: on every captured manager-gameweek, chip weeks included, the sum
--          over the 15 picks of multiplier x the player's gameweek points
--          (fct_player_gameweek, a blank gameweek counting 0) equals FPL's own
--          entry_history.points; the transfer cost is not in it. Warns; the
--          scheduled build's job summary and an annotation name each
--          difference (D13).
-- Origin: new in #216 (D7 as amended by O3, D13). Held on 13,090 of 13,090
--          live captures, chip weeks included (2026-27 GW1-7, 2026-10-22).
-- Tier: e2e
{{ config(group='warehouse_internal', tags=['e2e'], severity='warn', meta={'covers': '#216 AC13'}) }}

select season, entry_id, gameweek, fpl_points, rebuilt_points
from {{ ref('int_manager_gameweek_points') }}
where rebuilt_points is distinct from fpl_points
