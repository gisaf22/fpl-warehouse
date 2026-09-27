-- Layer: dim
-- Tests: dim_team
-- Asserts: every season holds exactly 20 teams.
-- Origin: new in #40
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#40 AC4'}) }}

-- A Premier League season has 20 clubs; any other count is a defect. Seasons
-- are taken from staging, not from dim_team itself, so a season the dimension
-- lost entirely scores 0 and fails rather than going unchecked.

with seasons as (

    select distinct season
    from {{ ref('stg_team') }}

),

counted as (

    select
        season,
        count(*) as team_count
    from {{ ref('dim_team') }}
    group by season

)

select
    coalesce(seasons.season, counted.season) as season,
    coalesce(counted.team_count, 0)          as team_count
from seasons
full outer join counted
    on counted.season = seasons.season
where coalesce(counted.team_count, 0) <> 20
