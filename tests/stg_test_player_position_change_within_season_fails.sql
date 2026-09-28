-- Layer: stg
-- Tests: stg_player (the constant_per_key test on position_id)
-- Asserts: a player whose position differs between two captures of one
--          season fails the fixed-position check, which names that player
--          and both positions; a player whose position holds all season, and
--          an fpl_id with different positions in two seasons, do not fail.
-- Origin: new in #41
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#41 AC2'}) }}

-- No fixture player changes position, so the rule is exercised on inline rows
-- shaped like stg_player, through the same test schema.yml applies to it.
-- Key (2026-27, 2) moves DEF -> MID between captures. Key (2026-27, 1) holds
-- MID across three captures. fpl_id 3 is a GKP in 2025-26 and a FWD in
-- 2026-27 — two different people, since fpl_id is reassigned each season.

with failing as (

    {{ test_constant_per_key(
        model="(select * from (values
            ('2026-27', 1, 'r1', 3), ('2026-27', 1, 'r2', 3), ('2026-27', 1, 'r3', 3),
            ('2026-27', 2, 'r1', 2), ('2026-27', 2, 'r2', 3),
            ('2025-26', 3, 'r0', 1), ('2026-27', 3, 'r1', 4)
        ) as t(season, fpl_id, run_id, position_id))",
        column_name='position_id',
        key=['season', 'fpl_id']
    ) }}

),

expected as (

    select * from (values ('2026-27', 2)) as e(season, fpl_id)

)

select
    coalesce(failing.season, expected.season) as season,
    coalesce(failing.fpl_id, expected.fpl_id) as fpl_id,
    failing.fpl_id is not null                as reported_failing,
    expected.fpl_id is not null               as changes_position,
    failing.distinct_values                   as reported_values
from failing
full outer join expected
    on failing.season = expected.season
    and failing.fpl_id = expected.fpl_id
where failing.fpl_id is null
   or expected.fpl_id is null
   -- Both positions must be named, in either order.
   or not (failing.distinct_values like '%2%' and failing.distinct_values like '%3%')
