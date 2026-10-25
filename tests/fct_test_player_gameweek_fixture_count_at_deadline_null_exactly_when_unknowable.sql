-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: fixture_count_at_deadline is NULL exactly where the gameweek has no
--          staged capture before its deadline, the player has no status row
--          before it, or the season has no fixtures-schedule row before it,
--          and non-NULL everywhere else.
-- Origin: new in #221 (D4)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#221 AC2'}) }}

-- The rule is read straight from the three dimensions, with no as-of macro, so
-- the model's lookup is not checked against itself. On the fixture tree every
-- 2025-26 row and 2026-27 GW1-2 are NULL (no capture precedes those
-- deadlines), and GW3-4 are not. No fixture player is first captured after a
-- computable deadline, and every season's fixtures history begins with its
-- bootstrap-static history, so the second and third NULL arms are pinned by
-- the model's unit test, not here.
--
-- The last check keeps the test from passing vacuously: every season must
-- have rows, and both a NULL and a non-NULL row must be expected somewhere.

with gameweeks as (

    select season, gameweek, deadline_time, last_capture_before_deadline_at
    from {{ ref('dim_gameweek') }}

),

checked as (

    select
        player_gameweek.season,
        player_gameweek.fpl_id,
        player_gameweek.gameweek,
        player_gameweek.fixture_count_at_deadline,
        gameweeks.last_capture_before_deadline_at is null
            or not exists (
                select 1
                from {{ ref('dim_player_status_history') }} as status
                where status.season = player_gameweek.season
                  and status.fpl_id = player_gameweek.fpl_id
                  and status.valid_from < gameweeks.deadline_time
            )
            or not exists (
                select 1
                from {{ ref('dim_fixture_schedule_history') }} as schedule
                where schedule.season = player_gameweek.season
                  and schedule.valid_from < gameweeks.deadline_time
            ) as expect_null
    from {{ ref('fct_player_gameweek') }} as player_gameweek
    left join gameweeks
        on gameweeks.season = player_gameweek.season
       and gameweeks.gameweek = player_gameweek.gameweek

)

select season, fpl_id, gameweek, fixture_count_at_deadline,
    case when expect_null then 'non-NULL where the count is unknowable'
         else 'NULL where the count is knowable'
    end as failure
from checked
where expect_null = (fixture_count_at_deadline is not null)

union all

select null, null, null, null,
    'no row expects NULL, or none expects a value'
where not exists (select 1 from checked where expect_null)
   or not exists (select 1 from checked where not expect_null)

union all

select seasons.season, null, null, null, 'season has no fct_player_gameweek row'
from (select distinct season from gameweeks) as seasons
where seasons.season not in (select season from checked)
