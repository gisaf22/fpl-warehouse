-- =============================================================================
-- Layer: dim_ (dimension)
-- Model: dim_player
-- =============================================================================
--
-- Purpose:
--   One row per player per season, so a player id on a fact resolves to the
--   position FPL assigned them within its own season.
--
-- Grain:
--   (season, fpl_id). fpl_id is reassigned every season, so season is part of
--   the key (decision 1 on #32).
--
-- Player set:
--   int_player_season — every player seen in any capture of the season,
--   departed players included — so dim_player and the spine cannot disagree
--   about who was in a season (#69).
--
-- Position:
--   Taken from the player's latest appearance: their newest capture within
--   the season, which for a departed player predates the season's latest
--   capture. Ordered by extracted_at, with run_id breaking a same-second tie,
--   as elsewhere. Position is fixed within a season (decision 2 on #32), so
--   which capture it comes from cannot matter; the constant_per_key test on
--   stg_player.position_id fails the build if that ever stops holding.
--
--   The label (position_short_name) is read from the same capture's position
--   list. Left joins, so a position that capture does not define surfaces as
--   a null the not_null test reports, rather than as a player silently
--   dropped.
--
-- Team:
--   Not carried. Team is per fixture (fct_player_fixture.team_fpl_id).
-- =============================================================================

with latest_appearance as (

    select
        season,
        fpl_id,
        run_id,
        position_id
    from {{ ref('stg_player') }}
    qualify row_number() over (
        partition by season, fpl_id
        order by extracted_at desc, run_id desc
    ) = 1

)

select
    roster.season,
    roster.fpl_id,
    roster.player_code,
    roster.web_name,
    latest_appearance.position_id,
    stg_position.position_short_name
from {{ ref('int_player_season') }} as roster
left join latest_appearance
    on  latest_appearance.season = roster.season
    and latest_appearance.fpl_id = roster.fpl_id
left join {{ ref('stg_position') }} as stg_position
    on  stg_position.season = latest_appearance.season
    and stg_position.run_id = latest_appearance.run_id
    and stg_position.position_id = latest_appearance.position_id
