-- Layer: int
-- Tests: int_player_gameweek_spine
-- Asserts: each season's spine is exactly the season roster crossed with the
--          rounds its latest bootstrap-static capture reports as finished —
--          no player or round missing, none extra, none duplicated.
-- Origin: new in #70
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#70 AC1'}) }}

-- Group membership is required: this test ref()s int_player_gameweek_spine,
-- int_season_roster and stg_gameweek, all access: private. See CLAUDE.md,
-- "Served contract".
--
-- The expected grid is built from the roster and the calendar, never from the
-- spine itself, so a spine that drops a player or a round fails here. Compared
-- with `except all` both ways, per season: a missing player, a player the
-- roster lacks, a missing or extra round and a duplicated row all fail. A
-- season with no finished round expects no rows, so its roster players are
-- correctly absent.

with latest_capture as (

    -- The same per-season capture int_player_gameweek_spine takes rounds from.
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

finished_rounds as (

    select calendar.season, calendar.round
    from {{ ref('stg_gameweek') }} as calendar
    inner join latest_capture using (season, run_id)
    where calendar.finished

),

expected as (

    select roster.season, roster.fpl_id, finished_rounds.round
    from {{ ref('int_season_roster') }} as roster
    inner join finished_rounds using (season)

),

spine as (

    select season, fpl_id, round
    from {{ ref('int_player_gameweek_spine') }}

),

missing as (

    select * from expected
    except all
    select * from spine

),

unexpected as (

    select * from spine
    except all
    select * from expected

)

select season, fpl_id, round, 'roster player missing this finished round in the spine' as failure
from missing

union all

select season, fpl_id, round, 'spine row not in roster x finished rounds' as failure
from unexpected
