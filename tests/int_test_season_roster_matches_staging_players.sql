-- Layer: int
-- Tests: int_season_roster
-- Asserts: each season's roster holds exactly the fpl_ids seen in any of that
--          season's bootstrap-static captures, no more and no fewer, each
--          carrying the web_name of its newest capture.
-- Origin: new in #69
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#69 AC1'}) }}

-- Group membership is required: this test ref()s stg_player and
-- int_season_roster, both access: private. See CLAUDE.md, "Served contract".
--
-- Compared both ways, per season: a staged player missing from the roster
-- and a roster row with no staged player both fail, and so does a roster
-- web_name that is not the newest capture's spelling. A duplicate roster row
-- is AC3's grain test, not this one.

with newest as (

    select season, fpl_id, web_name
    from (
        select
            season,
            fpl_id,
            web_name,
            row_number() over (
                partition by season, fpl_id
                order by extracted_at desc, run_id desc
            ) as capture_rank
        from {{ ref('stg_player') }}
    )
    where capture_rank = 1

),

roster as (

    select distinct season, fpl_id, web_name
    from {{ ref('int_season_roster') }}

)

select
    coalesce(newest.season, roster.season) as season,
    coalesce(newest.fpl_id, roster.fpl_id) as fpl_id,
    case
        when roster.fpl_id is null then 'seen in staging, missing from the roster'
        when newest.fpl_id is null then 'in the roster, never seen in staging'
        else 'roster web_name ' || coalesce(roster.web_name, 'NULL')
            || ' is not the newest capture''s ' || coalesce(newest.web_name, 'NULL')
    end as failure
from newest
full outer join roster
    on roster.season = newest.season
    and roster.fpl_id = newest.fpl_id
where roster.fpl_id is null
   or newest.fpl_id is null
   or roster.web_name is distinct from newest.web_name
