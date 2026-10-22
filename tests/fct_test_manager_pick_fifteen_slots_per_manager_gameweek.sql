-- Layer: fct
-- Tests: fct_manager_pick
-- Asserts: every manager-gameweek has exactly the slots 1..15, once each:
--          eleven starters (1-11) and four on the bench (12-15).
-- Origin: new in #216 (D9, D11)
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#216 AC8'}) }}

select
    season,
    entry_id,
    gameweek,
    count(*)                                  as picks,
    count(distinct slot)                      as slots,
    count(*) filter (where slot between 1 and 11)  as starters,
    count(*) filter (where slot between 12 and 15) as bench
from {{ ref('fct_manager_pick') }}
group by season, entry_id, gameweek
having count(*) <> 15
    or count(distinct slot) <> 15
    or count(*) filter (where slot between 1 and 11) <> 11
    or count(*) filter (where slot between 12 and 15) <> 4
