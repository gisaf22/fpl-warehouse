-- Layer: generic
-- Tests: constant_per_key (tests/generic/constant_per_key.sql)
-- Asserts: a key whose column takes two values across its rows fails, and the
--          failure returns that key with both values; a key that holds one
--          value, and the same fpl_id holding a different value in another
--          season, do not fail.
-- Origin: new in #69
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#69 AC6'}) }}

-- Key (2026-27, 2) changes code between captures: 200 then 201. Key
-- (2026-27, 1) is constant across three captures. fpl_id 3 holds 300 in
-- 2025-26 and 301 in 2026-27 — two different people, since fpl_id is
-- reassigned each season, so it is not a change and must not fail.

with failing as (

    {{ test_constant_per_key(
        model="(select * from (values
            ('2026-27', 1, 'r1', 100), ('2026-27', 1, 'r2', 100), ('2026-27', 1, 'r3', 100),
            ('2026-27', 2, 'r1', 200), ('2026-27', 2, 'r2', 201),
            ('2025-26', 3, 'r0', 300), ('2026-27', 3, 'r1', 301)
        ) as t(season, fpl_id, run_id, player_code))",
        column_name='player_code',
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
    expected.fpl_id is not null               as has_two_values,
    failing.distinct_values                   as reported_values
from failing
full outer join expected
    on failing.season = expected.season
    and failing.fpl_id = expected.fpl_id
where failing.fpl_id is null
   or expected.fpl_id is null
   -- Both codes must be named, in either order.
   or not (failing.distinct_values like '%200%' and failing.distinct_values like '%201%')
