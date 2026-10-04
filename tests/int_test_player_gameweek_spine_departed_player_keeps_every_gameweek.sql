-- Layer: int
-- Tests: int_player_gameweek_spine
-- Asserts: a player seen in an earlier capture of a season but absent from
--          that season's latest capture has a spine row for every gameweek the
--          latest capture reports as finished.
-- Origin: new in #70, modelled on int_test_season_roster_keeps_departed_player
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#70 AC3'}) }}

-- Group membership is required: this test ref()s int_player_gameweek_spine,
-- stg_player and stg_gameweek, all access: private. See CLAUDE.md, "Served
-- contract".
--
-- fct_test_player_gameweek_spine_covers_departed_players asserts a departed
-- player is present in the spine at all. This asserts they keep their rows:
-- one per finished gameweek, so fct_player_gameweek still carries the gameweeks
-- they played and fixture_count = 0 for the gameweeks after they left.
--
-- Departure is read from stg_player directly rather than from the roster, so
-- the test does not trust the model the spine now reads. Non-vacuous on the
-- fixture tree because of player 4's synthetic departure, which
-- stg_test_player_departure_present asserts is really there. This test does
-- not repeat that precondition.

with latest_player_capture as (

    select season, run_id
    from (
        select
            season,
            run_id,
            row_number() over (
                partition by season
                order by observed_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, observed_at from {{ ref('stg_player') }})
    )
    where capture_rank = 1

),

departed as (

    select distinct player.season, player.fpl_id
    from {{ ref('stg_player') }} as player
    where not exists (
        select 1
        from {{ ref('stg_player') }} as latest_player
        inner join latest_player_capture using (season, run_id)
        where latest_player.season = player.season
          and latest_player.fpl_id = player.fpl_id
    )

),

latest_calendar_capture as (

    -- The same per-season capture int_player_gameweek_spine takes gameweeks from.
    select season, run_id
    from (
        select
            season,
            run_id,
            row_number() over (
                partition by season
                order by observed_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, observed_at from {{ ref('stg_gameweek') }})
    )
    where capture_rank = 1

),

finished_gameweeks as (

    select calendar.season, calendar.gameweek
    from {{ ref('stg_gameweek') }} as calendar
    inner join latest_calendar_capture using (season, run_id)
    where calendar.finished

)

select
    departed.season,
    departed.fpl_id,
    finished_gameweeks.gameweek,
    'departed player has no spine row for this finished gameweek' as failure
from departed
inner join finished_gameweeks using (season)
left join {{ ref('int_player_gameweek_spine') }} as spine
    on  spine.season = departed.season
    and spine.fpl_id = departed.fpl_id
    and spine.gameweek = finished_gameweeks.gameweek
where spine.fpl_id is null
