-- Layer: int
-- Tests: int_season_roster
-- Asserts: exactly one row exists per (season, fpl_id).
-- Origin: new in #69, modelled on fct_test_player_gameweek_grain_uniqueness
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#69 AC3'}) }}

select
    season,
    fpl_id,
    count(*) as row_count
from {{ ref('int_season_roster') }}
group by season, fpl_id
having count(*) > 1
