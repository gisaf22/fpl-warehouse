-- Layer: fct
-- Tests: as_of (macro) over literal market captures
-- Asserts: as of a deadline, each player gets their last capture strictly
--          before it: a capture exactly at the deadline, or after it, is never
--          returned, another season's capture is never returned, and a player
--          first captured after the deadline gets null.
-- Origin: new in #142
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#142 AC2'}) }}

-- Deadline 2026-09-04 17:30. Player 1 has a capture exactly at it, so the one
-- before it is the answer. Player 2 is first captured after it. Player 3's
-- answer is the later of two captures before it, and a 2025-26 capture of the
-- same fpl_id, later still, must not match. A missing or extra result row
-- fails too.

with captures (season, fpl_id, capture_key, observed_at, now_cost) as (
    values
        ('2026-27', 1, 'c1', timestamp '2026-09-01 19:00:00', 80),
        ('2026-27', 1, 'c2', timestamp '2026-09-04 17:30:00', 79),
        ('2026-27', 1, 'c3', timestamp '2026-09-06 19:00:00', 78),
        ('2026-27', 2, 'c4', timestamp '2026-09-05 07:00:00', 55),
        ('2026-27', 3, 'c5', timestamp '2026-08-29 19:00:00', 60),
        ('2026-27', 3, 'c6', timestamp '2026-08-31 20:00:00', 61),
        ('2025-26', 3, 'c7', timestamp '2026-09-03 12:00:00', 99)
),

requests (season, fpl_id, as_of_time) as (
    values
        ('2026-27', 1, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 2, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 3, timestamp '2026-09-04 17:30:00')
),

expected (season, fpl_id, capture_key, now_cost) as (
    values
        ('2026-27', 1, 'c1',                  80),
        ('2026-27', 2, cast(null as varchar), cast(null as integer)),
        ('2026-27', 3, 'c6',                  61)
),

actual as (
    {{ as_of('requests', 'captures', 'observed_at', ['capture_key', 'observed_at', 'now_cost']) }}
)

select
    coalesce(expected.fpl_id, actual.fpl_id) as fpl_id,
    expected.capture_key as expected_capture_key,
    actual.capture_key   as actual_capture_key,
    expected.now_cost    as expected_now_cost,
    actual.now_cost      as actual_now_cost
from expected
full outer join actual
    on  actual.season = expected.season
    and actual.fpl_id = expected.fpl_id
where expected.fpl_id is null
   or actual.fpl_id is null
   or actual.capture_key is distinct from expected.capture_key
   or actual.now_cost    is distinct from expected.now_cost
