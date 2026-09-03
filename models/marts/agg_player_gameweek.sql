-- =============================================================================
-- Layer: agg_ (served)
-- Model: agg_player_gameweek
-- =============================================================================
--
-- Purpose:
--   Player-gameweek aggregate, built by LEFT JOIN of fct_player_fixture onto
--   int_player_gameweek_spine so that every (fpl_id, round) that should exist
--   does exist. Never model this grain directly from raw data.
--
-- Grain:
--   One row per (fpl_id, round), one-for-one with the spine.
--
-- fixture_count:
--   0 = blank gameweek (spine row with no fixture), 1 = normal, 2+ = double.
--   It is COUNT(fixture_id) over the joined fact, so it is the real number of
--   fixtures, not an assumption. Live data holds no double gameweek yet; the
--   aggregation below is written so one aggregates correctly when it lands.
--
-- Aggregation classes:
--
--   Additive — summed across the round's fixtures, 0 when the gameweek is
--   blank. A blank gameweek genuinely scores zero, and fixture_count is what
--   distinguishes "played and scored nothing" from "had no fixture"; any
--   consumer computing a per-appearance rate must divide by fixture_count
--   rather than assuming one fixture per round.
--
--   influence / creativity / threat are additive per-match component scores,
--   and so is ict_index itself. Verified on 2026-09-03 against FPL's own
--   season totals in bootstrap-static: summing the per-match ict_index
--   reproduces the published season figure for 626 of 626 players.
--
--   ict_index is therefore summed, NOT recomputed as
--   (influence + creativity + threat) / 10. That formula holds for most rows
--   but not all — 31 of 1,236 fixture rows publish an index that does not
--   reconcile with their own components (fpl_id 415 round 1 states
--   influence 0.0, creativity 1.2, threat 16.0 and an index of 0.7, where the
--   formula gives 1.7). Recomputing reproduces FPL's season total for only
--   538 of 626 players, so the published index is the authority and the
--   inconsistency is carried rather than silently corrected.
--
--   Point-in-time — value, selected and the transfers family are stated by FPL
--   per event, not per fixture: both rows of a double gameweek repeat the same
--   event-level number, so summing would double-count. The value from the
--   round's last fixture is taken instead, and is NULL for a blank gameweek
--   because no fixture row states it. NOTE: this is FPL's documented field
--   semantics, not something the current data can prove — no double gameweek
--   has occurred yet to observe the repetition. Revisit at the first double.
--
--   No defined gameweek aggregation — fixture_id, opponent_team_fpl_id,
--   was_home, team_h_score and team_a_score describe a single fixture and have
--   no meaning once two are combined. They are deliberately absent here;
--   consumers needing them must read fct_player_fixture at fixture grain.
--   first_kickoff_time / last_kickoff_time are carried instead, as those stay
--   well defined across any fixture_count and support as-of filtering.
-- =============================================================================

with spine as (

    select * from {{ ref('int_player_gameweek_spine') }}

),

fixtures as (

    select * from {{ ref('fct_player_fixture') }}

)

select
    -- Keys
    spine.fpl_id,
    spine.round,

    -- Gameweek context
    spine.web_name,
    spine.deadline_time,
    count(fixtures.fixture_id)                          as fixture_count,
    min(fixtures.kickoff_time)                          as first_kickoff_time,
    max(fixtures.kickoff_time)                          as last_kickoff_time,

    -- Every contributing fixture came from a ratified capture; NULL when blank
    bool_and(fixtures.is_ratified)                      as is_ratified,

    -- Appearance (additive)
    coalesce(sum(fixtures.minutes), 0)                  as minutes,
    coalesce(sum(fixtures.starts), 0)                   as starts,

    -- Scoring (additive)
    coalesce(sum(fixtures.total_points), 0)             as total_points,
    coalesce(sum(fixtures.bonus), 0)                    as bonus,
    coalesce(sum(fixtures.bps), 0)                      as bps,
    coalesce(sum(fixtures.goals_scored), 0)             as goals_scored,
    coalesce(sum(fixtures.assists), 0)                  as assists,
    coalesce(sum(fixtures.clean_sheets), 0)             as clean_sheets,
    coalesce(sum(fixtures.goals_conceded), 0)           as goals_conceded,
    coalesce(sum(fixtures.own_goals), 0)                as own_goals,
    coalesce(sum(fixtures.penalties_saved), 0)          as penalties_saved,
    coalesce(sum(fixtures.penalties_missed), 0)         as penalties_missed,
    coalesce(sum(fixtures.yellow_cards), 0)             as yellow_cards,
    coalesce(sum(fixtures.red_cards), 0)                as red_cards,
    coalesce(sum(fixtures.saves), 0)                    as saves,

    -- Defensive contribution family (additive)
    coalesce(sum(fixtures.clearances_blocks_interceptions), 0)
                                                        as clearances_blocks_interceptions,
    coalesce(sum(fixtures.recoveries), 0)               as recoveries,
    coalesce(sum(fixtures.tackles), 0)                  as tackles,
    coalesce(sum(fixtures.defensive_contribution), 0)   as defensive_contribution,

    -- Expected values (additive)
    coalesce(sum(fixtures.expected_goals), 0)           as expected_goals,
    coalesce(sum(fixtures.expected_assists), 0)         as expected_assists,
    coalesce(sum(fixtures.expected_goal_involvements), 0)
                                                        as expected_goal_involvements,
    coalesce(sum(fixtures.expected_goals_conceded), 0)  as expected_goals_conceded,

    -- ICT: components and index are all additive (round() clears float noise)
    round(coalesce(sum(fixtures.influence), 0), 1)      as influence,
    round(coalesce(sum(fixtures.creativity), 0), 1)     as creativity,
    round(coalesce(sum(fixtures.threat), 0), 1)         as threat,
    round(coalesce(sum(fixtures.ict_index), 0), 1)      as ict_index,

    -- Market: event-level, taken from the round's last fixture
    max_by(fixtures.value, fixtures.kickoff_time)       as value,
    max_by(fixtures.selected, fixtures.kickoff_time)    as selected,
    max_by(fixtures.transfers_in, fixtures.kickoff_time)
                                                        as transfers_in,
    max_by(fixtures.transfers_out, fixtures.kickoff_time)
                                                        as transfers_out,
    max_by(fixtures.transfers_balance, fixtures.kickoff_time)
                                                        as transfers_balance

from spine
left join fixtures
    on fixtures.fpl_id = spine.fpl_id
   and fixtures.round  = spine.round
group by
    spine.fpl_id,
    spine.round,
    spine.web_name,
    spine.deadline_time
