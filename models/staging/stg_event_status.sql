-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_event_status
-- =============================================================================
--
-- Purpose:
--   Flattens the `status` array of fpl-ingest's raw event-status captures.
--   Typing and renaming only — the round-level rollup is int_round_ratification's
--   job, not staging's.
--
-- Grain:
--   One row per (round, match_date) *per captured object*. This is NOT one row
--   per round: FPL's event-status serves one entry per match-date within the
--   round, so a round spanning three match days contributes three rows to every
--   capture that covers it.
--
-- Source:
--   source('fpl_raw', 'event_status'). The top-level `leagues` string is
--   deliberately not read — it carries no per-round meaning.
--
-- Naming:
--   FPL calls the round `event`; `round` is used throughout this warehouse, as
--   in stg_gameweek.
--
-- Typing:
--   `points` is left as VARCHAR rather than cast to a boolean here. It has three
--   observed values — "r", "p" and "" — and collapsing them is an
--   interpretation, which belongs downstream. See int_round_ratification.
-- =============================================================================

with raw as (

    select
        filename,
        unnest(status) as st
    from {{ source('fpl_raw', 'event_status') }}

)

select
    -- Capture identity (see stg_player_fixture for the key layout)
    {{ season_from_filename() }} as season,
    cast(str_split(filename, '/')[-3] as date) as extraction_date,
    str_split(filename, '/')[-2]               as run_id,
    strptime(
        split_part(str_split(filename, '/')[-2], '-', 1),
        '%Y%m%dT%H%M%SZ'
    )                                          as extracted_at,

    -- Keys
    cast(st.event as integer)                  as round,
    cast(st.date as date)                      as match_date,

    -- Finality signal
    cast(st.points as varchar)                 as points,
    cast(st.bonus_added as boolean)            as bonus_added

from raw
