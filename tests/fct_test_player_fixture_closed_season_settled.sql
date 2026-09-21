-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: every season fct_player_fixture treats as closed is backed by its
--          own calendar — its latest bootstrap-static capture reports every
--          round finished and data_checked — every row of it reads
--          is_ratified = true, and the live season is never listed as closed.
-- Origin: new in the 2025-26 history port, Step 3
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration']) }}

-- Group membership is required, not cosmetic: this test ref()s stg_gameweek,
-- which is access: private to warehouse_internal.

-- The closed-season override in fct_player_fixture sets is_ratified = true
-- without consulting event-status, which has nothing to say about a finished
-- season. This test is what stops that from being a bare assertion: the
-- season's own calendar, as last captured, must agree that it is over.
--
-- Everything is per season. A closed season is checked against its own
-- captures only, never against another season's.
--
-- Until a closed season's data is loaded, the calendar check has no rows to
-- examine and passes; the live-season guard still applies.
--
-- Fails with one row per problem.

with closed_rows as (

    select
        season,
        count(*)                                  as fixture_rows,
        count(*) filter (where not is_ratified
                           or is_ratified is null) as unratified_rows
    from {{ ref('fct_player_fixture') }}
    where list_contains({{ closed_seasons_list() }}, season)
    group by season

),

latest_capture as (

    select season, run_id
    from (
        select
            season,
            run_id,
            row_number() over (
                partition by season
                order by extracted_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, extracted_at from {{ ref('stg_gameweek') }})
    )
    where capture_rank = 1

),

calendar as (

    select
        gameweek.season,
        count(*)                                          as rounds,
        count(*) filter (where not (gameweek.finished
                                    and gameweek.data_checked)) as unsettled_rounds
    from {{ ref('stg_gameweek') }} as gameweek
    inner join latest_capture using (season, run_id)
    group by gameweek.season

)

select
    closed_rows.season,
    'closed season has no bootstrap-static calendar' as failure
from closed_rows
left join calendar using (season)
where calendar.season is null

union all

select
    calendar.season,
    'closed season calendar has ' || calendar.unsettled_rounds
        || ' of ' || calendar.rounds || ' rounds not finished and data_checked'
from closed_rows
inner join calendar using (season)
where calendar.unsettled_rounds > 0

union all

select
    season,
    unratified_rows || ' closed-season rows are not is_ratified = true'
from closed_rows
where unratified_rows > 0

union all

select
    '{{ var('season') }}',
    'the live season is listed in closed_seasons'
where list_contains({{ closed_seasons_list() }}, '{{ var('season') }}')
