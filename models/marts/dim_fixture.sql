-- =============================================================================
-- Layer: dim_ (dimension)
-- Model: dim_fixture
-- =============================================================================
--
-- Purpose:
--   One row per fixture per season: teams, round, kickoff, result and
--   difficulty, so a fixture id on a fact resolves to its context within its
--   own season.
--
-- Grain:
--   (season, fixture_id). fixture_id is reassigned every season, so season is
--   part of the key. A round may hold more or fewer than 10 fixtures (doubles
--   and blanks) and a team may play twice in one round; nothing here is keyed
--   on round or team.
--
-- Latest capture:
--   Teams, round, kickoff, score and finished come from each fixture's latest
--   capture, ordered by extracted_at with run_id breaking a same-second tie,
--   as in dim_team. So the score is the final one once there is one, and a
--   postponed fixture reads null round and kickoff — kept, not dropped and
--   not given an earlier capture's schedule.
--
-- Difficulty (decision 3 on #32):
--   Served from the last capture before kickoff, the value a manager saw
--   before the match, with difficulty_is_pre_kickoff = true. Kickoff is the
--   latest capture's: a rescheduled fixture's earlier kickoff is not when it
--   was played. A fixture with no kickoff (postponed) has not been played, so
--   every capture counts as before kickoff.
--
--   Where no capture precedes kickoff — all of 2025-26, whose one capture is
--   an end-of-season snapshot, and live fixtures played before capture
--   history began on 2026-08-29 — the earliest capture's value is carried,
--   the one closest to kickoff, with the flag false. Never null, so a
--   consumer can filter out values that may leak the result without losing
--   the column.
-- =============================================================================

with ranked as (

    select
        *,
        row_number() over (
            partition by season, fixture_id
            order by extracted_at desc, run_id desc
        ) as capture_rank_desc
    from {{ ref('stg_fixture') }}

),

latest as (

    select *
    from ranked
    where capture_rank_desc = 1

),

captures as (

    select
        ranked.season,
        ranked.fixture_id,
        ranked.extracted_at,
        ranked.run_id,
        ranked.team_h_difficulty,
        ranked.team_a_difficulty,
        latest.kickoff_time is null
            or ranked.extracted_at < latest.kickoff_time as is_pre_kickoff
    from ranked
    inner join latest
        on  latest.season = ranked.season
        and latest.fixture_id = ranked.fixture_id

),

difficulty as (

    select
        season,
        fixture_id,
        team_h_difficulty,
        team_a_difficulty,
        is_pre_kickoff
    from captures
    -- The last pre-kickoff capture if there is one, else the earliest.
    qualify row_number() over (
        partition by season, fixture_id
        order by
            is_pre_kickoff desc,
            case when is_pre_kickoff then extracted_at end desc,
            case when is_pre_kickoff then run_id end desc,
            extracted_at,
            run_id
    ) = 1

)

select
    latest.season,
    latest.fixture_id,
    latest.round,
    latest.kickoff_time,
    latest.team_h_fpl_id,
    latest.team_a_fpl_id,
    latest.team_h_score,
    latest.team_a_score,
    latest.finished,
    difficulty.team_h_difficulty,
    difficulty.team_a_difficulty,
    difficulty.is_pre_kickoff as difficulty_is_pre_kickoff
from latest
inner join difficulty
    on  difficulty.season = latest.season
    and difficulty.fixture_id = latest.fixture_id
