-- =============================================================================
-- Layer: stg_ (staging)
-- Model: stg_entry_picks_capture
-- =============================================================================
--
-- Purpose:
--   One row per admitted entry-picks capture (#216): a panel manager's picks
--   for one gameweek, typed and renamed. The one read of the entry-picks
--   source; stg_entry_picks unnests `picks` from this table.
--
-- Grain:
--   One row per capture_key.
--
-- Source:
--   fpl_raw.entry_picks at the payload root, read through declared_records
--   (#115): `picks` and `automatic_subs` are lists, and `entry_history` a
--   struct (#216 AC22), each holding only the declared fields. The read is
--   compacted gameweeks plus the raw tail (entry_picks_compacted_read, D8).
--
-- Capture identity:
--   Every capture column comes from int_admitted_capture (#104), so only
--   admitted captures are staged. The entry id is not in the payload: it is
--   the fourth segment of the index's endpoint, `entry-picks/<season>/<gw>/
--   <entry_id>`. The gameweek is the payload's own entry_history.event.
--
-- Points:
--   `points` is FPL's entry_history.points: the sum of multiplier x player
--   points over the 15 picks, without the transfer cost (#216 D7). It feeds
--   the reconciliation only and is not served.
--
-- Overall rank:
--   `overall_rank` is FPL's entry_history.overall_rank as raw has it: 0 stays
--   0 and null stays null (#219 D1). fct_manager_gameweek serves both as NULL.
-- =============================================================================

with raw as (

    {{ declared_records('entry_picks', '$') }}

)

select
    -- Capture identity, from the capture index (see int_admitted_capture)
    admitted.capture_key,
    admitted.season,
    admitted.run_id,
    admitted.observed_at,

    -- Keys
    cast(split_part(admitted.endpoint, '/', 4) as integer)        as entry_id,
    cast(raw."entry_history"."event" as integer)                  as gameweek,

    -- The manager's gameweek
    cast(raw."active_chip" as varchar)                            as active_chip,
    cast(raw."entry_history"."points" as integer)                 as points,
    cast(raw."entry_history"."event_transfers" as integer)        as event_transfers,
    cast(raw."entry_history"."event_transfers_cost" as integer)   as event_transfers_cost,
    -- As raw has it: FPL reports no valid rank as null or 0 (#219 D1)
    cast(raw."entry_history"."overall_rank" as integer)           as overall_rank,
    list_transform(raw."automatic_subs", lambda s: struct_pack(
        fpl_id_out := cast(s."element_out" as integer),
        fpl_id_in := cast(s."element_in" as integer)
    ))                                                            as automatic_subs,

    -- The 15 picks, after automatic substitutions (GLOSSARY.md, slot)
    len(raw."picks")                                              as pick_count,
    list_transform(raw."picks", lambda p: struct_pack(
        slot := cast(p."position" as integer),
        fpl_id := cast(p."element" as integer),
        multiplier := cast(p."multiplier" as integer),
        is_captain := cast(p."is_captain" as boolean),
        is_vice_captain := cast(p."is_vice_captain" as boolean)
    ))                                                            as picks

from raw
inner join {{ ref('int_admitted_capture') }} as admitted
    on admitted.capture_key = raw.capture_key
