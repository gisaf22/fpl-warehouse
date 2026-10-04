-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_player_gameweek_spine
-- =============================================================================
--
-- Purpose:
--   Every (fpl_id, gameweek) pair that *should* exist, so fct_player_gameweek
--   can be built by LEFT JOIN and a player with no fixture in a gameweek
--   surfaces as fixture_count = 0 rather than as a missing row.
--
-- Why it is not derived from fixtures:
--   Deriving the gameweek grain from whichever fixtures happened to be
--   captured is the original bug this rebuild exists to fix: a blank gameweek
--   and a dropped row are indistinguishable, and downstream rolling windows
--   silently shift. The spine is therefore built from the current player list
--   and the gameweek calendar only — it never reads fct_player_fixture.
--
-- Grain:
--   One row per (season, fpl_id, gameweek): each season's players crossed
--   with every gameweek that season's latest bootstrap-static capture reports
--   as finished. `season` comes from staging — see CLAUDE.md, "Season is part
--   of the grain".
--
-- Season scoping:
--   Every step below — the latest capture, the player set (per season in
--   int_player_season) and the players x gameweeks cross — is computed per
--   season. fpl_id and gameweek are both reassigned each season, so an
--   unscoped version would take one season's calendar for another's players.
--   Season is only ever a partition here; no row pairs one season's data with
--   another's.
--
-- Gameweek range:
--   `finished` is the boundary. A gameweek in progress or still upcoming has no
--   settled per-fixture data, and including it would manufacture
--   fixture_count = 0 rows indistinguishable from a genuine blank gameweek —
--   the exact ambiguity this model exists to remove. `data_checked` (bonus
--   applied, scores ratified) is available in stg_gameweek as a stricter gate
--   if a consumer ever needs one.
--
-- Player list:
--   Read from int_player_season (#70): every player seen in *any*
--   bootstrap-static capture of the season, with the newest web_name. The
--   spine computes no player set of its own, so it and dim_player cannot
--   disagree about who played. Why every capture and not the latest, and the
--   coverage limit, are in int_player_season's header, "Why every capture".
--
-- Gameweek range vs player list:
--   The two axes deliberately use different capture scopes. Gameweeks come
--   from the latest capture because the calendar is a statement about now and
--   an older capture reports fewer gameweeks finished. Players come from every
--   capture because squad membership is cumulative — someone who played is
--   part of the season's history whether or not they are still registered.
-- =============================================================================

with latest_capture as (

    -- One capture per season. run_id carries a per-run hash, so it identifies
    -- one capture outright.
    select
        season,
        run_id
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

players as (

    -- The season's player set, shared with dim_player: every player from every
    -- capture of the season, one row each, with the newest web_name.
    select
        season,
        fpl_id,
        web_name
    from {{ ref('int_player_season') }}

),

gameweeks as (

    select
        calendar.season,
        calendar.gameweek,
        calendar.deadline_time
    from {{ ref('stg_gameweek') }} as calendar
    inner join latest_capture using (season, run_id)
    where calendar.finished

)

select
    players.season,
    players.fpl_id,
    gameweeks.gameweek,
    players.web_name,
    gameweeks.deadline_time
from players
-- The within-season cross join: each season's players against that same
-- season's gameweeks, and nothing else.
inner join gameweeks using (season)
