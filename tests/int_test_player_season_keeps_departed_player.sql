-- Layer: int
-- Tests: int_player_season
-- Asserts: a player seen in an earlier capture of a season but absent from
--          that season's latest capture still has a roster row.
-- Origin: new in #69, modelled on
--         fct_test_player_gameweek_spine_covers_departed_players
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#69 AC2'}) }}

-- Non-vacuous on the fixture tree because of player 4's synthetic departure,
-- which stg_test_player_departure_present asserts is really there. This test
-- does not repeat that precondition.

with latest_capture as (

    select season, run_id
    from (
        select
            season,
            run_id,
            row_number() over (
                partition by season
                order by extracted_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, extracted_at from {{ ref('stg_player') }})
    )
    where capture_rank = 1

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

)

select
    departed.season,
    departed.fpl_id,
    'departed player has no roster row' as failure
from departed
left join {{ ref('int_player_season') }} as roster
    on roster.season = departed.season
    and roster.fpl_id = departed.fpl_id
where roster.fpl_id is null
