-- Layer: stg
-- Tests: stg_team
-- Asserts: a team whose strength is null in the source is staged with a null
--          strength — never 0, never dropped.
-- Origin: new in #38 — 2026-27 reports every team's strength as null (decision
--         4 on #32)
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#38 AC2'}) }}

-- Also fails when the source holds no null strength at all: the checked-in
-- live captures are all null, and a tree without one would pass this test
-- without testing anything.

with source_null as (

    select
        {{ season_from_filename() }}   as season,
        str_split(filename, '/')[-2]   as run_id,
        cast(t.id as integer)          as team_fpl_id
    from (
        select filename, unnest(teams) as t
        from {{ source('fpl_raw', 'bootstrap_static') }}
    )
    where t.strength is null

)

select
    source_null.season,
    source_null.run_id,
    source_null.team_fpl_id,
    case
        when staged.team_fpl_id is null then 'dropped'
        else 'strength reads ' || cast(staged.strength as varchar)
    end as failure
from source_null
left join {{ ref('stg_team') }} as staged
    on  staged.season      = source_null.season
    and staged.run_id      = source_null.run_id
    and staged.team_fpl_id = source_null.team_fpl_id
where staged.team_fpl_id is null
   or staged.strength is not null

union all

select null, null, null, 'no null strength in the source to test against'
where not exists (select 1 from source_null)
