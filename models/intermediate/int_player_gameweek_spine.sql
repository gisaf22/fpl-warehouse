-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_player_gameweek_spine
-- =============================================================================
--
-- Purpose:
--   Every (fpl_id, round) pair that *should* exist, so fct_player_gameweek can
--   be built by LEFT JOIN and a player with no fixture in a round surfaces as
--   fixture_count = 0 rather than as a missing row.
--
-- Why it is not derived from fixtures:
--   Deriving the gameweek grain from whichever fixtures happened to be
--   captured is the original bug this rebuild exists to fix: a blank gameweek
--   and a dropped row are indistinguishable, and downstream rolling windows
--   silently shift. The spine is therefore built from the current player list
--   and the gameweek calendar only — it never reads fct_player_fixture.
--
-- Grain:
--   One row per (season, fpl_id, round): each season's players crossed with
--   every round that season's latest bootstrap-static capture reports as
--   finished. `season` comes from staging — see CLAUDE.md, "Season is part of
--   the grain".
--
-- Season scoping:
--   Every step below — the latest capture, the player union, the web_name
--   dedup and the players x rounds cross — is computed per season. fpl_id and
--   round are both reassigned each season, so an unscoped version would take
--   one season's calendar for another's players. Season is only ever a
--   partition here; no row pairs one season's data with another's.
--
-- Round range:
--   `finished` is the boundary. A round in progress or still upcoming has no
--   settled per-fixture data, and including it would manufacture
--   fixture_count = 0 rows indistinguishable from a genuine blank gameweek —
--   the exact ambiguity this model exists to remove. `data_checked` (bonus
--   applied, scores ratified) is available in stg_gameweek as a stricter gate
--   if a consumer ever needs one.
--
-- Player list:
--   Every player seen in *any* bootstrap-static capture, not just the latest.
--
--   The latest capture alone tracks the squad as it stands now, which handles
--   a mid-season arrival correctly — they get spine rows for earlier rounds
--   that resolve to fixture_count = 0 — but silently loses a mid-season
--   *departure*. A player who leaves the league (transfer abroad, retirement,
--   or simply dropped from FPL's `elements`) vanishes from the spine, and with
--   it every fixture they actually played this season disappears from
--   fct_player_gameweek while remaining in fct_player_fixture. That is the
--   same silent row-loss class this model exists to prevent, arriving from the
--   player axis instead of the round axis.
--
--   Taking the union across all captures makes the treatment symmetric: a
--   departure keeps real rows for the weeks they played and fixture_count = 0
--   for the weeks after they left, exactly as an arrival gets fixture_count = 0
--   for the weeks before they joined. The two served tables then hold the same
--   player set by construction, asserted by
--   tests/fct_test_player_gameweek_covers_every_fixture.sql.
--
--   Verified 2026-09-14 against all 128 live bootstrap-static captures: the
--   union is 658 players and the latest capture is also 658, so this change is
--   currently a no-op on live data — FPL's `elements` list has only grown this
--   season (622 -> 658). It is a forward guard, not a repair.
--
--   Coverage limit: captures begin 2026-08-29, after GW1 (deadline
--   2026-08-21) had already been played. A player dropped from `elements`
--   inside that window appears in no capture at all and so cannot be
--   recovered by any union. Nothing in the warehouse can fix that; it is a
--   gap in what was captured.
--
--   web_name is deduplicated to the newest capture's spelling rather than
--   carried per capture. Without that, a player FPL renames mid-season
--   contributes two spine rows and doubles their gameweek grain — observed
--   live on fpl_id 551, captured as both "Angulo" and "N.Angulo".
--
-- Round range vs player list:
--   The two axes deliberately use different capture scopes. Rounds come from
--   the latest capture because the calendar is a statement about now and an
--   older capture reports fewer rounds finished. Players come from every
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
                order by extracted_at desc, run_id desc
            ) as capture_rank
        from (select distinct season, run_id, extracted_at from {{ ref('stg_gameweek') }})
    )
    where capture_rank = 1

),

players as (

    -- Every player from every capture of the season, one row each, carrying
    -- the most recently captured spelling of web_name.
    select
        season,
        fpl_id,
        web_name
    from (
        select
            season,
            fpl_id,
            web_name,
            row_number() over (
                partition by season, fpl_id
                order by extracted_at desc, run_id desc
            ) as name_rank
        from {{ ref('stg_player') }}
    )
    where name_rank = 1

),

rounds as (

    select
        gameweek.season,
        gameweek.round,
        gameweek.deadline_time
    from {{ ref('stg_gameweek') }} as gameweek
    inner join latest_capture using (season, run_id)
    where gameweek.finished

)

select
    players.season,
    players.fpl_id,
    rounds.round,
    players.web_name,
    rounds.deadline_time
from players
-- The within-season cross join: each season's players against that same
-- season's rounds, and nothing else.
inner join rounds using (season)
