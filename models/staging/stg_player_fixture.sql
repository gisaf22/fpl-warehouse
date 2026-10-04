-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_player_fixture
-- =============================================================================
--
-- Purpose:
--   Flattens fpl-ingest's raw element-summary captures into one row per
--   player per played fixture. Typing and renaming only — no joins, no
--   aggregation, no business logic.
--
-- Grain:
--   One row per (fpl_id, fixture_id) *per captured object*. This model is 1:1
--   with the raw source, so a player captured across several runs contributes
--   one row per run. Deduplication to a single row per (fpl_id, fixture_id) is
--   the served fct_ layer's job, not staging's.
--
-- Source:
--   source('fpl_raw', 'element_summary') — the `history` array of each
--   per-player payload. `fixtures` (upcoming) and `history_past` (prior
--   seasons) are deliberately not read here.
--
-- Naming:
--   Follows the retired src/models/ convention — `fpl_id` for the player key,
--   `*_fpl_id` for FPL team identifiers, FPL's own field names preserved
--   otherwise (bps, ict_index, clearances_blocks_interceptions, ...).
--
-- Typing:
--   FPL serves influence/creativity/threat/ict_index and the expected_*
--   family as JSON strings; they are cast to DOUBLE here. kickoff_time is
--   an ISO-8601 UTC string cast to TIMESTAMP.
--
-- Note:
--   `team_fpl_id` is deliberately absent — the raw history row carries only
--   `opponent_team` and `was_home`, never the player's own team. Resolving it
--   at build time is the known as-of bug this rebuild must not reintroduce.
--
-- Capture identity:
--   Only admitted captures are staged: each payload's key, from
--   capture_key_from_filename, is inner-joined to int_admitted_capture (#104).
--   capture_key, season, extraction_date, run_id, extracted_at and
--   observed_at all come from there, never from the object's path. A payload
--   that is unadmitted or not yet indexed is not staged.
--   The served layer resolves competing captures of the same
--   (fpl_id, fixture_id) by observed_at, then run_id. extracted_at is carried
--   only because fct_player_fixture serves it (#88 E1).
--
-- Season:
--   `season` is part of capture identity. fpl_id, fixture_id and gameweek are
--   all reassigned every season, so every downstream dedup, retraction check
--   and ratification lookup partitions by season as well — it keeps that
--   within-season logic from ever reaching across a season boundary. It is
--   never used to relate one season's rows to another's. The same column
--   appears on every stg_ model.
-- =============================================================================

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(history) as h
    from {{ source('fpl_raw', 'element_summary') }}

)

select
    -- Capture identity
    admitted.capture_key,
    admitted.season,
    admitted.extraction_date,
    admitted.run_id,
    admitted.extracted_at,
    admitted.observed_at,

    -- Keys
    cast(h.element             as integer)   as fpl_id,
    cast(h.fixture             as integer)   as fixture_id,
    cast(h.round               as integer)   as gameweek,

    -- Fixture context
    cast(h.opponent_team       as integer)   as opponent_team_fpl_id,
    cast(h.was_home            as boolean)   as was_home,
    cast(h.kickoff_time        as timestamp) as kickoff_time,
    cast(h.team_h_score        as integer)   as team_h_score,
    cast(h.team_a_score        as integer)   as team_a_score,

    -- Appearance
    cast(h.minutes             as integer)   as minutes,
    cast(h.starts              as integer)   as starts,

    -- Scoring
    cast(h.total_points        as integer)   as total_points,
    cast(h.bonus               as integer)   as bonus,
    cast(h.bps                 as integer)   as bps,
    cast(h.goals_scored        as integer)   as goals_scored,
    cast(h.assists             as integer)   as assists,
    cast(h.clean_sheets        as integer)   as clean_sheets,
    cast(h.goals_conceded      as integer)   as goals_conceded,
    cast(h.own_goals           as integer)   as own_goals,
    cast(h.penalties_saved     as integer)   as penalties_saved,
    cast(h.penalties_missed    as integer)   as penalties_missed,
    cast(h.yellow_cards        as integer)   as yellow_cards,
    cast(h.red_cards           as integer)   as red_cards,
    cast(h.saves               as integer)   as saves,

    -- Defensive contribution family
    cast(h.clearances_blocks_interceptions as integer) as clearances_blocks_interceptions,
    cast(h.recoveries          as integer)   as recoveries,
    cast(h.tackles             as integer)   as tackles,
    cast(h.defensive_contribution as integer) as defensive_contribution,

    -- Expected values (served as strings)
    cast(h.expected_goals              as double) as expected_goals,
    cast(h.expected_assists            as double) as expected_assists,
    cast(h.expected_goal_involvements  as double) as expected_goal_involvements,
    cast(h.expected_goals_conceded     as double) as expected_goals_conceded,

    -- ICT family (served as strings; populated only at ratification)
    cast(h.influence           as double)    as influence,
    cast(h.creativity          as double)    as creativity,
    cast(h.threat              as double)    as threat,
    cast(h.ict_index           as double)    as ict_index,

    -- Market
    cast(h.value               as integer)   as value,
    cast(h.selected            as integer)   as selected,
    cast(h.transfers_in        as integer)   as transfers_in,
    cast(h.transfers_out       as integer)   as transfers_out,
    cast(h.transfers_balance   as integer)   as transfers_balance,

    cast(h.modified            as boolean)   as modified

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
