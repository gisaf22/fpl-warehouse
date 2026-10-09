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
-- team_fpl_id:
--   FPL's `team`: the club the player is listed at as of this capture (#123).
--   Valid only as of the capture, for player status history's time ranges.
--   Never a build-time "current team" joined onto past fixtures (CLAUDE.md,
--   known bug 1); the club for a fixture is fct_player_fixture.team_fpl_id.
--
-- Status and availability:
--   As of the capture, typed only. An empty `news` is NULL, so an empty string
--   and a null never differ (#125 AC3). `news_added` is kept as published:
--   FPL can clear `news` and keep its timestamp.
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
--
-- Market (#140):
--   Price, ownership and the gameweek's transfer flow as of the capture, as
--   the source gives them: typed only, no derived values (#138 M2).
--   `now_cost` is in tenths, as published. `selected_by_percent` is published
--   as a string with one decimal place, so DECIMAL(4,1) holds it exactly; an
--   empty string is NULL. stg_test_player_selected_by_percent_has_one_decimal_place
--   fails the build if FPL ever publishes more places, which the cast would
--   otherwise round silently.
--
-- total_players:
--   The game's player count at the capture's root, the ownership denominator
--   (#138 M3), copied onto every player row of that capture. Read from the
--   root through declared_records' '$' path (#140 D1), so it is guarded like
--   the element fields.
-- =============================================================================

-- Fields come through declared_records, which selects only the columns
-- declared at `$.elements[*]` in sources.yml (#115): an undeclared field fails
-- the build rather than escaping the presence test.
with raw as (

    {{ declared_records('bootstrap_static', '$.elements[*]') }}

),

-- One row per payload: the fields declared at its root.
root as (

    {{ declared_records('bootstrap_static', '$') }}

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
    cast(raw."id" as integer)                  as fpl_id,

    -- Identity
    cast(raw."web_name" as varchar)            as web_name,
    cast(raw."code" as integer)                as player_code,

    -- Position as of this capture; refers to stg_position.position_id
    cast(raw."element_type" as integer)        as position_id,

    -- Season total as of this capture
    cast(raw."total_points" as integer)        as total_points,

    -- Listed club as of this capture
    cast(raw."team" as integer)                as team_fpl_id,

    -- Status and availability as of this capture
    cast(raw."status" as varchar)              as status,
    cast(raw."chance_of_playing_this_round" as integer)
                                               as chance_of_playing_this_round,
    cast(raw."chance_of_playing_next_round" as integer)
                                               as chance_of_playing_next_round,
    nullif(cast(raw."news" as varchar), '')    as news,
    cast(raw."news_added" as timestamp)        as news_added,
    cast(raw."can_select" as boolean)          as can_select,
    cast(raw."removed" as boolean)             as removed,

    -- Market as of this capture
    cast(raw."now_cost" as integer)            as now_cost,
    cast(nullif(cast(raw."selected_by_percent" as varchar), '') as decimal(4, 1))
                                               as selected_by_percent,
    cast(raw."transfers_in_event" as integer)  as transfers_in_event,
    cast(raw."transfers_out_event" as integer) as transfers_out_event,

    -- The capture's player count, from its root
    cast(root."total_players" as integer)      as total_players

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
inner join root
    on root.capture_key = raw.capture_key
