-- Layer: dim
-- Tests: as_of (macro) over literal fixture schedule history rows
-- Asserts: as of a moment, each fixture gets the row opened strictly before
--          it: a row opened exactly at the moment is never returned, and an
--          open row opened weeks before it is returned, not nulled.
-- Origin: new in #153
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#153 AC2'}) }}

-- Moment 2026-09-12 12:30. Fixture 1's second row opens exactly at it, so the
-- first row is the answer. Fixture 2's only row opened at the first capture,
-- 2026-08-29, and is still open: a schedule does not go stale, so no max_age
-- may null it. A missing or extra result row fails too.

with history_rows (season, fixture_id, valid_from, valid_to, kickoff_time, capture_key) as (
    values
        ('2026-27', 1, timestamp '2026-09-01 19:00:00', timestamp '2026-09-12 12:30:00', timestamp '2026-09-19 14:00:00', 'c1'),
        ('2026-27', 1, timestamp '2026-09-12 12:30:00', null,                            timestamp '2026-09-20 13:00:00', 'c2'),
        ('2026-27', 2, timestamp '2026-08-29 01:23:00', null,                            timestamp '2026-09-27 14:00:00', 'c3')
),

-- The other tracked fields, which the lookup returns, are null throughout.
history as (
    select
        *,
        cast(null as integer) as gameweek,
        cast(null as integer) as team_h_fpl_id,
        cast(null as integer) as team_a_fpl_id,
        cast(null as integer) as team_h_difficulty,
        cast(null as integer) as team_a_difficulty
    from history_rows
),

requests (season, fixture_id, as_of_time) as (
    values
        ('2026-27', 1, timestamp '2026-09-12 12:30:00'),
        ('2026-27', 2, timestamp '2026-09-12 12:30:00')
),

expected (season, fixture_id, capture_key, kickoff_time) as (
    values
        ('2026-27', 1, 'c1', timestamp '2026-09-19 14:00:00'),
        ('2026-27', 2, 'c3', timestamp '2026-09-27 14:00:00')
),

actual as (
    {{ as_of('requests', 'history', 'valid_from',
             ['valid_from', 'valid_to', 'gameweek', 'kickoff_time',
              'team_h_fpl_id', 'team_a_fpl_id', 'team_h_difficulty',
              'team_a_difficulty', 'capture_key'],
             keys=['season', 'fixture_id']) }}
)

select
    coalesce(expected.fixture_id, actual.fixture_id) as fixture_id,
    expected.capture_key  as expected_capture_key,
    actual.capture_key    as actual_capture_key,
    expected.kickoff_time as expected_kickoff_time,
    actual.kickoff_time   as actual_kickoff_time
from expected
full outer join actual
    on  actual.season     = expected.season
    and actual.fixture_id = expected.fixture_id
where expected.fixture_id is null
   or actual.fixture_id is null
   or actual.capture_key  is distinct from expected.capture_key
   or actual.kickoff_time is distinct from expected.kickoff_time
