-- Layer: dim
-- Tests: as_of (macro) over dim_fixture_schedule_history
-- Asserts: for every fixture and every deadline of its season, the as-of
--          schedule equals the fixture's last staged capture strictly before
--          the deadline; a fixture with no capture before it gets no row.
-- Origin: new in #153
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#153 AC3'}) }}

-- The oracle is read from stg_fixture, independently of the history model:
-- the fixture's latest capture with observed_at strictly before the deadline,
-- run_id breaking a repeat. Each deadline is the one in the latest capture, as
-- FPL can move it (#80).
--
-- The last check keeps the test from passing vacuously: some fixture's as-of
-- schedule must differ between two deadlines, so a lookup that returned the
-- open row for every deadline fails. On the fixture tree that is fixtures 44,
-- 78 and 81, rescheduled at the 2026-09-06 capture between the gameweek 3 and
-- 4 deadlines, and the 31 from 161, rescheduled at 2026-09-14 between
-- gameweek 4 and 5.

with deadlines as (

    select season, gameweek as deadline_gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

requests as (

    select fixtures.season, fixtures.fixture_id, deadlines.deadline_gameweek,
        deadlines.deadline_time as as_of_time
    from (select distinct season, fixture_id from {{ ref('stg_fixture') }}) as fixtures
    inner join deadlines on deadlines.season = fixtures.season

),

capture_before as (

    select
        requests.season, requests.fixture_id, requests.as_of_time,
        captures.observed_at,
        struct_pack(
            gameweek          := captures.gameweek,
            kickoff_time      := captures.kickoff_time,
            team_h_fpl_id     := captures.team_h_fpl_id,
            team_a_fpl_id     := captures.team_a_fpl_id,
            team_h_difficulty := captures.team_h_difficulty,
            team_a_difficulty := captures.team_a_difficulty
        ) as schedule
    from requests
    inner join {{ ref('stg_fixture') }} as captures
        on  captures.season      = requests.season
        and captures.fixture_id  = requests.fixture_id
        and captures.observed_at < requests.as_of_time
    qualify row_number() over (
        partition by requests.season, requests.fixture_id, requests.as_of_time
        order by captures.observed_at desc, captures.run_id desc
    ) = 1

),

as_of as (
    {{ as_of('requests', ref('dim_fixture_schedule_history'), 'valid_from',
             ['valid_from', 'valid_to', 'gameweek', 'kickoff_time',
              'team_h_fpl_id', 'team_a_fpl_id', 'team_h_difficulty',
              'team_a_difficulty', 'capture_key'],
             keys=['season', 'fixture_id']) }}
),

checked as (

    select
        as_of.season, as_of.fixture_id, as_of.deadline_gameweek, as_of.as_of_time,
        as_of.valid_from,
        case when as_of.valid_from is not null then struct_pack(
            gameweek          := as_of.gameweek,
            kickoff_time      := as_of.kickoff_time,
            team_h_fpl_id     := as_of.team_h_fpl_id,
            team_a_fpl_id     := as_of.team_a_fpl_id,
            team_h_difficulty := as_of.team_h_difficulty,
            team_a_difficulty := as_of.team_a_difficulty
        ) end as as_of_schedule,
        capture_before.observed_at as last_before,
        capture_before.schedule    as capture_schedule
    from as_of
    left join capture_before
        on  capture_before.season     = as_of.season
        and capture_before.fixture_id = as_of.fixture_id
        and capture_before.as_of_time = as_of.as_of_time

)

select season, fixture_id, deadline_gameweek, as_of_time, valid_from,
    as_of_schedule::varchar as as_of_schedule, last_before,
    capture_schedule::varchar as capture_schedule,
    case
        when valid_from >= as_of_time  then 'row opened at or after the deadline'
        when last_before is null       then 'row returned with no capture before the deadline'
        when valid_from is null        then 'no row although a capture precedes the deadline'
        else                                'schedule differs from the last capture before the deadline'
    end as failure
from checked
where valid_from >= as_of_time
   or (last_before is null and valid_from is not null)
   or (last_before is not null and valid_from is null)
   or as_of_schedule is distinct from capture_schedule

union all

select null, null, null, null, null, null, null, null,
    'no fixture schedule differs between two deadlines'
where not exists (
    select 1 from checked
    where as_of_schedule is not null
    group by season, fixture_id
    having count(distinct as_of_schedule) > 1
)
