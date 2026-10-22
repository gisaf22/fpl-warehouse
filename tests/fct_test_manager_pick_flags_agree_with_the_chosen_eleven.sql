-- Layer: fct
-- Tests: fct_manager_pick
-- Asserts: the automatic-sub flags agree with the chosen-eleven rule: every
--          player subbed in sits in slots 1-11, every player subbed out in
--          slots 12-15, and each manager-gameweek's chosen eleven (slot 1-11
--          rows not subbed in, plus the rows subbed out) is exactly 11 players.
-- Origin: new in #216 (D7 as amended by O4; AC9, added 2026-10-22)
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#216 AC9'}) }}

select
    season,
    entry_id,
    gameweek,
    count(*) filter (where is_auto_sub_in and slot > 11)          as subbed_in_on_bench,
    count(*) filter (where is_auto_sub_out and slot <= 11)        as subbed_out_in_eleven,
    count(*) filter (where (slot <= 11 and not is_auto_sub_in) or is_auto_sub_out) as chosen_eleven
from {{ ref('fct_manager_pick') }}
group by season, entry_id, gameweek
having count(*) filter (where is_auto_sub_in and slot > 11) > 0
    or count(*) filter (where is_auto_sub_out and slot <= 11) > 0
    or count(*) filter (where (slot <= 11 and not is_auto_sub_in) or is_auto_sub_out) <> 11
