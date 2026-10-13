-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: every season with an admitted bootstrap-static capture has exactly
--          38 rows, gameweeks 1..38, so a season admitted but never staged
--          fails the build instead of publishing without it.
-- Origin: new in #169 (#163 S11 amended)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#169 AC2'}) }}

-- The season list comes from admission, not from stg_gameweek: dim_gameweek
-- is built from stg_gameweek, so a season staging dropped would be absent
-- from both and a staged list could never fail (S11).
with admitted_seasons as (

    select distinct season
    from {{ ref('int_admitted_capture') }}
    where endpoint = 'bootstrap-static'

),

per_season as (

    select
        season,
        count(*)                 as row_count,
        count(distinct gameweek) as distinct_gameweeks,
        min(gameweek)            as min_gameweek,
        max(gameweek)            as max_gameweek
    from {{ ref('dim_gameweek') }}
    group by season

)

select
    admitted_seasons.season,
    per_season.row_count,
    per_season.distinct_gameweeks,
    per_season.min_gameweek,
    per_season.max_gameweek
from admitted_seasons
left join per_season
    on per_season.season = admitted_seasons.season
where per_season.season is null
   or per_season.row_count <> 38
   or per_season.distinct_gameweeks <> 38
   or per_season.min_gameweek <> 1
   or per_season.max_gameweek <> 38
