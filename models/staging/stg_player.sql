-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_player
-- =============================================================================
--
-- Purpose:
--   Flattens the `elements` array of fpl-ingest's raw bootstrap-static
--   captures into one row per player. Typing and renaming only.
--
-- Grain:
--   One row per (fpl_id) *per captured object* — 1:1 with the raw source, so
--   a player contributes one row per bootstrap-static run. Selecting a single
--   capture is the served layer's job, not staging's.
--
-- Note:
--   `team` is deliberately not carried. Bootstrap-static states a player's
--   team as of the capture, and joining it onto historical fixtures at build
--   time is the known as-of bug this rebuild must not reintroduce.
--
-- position_id:
--   FPL's `element_type`, as of the capture. Unlike team it is treated as
--   fixed within a season (decision 2 on #32); a constant_per_key test on
--   this column asserts it (#41).
--
-- player_code:
--   FPL's `code`, the player's identifier across seasons — `fpl_id` is
--   reassigned every season (verified 2026-09-16: 471 of 476 players present
--   in both 2025-26 and 2026-27 changed id; `code` was unique within each
--   season and consistent with element-summary's `history_past.element_code`
--   for all 659 live players). It is carried as a plain column only. Nothing
--   joins, deduplicates or filters on it; `fpl_id` stays the key within a
--   season.
--
-- total_points:
--   The player's season total as of the capture. Carried so
--   stg_test_player_total_points_matches_history can reconcile it against the
--   same run's element-summary history; not a served column.
-- =============================================================================

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(elements) as e
    from {{ source('fpl_raw', 'bootstrap_static') }}

)

select
    -- Capture identity, from the capture index (see int_admitted_capture)
    admitted.capture_key,
    admitted.season,
    admitted.extraction_date,
    admitted.run_id,
    admitted.extracted_at,
    admitted.observed_at,

    -- Keys
    cast(e.id as integer)                      as fpl_id,

    -- Identity
    cast(e.web_name as varchar)                as web_name,
    cast(e.code as integer)                    as player_code,

    -- Position as of this capture; refers to stg_position.position_id
    cast(e.element_type as integer)            as position_id,

    -- Season total as of this capture
    cast(e.total_points as integer)            as total_points

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
