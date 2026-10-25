-- =============================================================================
-- Layer: fct_ (served)
-- Model: fct_player_gameweek
-- =============================================================================
--
-- Purpose:
--   Player-gameweek aggregate, built by LEFT JOIN of fct_player_fixture onto
--   int_player_gameweek_spine so that every (fpl_id, gameweek) that should
--   exist does exist. Never model this grain directly from raw data.
--
-- Grain:
--   One row per (season, fpl_id, gameweek), one-for-one with the spine.
--   `season` is carried from the spine, which reads it from staging — see
--   CLAUDE.md, "Season is part of the grain". The join below carries season, so
--   a gameweek number is only ever matched within the season it belongs to.
--
-- fixture_count:
--   0 = nothing observed (spine row with no fixture: the team had no fixture,
--   the player was not yet registered, or had departed), 1 = normal,
--   2+ = double. It is COUNT(fixture_id) over the joined fact, so it is the
--   real number of fixtures, not an assumption. 2025-26 holds 409 double
--   gameweek keys (#133 S18).
--   CAST to INTEGER for the same reason as the additive columns: COUNT()
--   returns BIGINT, and the real range of this column is 0-3.
--
-- Aggregation classes:
--
--   Additive — summed across the gameweek's fixtures, NULL when fixture_count
--   is 0 (#133 S17). Nothing was observed for that row, so it states no
--   measure; a zero is only ever a real observed zero, from a fixture the
--   player had. There is deliberately no COALESCE: the null_exactly_when test
--   in schema.yml fails the build if a measure is NULL with a fixture or
--   non-NULL without one. Any consumer computing a per-appearance rate must
--   divide by fixture_count rather than assuming one fixture per gameweek.
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
--   Every additive integer column is CAST back to INTEGER. DuckDB's SUM()
--   widens INTEGER to HUGEINT by default, which would otherwise put a 128-bit
--   type in the served contract for quantities whose real ceiling is two
--   digits (observed maxima 2026-09-03: minutes 90, bps 87, recoveries 22,
--   everything else under 25; a full prior season totals 3,420 minutes and
--   822 bps). INTEGER also keeps these columns the same type they have at
--   fixture grain in fct_player_fixture.
--
--   Point-in-time — value, selected and the transfers family are stated by FPL
--   per event, not per fixture: both rows of a double gameweek repeat the same
--   event-level number, so summing would double-count. The value from the
--   gameweek's last fixture is taken instead, and is NULL where fixture_count is 0
--   because no fixture row states it. Observed, not just documented: both
--   fixture rows carry the same values in all 409 double gameweek keys of
--   2025-26 (#133 S18).
--
--   No defined gameweek aggregation — fixture_id, opponent_team_fpl_id,
--   was_home, team_h_score and team_a_score describe a single fixture and have
--   no meaning once two are combined. They are deliberately absent here;
--   consumers needing them must read fct_player_fixture at fixture grain.
--   first_kickoff_time / last_kickoff_time are carried instead, as those stay
--   well defined across any fixture_count and support as-of filtering.
--
-- fixture_count_at_deadline (#221):
--   The number of fixtures the player's club had scheduled in the gameweek as
--   the schedule stood at the gameweek's deadline (dim_gameweek). Both the
--   club (dim_player_status_history.team_fpl_id) and the schedule
--   (dim_fixture_schedule_history) are looked up strictly before the deadline
--   through as_of (ADR 0002), and a fixture counts for its club on either
--   side. fixture_count is realised, from element-summary history; this is
--   what a manager could know at the deadline, so a fixture postponed after
--   it still counts here while fixture_count reads 0 (D2).
--   NULL when it is unknowable (D4): the gameweek has no staged capture
--   before its deadline (dim_gameweek.last_capture_before_deadline_at is
--   null: all of 2025-26 and 2026-27 GW1-2), the season has no schedule row
--   opened before the deadline (the first rule reads bootstrap-static, the
--   schedule the fixtures endpoint), or the player has no status row before
--   it. 0 is an observed blank: the club had no fixture in the gameweek.
--   Not part of null_exactly_when(fixture_count = 0): a 1 here beside a 0
--   there is the postponement this column exists to show.
--   A departed player keeps their last club's count, because status rows
--   never close on absence (#123); such a player cannot be picked.
--   The club is used here only and is not served: a player transferred
--   between the two fixtures of a double has no single club (#43).
--   Both lookups join after the fixture aggregation, one row per
--   (season, fpl_id, gameweek) and per (season, gameweek, team), so they
--   cannot fan out the sums above (D3).
-- =============================================================================

with spine as (

    select * from {{ ref('int_player_gameweek_spine') }}

),

fixtures as (

    select * from {{ ref('fct_player_fixture') }}

),

player_gameweek as (

select
    -- Keys
    spine.season,
    spine.fpl_id,
    spine.gameweek,

    -- Gameweek context
    spine.web_name,
    cast(count(fixtures.fixture_id) as integer)         as fixture_count,
    min(fixtures.kickoff_time)                          as first_kickoff_time,
    max(fixtures.kickoff_time)                          as last_kickoff_time,

    -- The gameweek's finality, per FPL's event-status (see fct_player_fixture);
    -- every contributing fixture carries the same value, so this aggregate is
    -- a pass-through that stays NULL for a blank gameweek — which
    -- fct_test_player_gameweek_counted_gameweek_has_kickoff asserts. Joining
    -- int_gameweek_status here instead would give a blank gameweek the
    -- gameweek's real flag and break that contract.
    bool_and(fixtures.is_ratified)                      as is_ratified,

    -- Appearance (additive)
    cast(sum(fixtures.minutes) as integer)              as minutes,
    cast(sum(fixtures.starts) as integer)               as starts,

    -- Scoring (additive)
    cast(sum(fixtures.total_points) as integer)         as total_points,
    cast(sum(fixtures.bonus) as integer)                as bonus,
    cast(sum(fixtures.bps) as integer)                  as bps,
    cast(sum(fixtures.goals_scored) as integer)         as goals_scored,
    cast(sum(fixtures.assists) as integer)              as assists,
    cast(sum(fixtures.clean_sheets) as integer)         as clean_sheets,
    cast(sum(fixtures.goals_conceded) as integer)       as goals_conceded,
    cast(sum(fixtures.own_goals) as integer)            as own_goals,
    cast(sum(fixtures.penalties_saved) as integer)      as penalties_saved,
    cast(sum(fixtures.penalties_missed) as integer)     as penalties_missed,
    cast(sum(fixtures.yellow_cards) as integer)         as yellow_cards,
    cast(sum(fixtures.red_cards) as integer)            as red_cards,
    cast(sum(fixtures.saves) as integer)                as saves,

    -- Defensive contribution family (additive)
    cast(sum(fixtures.clearances_blocks_interceptions) as integer)
                                                        as clearances_blocks_interceptions,
    cast(sum(fixtures.recoveries) as integer)           as recoveries,
    cast(sum(fixtures.tackles) as integer)              as tackles,
    cast(sum(fixtures.defensive_contribution) as integer)
                                                        as defensive_contribution,

    -- Expected values (additive)
    sum(fixtures.expected_goals)                        as expected_goals,
    sum(fixtures.expected_assists)                      as expected_assists,
    sum(fixtures.expected_goal_involvements)            as expected_goal_involvements,
    sum(fixtures.expected_goals_conceded)               as expected_goals_conceded,

    -- ICT: components and index are all additive (round() clears float noise)
    round(sum(fixtures.influence), 1)                   as influence,
    round(sum(fixtures.creativity), 1)                  as creativity,
    round(sum(fixtures.threat), 1)                      as threat,
    round(sum(fixtures.ict_index), 1)                   as ict_index,

    -- Market: event-level, taken from the gameweek's last fixture
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
    on fixtures.season = spine.season
   and fixtures.fpl_id = spine.fpl_id
   and fixtures.gameweek = spine.gameweek
group by
    spine.season,
    spine.fpl_id,
    spine.gameweek,
    spine.web_name

),

-- Gameweeks whose deadline count is knowable (D4): a staged capture and a
-- schedule row both precede the deadline.
computable_gameweeks as (

    select gameweek.season, gameweek.gameweek, gameweek.deadline_time
    from {{ ref('dim_gameweek') }} as gameweek
    where gameweek.last_capture_before_deadline_at is not null
      and exists (
          select 1
          from {{ ref('dim_fixture_schedule_history') }} as schedule
          where schedule.season = gameweek.season
            and schedule.valid_from < gameweek.deadline_time
      )

),

club_requests as (

    select
        player_gameweek.season,
        player_gameweek.fpl_id,
        player_gameweek.gameweek,
        computable_gameweeks.deadline_time as as_of_time
    from player_gameweek
    inner join computable_gameweeks
        on computable_gameweeks.season = player_gameweek.season
       and computable_gameweeks.gameweek = player_gameweek.gameweek

),

club_at_deadline as (

    {{ player_status_as_of('club_requests') }}

),

-- Every fixture of the season, at each computable deadline. The request's
-- gameweek is deadline_gameweek, so it cannot clash with the schedule's own.
schedule_requests as (

    select
        computable_gameweeks.season,
        computable_gameweeks.gameweek as deadline_gameweek,
        computable_gameweeks.deadline_time as as_of_time,
        season_fixtures.fixture_id
    from computable_gameweeks
    inner join (
        select distinct season, fixture_id
        from {{ ref('dim_fixture_schedule_history') }}
    ) as season_fixtures
        on season_fixtures.season = computable_gameweeks.season

),

schedule_at_deadline as (

    {{ as_of('schedule_requests', ref('dim_fixture_schedule_history'), 'valid_from',
             ['gameweek', 'team_h_fpl_id', 'team_a_fpl_id'],
             keys=['season', 'fixture_id']) }}

),

team_fixtures_at_deadline as (

    select
        season,
        deadline_gameweek as gameweek,
        sides.team_fpl_id,
        count(*) as fixture_count
    from schedule_at_deadline,
        unnest([team_h_fpl_id, team_a_fpl_id]) as sides (team_fpl_id)
    where schedule_at_deadline.gameweek = schedule_at_deadline.deadline_gameweek
    group by season, deadline_gameweek, sides.team_fpl_id

)

select
    player_gameweek.*,
    case
        when club_at_deadline.valid_from is not null
        then cast(coalesce(team_fixtures_at_deadline.fixture_count, 0) as integer)
    end as fixture_count_at_deadline
from player_gameweek
left join club_at_deadline
    on club_at_deadline.season = player_gameweek.season
   and club_at_deadline.fpl_id = player_gameweek.fpl_id
   and club_at_deadline.gameweek = player_gameweek.gameweek
left join team_fixtures_at_deadline
    on team_fixtures_at_deadline.season = player_gameweek.season
   and team_fixtures_at_deadline.gameweek = player_gameweek.gameweek
   and team_fixtures_at_deadline.team_fpl_id = club_at_deadline.team_fpl_id
