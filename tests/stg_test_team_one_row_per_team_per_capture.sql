-- Layer: stg
-- Tests: stg_team
-- Asserts: every bootstrap-static capture stages exactly one row per team it
--          lists, each with its team_code carried.
-- Origin: new in #38
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#38 AC1'}) }}

-- Compared per capture against the source's own `teams` array, so a team
-- missing from staging, a team staged twice, and a team with no team_code all
-- surface as a row here. The ported season's single capture is checked the
-- same way as each live capture.

with source_teams as (

    select
        {{ season_from_filename() }}   as season,
        str_split(filename, '/')[-2]   as run_id,
        cast(t.id as integer)          as team_fpl_id
    from (
        select filename, unnest(teams) as t
        from {{ source('fpl_raw', 'bootstrap_static') }}
    )

),

staged as (

    select
        season,
        run_id,
        team_fpl_id,
        count(*)                       as row_count,
        count(team_code)               as with_code
    from {{ ref('stg_team') }}
    group by season, run_id, team_fpl_id

)

select
    coalesce(source_teams.season, staged.season)           as season,
    coalesce(source_teams.run_id, staged.run_id)           as run_id,
    coalesce(source_teams.team_fpl_id, staged.team_fpl_id) as team_fpl_id,
    case
        when staged.team_fpl_id is null       then 'missing from staging'
        when source_teams.team_fpl_id is null then 'not in the capture'
        when staged.row_count > 1             then 'duplicated'
        else 'no team_code'
    end                                                    as failure
from source_teams
full outer join staged
    on  staged.season      = source_teams.season
    and staged.run_id      = source_teams.run_id
    and staged.team_fpl_id = source_teams.team_fpl_id
where staged.team_fpl_id is null
   or source_teams.team_fpl_id is null
   or staged.row_count > 1
   or staged.with_code < staged.row_count
