-- Layer: stg
-- Tests: stg_fixture
-- Asserts: each staged fixture's season agrees with its own kickoff date, and a
--          fixture_id the source carries in two seasons stays two seasons in
--          staging.
-- Origin: new in #37 — fixture_id is reassigned every season, so ids 1-380
--         repeat in every season's capture
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#37 AC3'}) }}

-- The kickoff date is the independent witness. Season is parsed from the key
-- (season_from_filename), so checking it against the same macro would only
-- compare it with itself; the payload's own kickoff_time says which season a
-- fixture was played in. A row labelled with the wrong season — the ported
-- season read as the live `season` var, say — kicks off outside its label's
-- window and fails here.
--
-- The window runs from 1 June of a season's first year to 31 August of its
-- second: wide enough for any real Premier League season (2019-20 finished on
-- 26 July 2020), still disjoint from the next season's matches, so a one-season
-- mislabel is always caught. A fixture with no kickoff yet has no date to
-- check; its season is pinned by the unit test on the key rule instead.
--
-- The merge check fails when a fixture_id whose source kickoffs fall in two
-- seasons is staged under fewer seasons. It needs such an id to exist, so it
-- also fails when the source holds two seasons but shares no id between them.
-- A build with one season (no history_root) has nothing to merge and passes.

with staged_window as (

    select
        season,
        run_id,
        fixture_id,
        kickoff_time,
        make_date(cast(left(season, 4) as integer), 6, 1)     as window_start,
        make_date(cast(left(season, 4) as integer) + 1, 9, 1) as window_end
    from {{ ref('stg_fixture') }}
    where kickoff_time is not null

),

source_spread as (

    -- Seasons each source fixture_id is played in, judged by kickoff alone:
    -- shifting back seven months puts the season boundary at 1 August.
    select
        cast(id as integer)                                         as fixture_id,
        count(distinct year(cast(kickoff_time as timestamp) - interval 7 month)) as seasons_by_kickoff
    from {{ source('fpl_raw', 'fixtures') }}
    where kickoff_time is not null
    group by 1

),

staged_spread as (

    select
        fixture_id,
        count(distinct season) as seasons_staged
    from {{ ref('stg_fixture') }}
    group by fixture_id

)

select
    season,
    run_id,
    fixture_id,
    'kickoff ' || cast(kickoff_time as varchar) || ' is outside season ' || season as failure
from staged_window
where kickoff_time < window_start
   or kickoff_time >= window_end

union all

select
    null,
    null,
    source_spread.fixture_id,
    'played in ' || source_spread.seasons_by_kickoff || ' seasons, staged under '
        || coalesce(staged_spread.seasons_staged, 0)
from source_spread
left join staged_spread
    on staged_spread.fixture_id = source_spread.fixture_id
where coalesce(staged_spread.seasons_staged, 0) < source_spread.seasons_by_kickoff

union all

select null, null, null, 'two seasons in the source but no fixture_id shared between them'
where (select count(distinct {{ season_from_filename() }})
       from {{ source('fpl_raw', 'fixtures') }}) > 1
  and not exists (select 1 from source_spread where seasons_by_kickoff > 1)
