-- Layer: dim
-- Tests: player_status_as_of (macro)
-- Asserts: as of a deadline, each player gets the row containing their last
--          capture before it: a row opened by a capture exactly at the
--          deadline, or after it, is never returned, and a player first
--          captured after the deadline gets null.
-- Origin: new in #128
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#128 AC1'}) }}

-- Deadline 2026-09-04 17:30. Player 1's d row opens exactly at it, so the a
-- row before it is the answer. Player 2's i row opens after it. Player 3 has
-- no row before it. A missing or extra result row fails too.

with history (season, fpl_id, valid_from, valid_to, status) as (
    values
        ('2026-27', 1, timestamp '2026-09-01 19:00:00', timestamp '2026-09-04 17:30:00', 'a'),
        ('2026-27', 1, timestamp '2026-09-04 17:30:00', timestamp '2026-09-06 19:00:00', 'd'),
        ('2026-27', 1, timestamp '2026-09-06 19:00:00', null,                            'a'),
        ('2026-27', 2, timestamp '2026-09-01 19:00:00', timestamp '2026-09-05 07:00:00', 'a'),
        ('2026-27', 2, timestamp '2026-09-05 07:00:00', null,                            'i'),
        ('2026-27', 3, timestamp '2026-09-05 07:00:00', null,                            'a')
),

requests (season, fpl_id, as_of_time) as (
    values
        ('2026-27', 1, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 2, timestamp '2026-09-04 17:30:00'),
        ('2026-27', 3, timestamp '2026-09-04 17:30:00')
),

expected (season, fpl_id, valid_from, status) as (
    values
        ('2026-27', 1, timestamp '2026-09-01 19:00:00', 'a'),
        ('2026-27', 2, timestamp '2026-09-01 19:00:00', 'a'),
        ('2026-27', 3, cast(null as timestamp),         cast(null as varchar))
),

actual as (
    {{ player_status_as_of('requests', history='history') }}
)

select
    coalesce(expected.fpl_id, actual.fpl_id) as fpl_id,
    expected.valid_from as expected_valid_from,
    actual.valid_from   as actual_valid_from,
    expected.status     as expected_status,
    actual.status       as actual_status
from expected
full outer join actual
    on  actual.season = expected.season
    and actual.fpl_id = expected.fpl_id
where expected.fpl_id is null
   or actual.fpl_id is null
   or actual.valid_from is distinct from expected.valid_from
   or actual.status     is distinct from expected.status
