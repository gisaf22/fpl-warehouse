-- =============================================================================
-- Layer: fct_ (marts, served)
-- Model: fct_manager_pick
-- =============================================================================
--
-- Purpose:
--   One row per (season, entry_id, gameweek, slot) for every captured
--   manager-gameweek (#216 D9): the pick in that slot as FPL returned it,
--   after automatic substitutions, with the captain flags and whether FPL
--   substituted the player in or out. The chosen eleven is the slot 1-11 rows
--   not subbed in plus the rows subbed out (D7, amended by O4). No points: a
--   consumer joins fct_player_gameweek.
-- =============================================================================

with captured as (

    select grid.season, grid.entry_id, grid.gameweek, grid.capture_key
    from {{ ref('int_manager_gameweek_status') }} as grid
    where grid.status = 'captured'

)

select
    captured.season,
    captured.entry_id,
    captured.gameweek,
    picks.slot,
    picks.fpl_id,
    picks.is_captain,
    picks.is_vice_captain,
    list_contains(list_transform(captures.automatic_subs, s -> s.fpl_id_in), picks.fpl_id)
        as is_auto_sub_in,
    list_contains(list_transform(captures.automatic_subs, s -> s.fpl_id_out), picks.fpl_id)
        as is_auto_sub_out
from captured
inner join {{ ref('stg_entry_picks') }} as picks
    on picks.capture_key = captured.capture_key
inner join {{ ref('stg_entry_picks_capture') }} as captures
    on captures.capture_key = captured.capture_key
