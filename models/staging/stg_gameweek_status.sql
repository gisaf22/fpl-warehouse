-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_gameweek_status
-- =============================================================================
--
-- Purpose:
--   Flattens the `status` array of fpl-ingest's raw event-status captures.
--   Typing and renaming only — the gameweek-level rollup is int_gameweek_status's
--   job, not staging's.
--
-- Grain:
--   One row per (gameweek, match_date) *per captured object*. This is NOT one
--   row per gameweek: FPL's event-status serves one entry per match-date within
--   the gameweek, so a gameweek spanning three match days contributes three rows
--   to every capture that covers it.
--
-- Source:
--   fpl_raw.event_status, read through declared_records (#115). The top-level
--   `leagues` string is deliberately not declared, so it cannot be read — it
--   carries no per-gameweek meaning.
--
-- Naming:
--   FPL calls the gameweek `event`; this warehouse calls it `gameweek` from
--   staging onward (#89, #101). The model was stg_event_status until #101; the
--   source keeps the endpoint's name.
--
-- Typing:
--   `points` is left as VARCHAR rather than cast to a boolean here. It has three
--   observed values — "r", "p" and "" — and collapsing them is an
--   interpretation, which belongs downstream. See int_gameweek_status.
-- =============================================================================

-- Fields come through declared_records, which selects only the columns
-- declared at `$.status[*]` in sources.yml (#115): an undeclared field fails
-- the build rather than escaping the presence test.
with raw as (

    {{ declared_records('event_status', '$.status[*]') }}

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
    cast(raw."event" as integer)               as gameweek,
    cast(raw."date" as date)                   as match_date,

    -- Finality signal
    cast(raw.points as varchar)                as points,
    cast(raw.bonus_added as boolean)           as bonus_added

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
