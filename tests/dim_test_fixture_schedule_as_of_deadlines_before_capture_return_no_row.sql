-- Layer: dim
-- Tests: as_of (macro) over dim_fixture_schedule_history
-- Asserts: as of every 2025-26 deadline and the 2026-27 gameweek 1 and 2
--          deadlines, all of which predate their season's first capture, no
--          fixture gets a schedule.
-- Origin: new in #153
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#153 AC4'}) }}

-- Literal seasons on purpose: the claim is about capture history. 2025-26's
-- single capture is from the end of the season, after every deadline;
-- 2026-27's began on 2026-08-29, after its gameweek 2 deadline. The "has no
-- ..." checks keep the test from passing on an empty request set.

with deadlines as (

    select season, gameweek as deadline_gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    where season = '2025-26'
       or (season = '2026-27' and gameweek in (1, 2))
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

as_of as (
    {{ as_of('requests', ref('dim_fixture_schedule_history'), 'valid_from',
             ['valid_from', 'capture_key'], keys=['season', 'fixture_id']) }}
)

select 'schedule returned before the first capture' as failure,
    season, deadline_gameweek, fixture_id
from as_of
where valid_from is not null or capture_key is not null

union all

select 'has no 2025-26 deadlines', null, null, null
where not exists (select 1 from deadlines where season = '2025-26')

union all

select 'has no 2026-27 gameweek 1 and 2 deadlines', null, null, null
where (select count(*) from deadlines where season = '2026-27') <> 2

union all

select 'has no fixtures for those deadlines', season, null, null
from (values ('2025-26'), ('2026-27')) as seasons (season)
where not exists (select 1 from requests where requests.season = seasons.season)
