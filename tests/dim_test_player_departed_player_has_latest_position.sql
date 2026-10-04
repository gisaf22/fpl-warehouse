-- Layer: dim
-- Tests: dim_player
-- Asserts: a player seen in an earlier capture of a season but absent from
--          that season's latest capture has a dim_player row, carrying the
--          position from the latest capture they appear in.
-- Origin: new in #41, modelled on int_test_season_roster_keeps_departed_player
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#41 AC1'}) }}

-- Non-vacuous on the fixture tree because of player 4's synthetic departure,
-- which stg_test_player_departure_present asserts is really there. This test
-- does not repeat that precondition.

with latest_capture as (

    select season, run_id
    from (select distinct season, run_id, observed_at from {{ ref('stg_player') }})
    qualify row_number() over (
        partition by season
        order by observed_at desc, run_id desc
    ) = 1

),

departed as (

    select distinct player.season, player.fpl_id
    from {{ ref('stg_player') }} as player
    where not exists (
        select 1
        from {{ ref('stg_player') }} as latest_player
        inner join latest_capture using (season, run_id)
        where latest_player.season = player.season
          and latest_player.fpl_id = player.fpl_id
    )

),

-- Each departed player's position in the latest capture they appear in.
last_appearance as (

    select player.season, player.fpl_id, player.position_id
    from {{ ref('stg_player') }} as player
    inner join departed using (season, fpl_id)
    qualify row_number() over (
        partition by player.season, player.fpl_id
        order by player.observed_at desc, player.run_id desc
    ) = 1

)

select
    last_appearance.season,
    last_appearance.fpl_id,
    last_appearance.position_id as expected_position_id,
    dim.position_id             as actual_position_id,
    case
        when dim.fpl_id is null then 'departed player has no dim_player row'
        else 'position is not the latest appearance''s'
    end as failure
from last_appearance
left join {{ ref('dim_player') }} as dim
    on dim.season = last_appearance.season
    and dim.fpl_id = last_appearance.fpl_id
where dim.fpl_id is null
   or dim.position_id is distinct from last_appearance.position_id
