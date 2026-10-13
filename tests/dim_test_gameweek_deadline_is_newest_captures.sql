-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: each gameweek serves the deadline_time of its newest staged
--          capture by observed_at, run_id breaking a repeat, and every staged
--          gameweek has a row.
-- Origin: new in #169 (#163 S2, #104). In the fixture tree 2026-27 GW17-20
--         moved earlier at the 2026-09-14 capture (GW17 13:30 -> 11:00 on
--         2026-12-26), so the oldest capture's value or the greatest
--         deadline_time differs from the newest.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#169 AC5'}) }}

with newest as (

    select season, gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at desc, run_id desc
    ) = 1

)

select
    coalesce(newest.season, served.season)     as season,
    coalesce(newest.gameweek, served.gameweek) as gameweek,
    newest.deadline_time                       as newest_capture_deadline,
    served.deadline_time                       as served_deadline
from newest
full outer join {{ ref('dim_gameweek') }} as served
    on served.season = newest.season
    and served.gameweek = newest.gameweek
where served.deadline_time is distinct from newest.deadline_time
