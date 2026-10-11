-- =============================================================================
-- Layer: dim_ (dimension)
-- Model: dim_fixture_schedule_history
-- =============================================================================
--
-- Purpose:
--   One row per change in a fixture's schedule, so a consumer can join the
--   schedule that held at any moment by (season, fixture_id) and time
--   (#152, Feature #151).
--
-- Grain:
--   (season, fixture_id, valid_from), over the half-open interval
--   [valid_from, valid_to). valid_to is null on the open row. Natural key, no
--   surrogate (docs/adr/0002-as-of-joins-on-natural-keys.md).
--
-- How it is built:
--   SCD2 as an ordinary model from immutable captures, as
--   dim_player_status_history is (docs/adr/0001-scd2-as-models-from-captures.md).
--   Every admitted fixtures capture of a fixture is compared with the
--   previous one; a capture whose tracked fields differ opens a row, and the
--   next opening closes it. Captures are ordered by observed_at, with run_id
--   breaking a repeat, as everywhere else (#104); a tie on observed_at fails
--   stg_fixture's own test. Everything is partitioned by season: fixture_id
--   is reassigned each season.
--
-- Tracked fields (a change opens a row):
--   gameweek, kickoff_time, team_h_fpl_id, team_a_fpl_id, team_h_difficulty,
--   team_a_difficulty. Compared with IS DISTINCT FROM, so two nulls are
--   equal. A postponed fixture's null gameweek and kickoff are a change, and
--   its unscheduled spell is kept as a row.
--
-- Not tracked (#151 C5):
--   The result (scores, finished) is a ratified outcome, not schedule.
--   provisional_start_time is not read: false in every capture measured.
--
-- Attribute (carried, never opens a row):
--   capture_key, from the capture that opened the row: the evidence for
--   valid_from, and later captures cannot change a row's values on rebuild
--   (ADR 0001).
--
-- No backdating:
--   A fixture's first row opens at its first capture. Before it there is no
--   row; 2025-26's only capture postdates every 2025-26 kickoff.
-- =============================================================================

with captures as (

    select
        season,
        fixture_id,
        observed_at,
        run_id,
        capture_key,
        gameweek,
        kickoff_time,
        team_h_fpl_id,
        team_a_fpl_id,
        team_h_difficulty,
        team_a_difficulty
    from {{ ref('stg_fixture') }}

),

compared as (

    select
        *,
        row_number() over capture_order = 1 as is_first_capture,
        lag(gameweek)          over capture_order as prev_gameweek,
        lag(kickoff_time)      over capture_order as prev_kickoff_time,
        lag(team_h_fpl_id)     over capture_order as prev_team_h_fpl_id,
        lag(team_a_fpl_id)     over capture_order as prev_team_a_fpl_id,
        lag(team_h_difficulty) over capture_order as prev_team_h_difficulty,
        lag(team_a_difficulty) over capture_order as prev_team_a_difficulty
    from captures
    window capture_order as (
        partition by season, fixture_id
        order by observed_at, run_id
    )

),

openings as (

    select *
    from compared
    where is_first_capture
       or gameweek          is distinct from prev_gameweek
       or kickoff_time      is distinct from prev_kickoff_time
       or team_h_fpl_id     is distinct from prev_team_h_fpl_id
       or team_a_fpl_id     is distinct from prev_team_a_fpl_id
       or team_h_difficulty is distinct from prev_team_h_difficulty
       or team_a_difficulty is distinct from prev_team_a_difficulty

)

select
    season,
    fixture_id,
    observed_at as valid_from,
    lead(observed_at) over (
        partition by season, fixture_id
        order by observed_at, run_id
    )           as valid_to,

    -- Tracked fields
    gameweek,
    kickoff_time,
    team_h_fpl_id,
    team_a_fpl_id,
    team_h_difficulty,
    team_a_difficulty,

    -- Attribute, from the opening capture
    capture_key
from openings
