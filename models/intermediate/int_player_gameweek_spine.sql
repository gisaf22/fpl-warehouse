-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_player_gameweek_spine
-- =============================================================================
--
-- Purpose:
--   Every (fpl_id, round) pair that *should* exist, so agg_player_gameweek can
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
--   One row per (fpl_id, round): players from the latest bootstrap-static
--   capture, crossed with every round that capture reports as finished.
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
--   The latest capture only, so the spine tracks the squad as it stands now.
--   A player who joined mid-season still gets spine rows for earlier rounds,
--   which correctly resolve to fixture_count = 0.
-- =============================================================================

with latest_capture as (

    -- run_id carries a per-run hash, so it identifies one capture outright.
    select run_id
    from {{ ref('stg_gameweek') }}
    order by extracted_at desc, run_id desc
    limit 1

),

players as (

    select
        fpl_id,
        web_name
    from {{ ref('stg_player') }}
    where run_id = (select run_id from latest_capture)

),

rounds as (

    select
        round,
        deadline_time
    from {{ ref('stg_gameweek') }}
    where run_id = (select run_id from latest_capture)
      and finished

)

select
    players.fpl_id,
    rounds.round,
    players.web_name,
    rounds.deadline_time
from players
cross join rounds
