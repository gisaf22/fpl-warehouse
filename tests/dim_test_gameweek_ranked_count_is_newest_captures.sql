-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: every served ranked_count is events[].ranked_count from the
--          season's newest staged bootstrap-static capture, by observed_at
--          with run_id breaking a repeat.
-- Origin: new in #219 (D2). In the fixture GW2's oldest capture (08-29) reads
--         9,907,576 and its newest (09-14) 9,904,815, so a model that takes
--         the oldest capture fails.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC3'}) }}

with newest as (

    select season, gameweek, ranked_count
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

oldest as (

    select season, gameweek, ranked_count
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at, run_id
    ) = 1

)

select
    served.season,
    served.gameweek,
    newest.ranked_count as newest_capture_ranked_count,
    served.ranked_count as served_ranked_count
from {{ ref('dim_gameweek') }} as served
left join newest
    on newest.season = served.season
   and newest.gameweek = served.gameweek
where served.ranked_count is not null
  and served.ranked_count is distinct from newest.ranked_count

{% if target.name == 'fixtures' %}
union all
select 'no served ranked_count whose oldest capture differs in the fixture', null, null, null
where not exists (
    select 1
    from {{ ref('dim_gameweek') }} as served
    inner join oldest using (season, gameweek)
    where served.ranked_count is not null
      and oldest.ranked_count <> served.ranked_count
)
{% endif %}
