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
--   The latest capture alone tracks the squad as it stands now, which handles
--   a mid-season arrival correctly — they get spine rows for earlier rounds
--   that resolve to fixture_count = 0 — but silently loses a mid-season
--   *departure*. A player who leaves the league (transfer abroad, retirement,
--   or simply dropped from FPL's `elements`) vanishes from it, and with them
--   every fixture they actually played this season would disappear from
--   fct_player_gameweek while remaining in fct_player_fixture. That is the
--   silent row-loss class the spine exists to prevent, arriving from the
--   player axis instead of the round axis.
--
--   Taking the union across all captures makes the treatment symmetric: a
--   departure keeps real rows for the weeks they played and fixture_count = 0
--   for the weeks after they left, exactly as an arrival gets fixture_count = 0
--   for the weeks before they joined. The two served facts then hold the same
--   player set by construction, asserted by
--   tests/fct_test_player_gameweek_covers_every_fixture.sql.
--
--   Verified 2026-09-14 against all 128 live bootstrap-static captures: the
--   union was 658 players and the latest capture was also 658 — FPL's
--   `elements` list had only grown that season (622 -> 658). It is a forward
--   guard, not a repair.
--
--   Coverage limit: captures begin 2026-08-29, after GW1 (deadline
--   2026-08-21) had already been played. A player dropped from `elements`
--   inside that window appears in no capture at all and so cannot be
--   recovered by any union. Nothing in the warehouse can fix that; it is a
--   gap in what was captured.
--
--   This rationale moved here from int_player_gameweek_spine's header in #70,
--   when the spine stopped computing its own player set.
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
