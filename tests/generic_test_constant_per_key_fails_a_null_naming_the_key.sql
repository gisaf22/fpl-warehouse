-- Layer: generic
-- Tests: constant_per_key (tests/generic/constant_per_key.sql)
-- Asserts: a key whose column is null in any row fails, and the failure
--          returns that key; a key with no null does not fail.
-- Origin: new in #69
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#69 AC5'}) }}

-- Stands in for stg_player.player_code: one row per capture, keyed by
-- (season, fpl_id). Key (2026-27, 2) is null in one of its two captures, the
-- case AC5 exists for, and must be reported even though its other capture
-- carries a code. Every other key is clean.

with failing as (

    {{ test_constant_per_key(
        model="(select * from (values
            ('2026-27', 1, 'r1', 100), ('2026-27', 1, 'r2', 100),
            ('2026-27', 2, 'r1', 200), ('2026-27', 2, 'r2', null),
            ('2025-26', 2, 'r0', 900)
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
    expected.fpl_id is not null               as has_a_null
from failing
full outer join expected
    on failing.season = expected.season
    and failing.fpl_id = expected.fpl_id
where failing.fpl_id is null
   or expected.fpl_id is null
