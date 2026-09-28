-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_season_roster
-- =============================================================================
--
-- Purpose:
--   The season's player set, once: one row per (season, fpl_id) for every
--   player seen in ANY bootstrap-static capture of that season (#69). The
--   spine (#70) and dim_player (#41) both take their players from here, so
--   they cannot disagree about who was in a season.
--
-- Why every capture and not the latest:
--   The latest capture is the squad as it stands now. A player who leaves the
--   league mid-season vanishes from it, yet their fixtures stay in
--   fct_player_fixture. Taking every capture keeps them — see
--   int_player_gameweek_spine's header, "Player list", for the full case and
--   its coverage limit (players dropped before capture began cannot be
--   recovered by any union).
--
-- Columns:
--   Identity and the newest web_name only. Everything else about a player
--   belongs in dim_player (#41).
--
--   web_name is the newest capture's spelling. Carried per capture instead, a
--   player FPL renames mid-season would contribute two rows — observed live
--   on fpl_id 551, "Angulo" and "N.Angulo".
--
--   player_code is carried, never used: nothing here joins, deduplicates or
--   filters on it. It is taken from the same newest capture; the
--   constant_per_key test on stg_player.player_code fails the build if it is
--   ever null or changes within a season, so which capture it comes from
--   cannot matter.
--
-- Season scoping:
--   Partitioned by season throughout. fpl_id is reassigned each season, so the
--   same fpl_id in two seasons is two people and two rows.

select
    season,
    fpl_id,
    player_code,
    web_name
from (
    select
        season,
        fpl_id,
        player_code,
        web_name,
        row_number() over (
            partition by season, fpl_id
            order by extracted_at desc, run_id desc
        ) as capture_rank
    from {{ ref('stg_player') }}
)
where capture_rank = 1
