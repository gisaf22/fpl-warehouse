-- =============================================================================
-- Layer: dim_ (dimension)
-- Model: dim_player_status_history
-- =============================================================================
--
-- Purpose:
--   One row per change in a player's tracked status fields, so a consumer can
--   join the state that held at any moment by (season, fpl_id) and time
--   (#126, Feature #123).
--
-- Grain:
--   (season, fpl_id, valid_from), over the half-open interval
--   [valid_from, valid_to). valid_to is null on the open row. Natural key, no
--   surrogate (docs/adr/0002-as-of-joins-on-natural-keys.md).
--
-- How it is built:
--   SCD2 as an ordinary model from immutable captures, not a dbt snapshot
--   (docs/adr/0001-scd2-as-models-from-captures.md). Every admitted
--   bootstrap-static capture of a player is compared with the previous one;
--   a capture whose tracked fields differ opens a row, and the next opening
--   closes it. Captures are ordered by observed_at, with run_id breaking a
--   tie, as everywhere else (#104). Everything is partitioned by season:
--   fpl_id is reassigned each season.
--
-- Tracked fields (a change opens a row):
--   status, chance_of_playing_this_round, chance_of_playing_next_round, news,
--   can_select, removed, team_fpl_id, position_id. Compared with
--   IS DISTINCT FROM, so two nulls are equal.
--
-- Attributes (carried, never open a row):
--   news_added, player_code, capture_key, taken from the capture that opened
--   the row: capture_key is the evidence for valid_from, and later captures
--   cannot change a row's values on rebuild (ADR 0001).
--
-- No backdating:
--   A player's first row opens at their first capture. Before it there is no
--   row; 2025-26's only capture postdates every 2025-26 deadline.
--
-- No closing on absence:
--   A player missing from later captures keeps an open row. That rule was
--   rejected on #123; stg_test_player_set_never_shrinks_warns names them.
--
-- team_fpl_id:
--   The club listed at the capture, valid only within its interval. Never a
--   build-time "current team" (CLAUDE.md, known bug 1); the club for a
--   fixture is fct_player_fixture.team_fpl_id.
-- =============================================================================

with captures as (

    select
        season,
        fpl_id,
        observed_at,
        run_id,
        capture_key,
        status,
        chance_of_playing_this_round,
        chance_of_playing_next_round,
        news,
        can_select,
        removed,
        team_fpl_id,
        position_id,
        news_added,
        player_code
    from {{ ref('stg_player') }}

),

compared as (

    select
        *,
        row_number() over capture_order = 1 as is_first_capture,
        lag(status)                       over capture_order as prev_status,
        lag(chance_of_playing_this_round) over capture_order as prev_chance_this_round,
        lag(chance_of_playing_next_round) over capture_order as prev_chance_next_round,
        lag(news)                         over capture_order as prev_news,
        lag(can_select)                   over capture_order as prev_can_select,
        lag(removed)                      over capture_order as prev_removed,
        lag(team_fpl_id)                  over capture_order as prev_team_fpl_id,
        lag(position_id)                  over capture_order as prev_position_id
    from captures
    window capture_order as (
        partition by season, fpl_id
        order by observed_at, run_id
    )

),

openings as (

    select *
    from compared
    where is_first_capture
       or status                       is distinct from prev_status
       or chance_of_playing_this_round is distinct from prev_chance_this_round
       or chance_of_playing_next_round is distinct from prev_chance_next_round
       or news                         is distinct from prev_news
       or can_select                   is distinct from prev_can_select
       or removed                      is distinct from prev_removed
       or team_fpl_id                  is distinct from prev_team_fpl_id
       or position_id                  is distinct from prev_position_id

)

select
    season,
    fpl_id,
    observed_at as valid_from,
    lead(observed_at) over (
        partition by season, fpl_id
        order by observed_at, run_id
    )           as valid_to,

    -- Tracked fields
    status,
    chance_of_playing_this_round,
    chance_of_playing_next_round,
    news,
    can_select,
    removed,
    team_fpl_id,
    position_id,

    -- Attributes, from the opening capture
    news_added,
    player_code,
    capture_key
from openings
