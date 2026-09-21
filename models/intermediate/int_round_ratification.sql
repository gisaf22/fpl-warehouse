-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_round_ratification
-- =============================================================================
--
-- Purpose:
--   Collapses stg_event_status's (round, match_date) x capture grain down to
--   one authoritative row per round: has FPL ratified this round's points?
--
--   This is the reshape that replaces the served layer's former inference,
--   which read "FPL has published a final score for this fixture" as a proxy
--   for "this round's points are final". Those are not the same event —
--   scores appear at full time, bonus points are applied hours later — so the
--   old proxy reported ratified during the settle window, while `bonus` was
--   still 0. See CLAUDE.md, "Round ratification".
--
-- Grain:
--   One row per (season, round), for every round that appears in at least one
--   event-status capture. Rounds absent from every capture are absent here;
--   handling that gap is fct_player_fixture's job, not this model's.
--
--   Both rollup levels partition by season: round numbers repeat every season,
--   and "ever observed ratified" must never let one season's verdict answer
--   for another's round of the same number.
--
-- Why an intermediate model:
--   Per CLAUDE.md "Layering", the layer is used only when a reshape is
--   genuinely complex or reused. Both apply: the rollup is two-level (below),
--   and fct_player_fixture and fct_player_gameweek both need it.
--
-- The rollup rule — two levels, in this order:
--
--   1. Within one capture, a round is ratified only when *every* dated entry
--      for it is ratified. A round in transition mixes values across its match
--      dates within a single payload (observed: `""` and `"p"` side by side),
--      so this must be bool_and, never bool_or.
--
--   2. Across captures, a round is ratified if *any* capture ever said so.
--      event-status serves only the current round's dates — a finished round
--      rolls out of the window completely — so the newest capture reports
--      nothing at all about rounds already settled. Taking the latest capture
--      the way fct_player_fixture resolves competing element-summary captures
--      would therefore lose every past round. Ratification is monotonic (FPL
--      does not un-ratify a round), so "ever observed ratified" is sound.
--
--   A dated entry counts as ratified when points = 'r' AND bonus_added. The
--   two move together in every capture observed, so requiring both is belt and
--   braces rather than a live disagreement. `points` values 'p' and '' are both
--   treated as not-ratified — '' is an in-progress state, not a missing one.
-- =============================================================================

with per_capture as (

    select
        season,
        round,
        run_id,
        bool_and(points = 'r' and bonus_added) as is_ratified
    from {{ ref('stg_event_status') }}
    group by season, round, run_id

)

select
    season,
    round,
    coalesce(bool_or(is_ratified), false) as is_ratified
from per_capture
group by season, round
