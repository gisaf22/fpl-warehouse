-- Layer: fct
-- Tests: as_of (macro) over literal market captures
-- Asserts: with max_age, a capture in [moment - max_age, moment) is used, the
--          boundary itself included; a latest capture older than that returns
--          null rather than an older one; and with max_age omitted the lookup
--          is unbounded.
-- Origin: new in #142 (P3)
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#142 AC6'}) }}

-- Moment 2026-09-04 17:30, max_age 24 hours, so the window opens at
-- 2026-09-03 17:30. Player 1's only capture is exactly at that boundary. Player
-- 2's is one microsecond before it. Player 3 has one capture outside and a
-- later one inside. Player 4's latest before the moment is outside, and its
-- capture at the moment itself does not count. Player 2 is asked again with
-- max_age omitted, where its capture must be returned. A missing or extra
-- result row fails too.

with captures (season, fpl_id, capture_key, observed_at, now_cost) as (
    values
        ('2026-27', 1, 'c1', timestamp '2026-09-03 17:30:00',        80),
        ('2026-27', 2, 'c2', timestamp '2026-09-03 17:29:59.999999', 55),
        ('2026-27', 3, 'c3', timestamp '2026-09-01 19:00:00',        60),
        ('2026-27', 3, 'c4', timestamp '2026-09-04 10:00:00',        61),
        ('2026-27', 4, 'c5', timestamp '2026-09-02 19:00:00',        45),
        ('2026-27', 4, 'c6', timestamp '2026-09-04 17:30:00',        46)
),

requests (season, fpl_id, as_of_time) as (
    values
        ('2026-27', 1, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 2, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 3, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 4, timestamp '2026-09-04 17:30:00')
),

unbounded_requests as (
    select * from requests where fpl_id = 2
),

expected (bounded, fpl_id, capture_key, now_cost) as (
    values
        (true,  1, 'c1',                  80),
        (true,  2, cast(null as varchar), cast(null as integer)),
        (true,  3, 'c4',                  61),
        (true,  4, cast(null as varchar), cast(null as integer)),
        (false, 2, 'c2',                  55)
),

bounded as (
    {{ as_of('requests', 'captures', 'observed_at', ['capture_key', 'now_cost'],
             max_age="interval '24 hours'") }}
),

unbounded as (
    {{ as_of('unbounded_requests', 'captures', 'observed_at', ['capture_key', 'now_cost']) }}
),

actual as (
    select true as bounded, fpl_id, capture_key, now_cost from bounded
    union all
    select false, fpl_id, capture_key, now_cost from unbounded
)

select
    coalesce(expected.bounded, actual.bounded) as bounded,
    coalesce(expected.fpl_id, actual.fpl_id)   as fpl_id,
    expected.capture_key as expected_capture_key,
    actual.capture_key   as actual_capture_key,
    expected.now_cost    as expected_now_cost,
    actual.now_cost      as actual_now_cost
from expected
full outer join actual
    on  actual.bounded = expected.bounded
    and actual.fpl_id  = expected.fpl_id
where expected.fpl_id is null
   or actual.fpl_id is null
   or actual.capture_key is distinct from expected.capture_key
   or actual.now_cost    is distinct from expected.now_cost
