-- =============================================================================
-- Layer: fct_ (marts, served)
-- Model: fct_manager_gameweek
-- =============================================================================
--
-- Purpose:
--   One row per (season, entry_id, gameweek) for every captured
--   manager-gameweek (#216 D9, D10): the manager's cohort, chip, transfers,
--   transfer cost and FPL's automatic substitutions. Absent, never NULL, for a
--   gameweek before the join week or without a settlement marker (D4, D5).
--   FPL's points total is not served (D9).
--
-- Overall rank (#219 D1):
--   The manager's overall rank at the end of the gameweek, from the winning
--   capture. NULL where FPL reports no valid rank, as null or 0 (cause
--   unknown); staging keeps the 0. Keyed to the same gameweek as
--   dim_gameweek.ranked_count; any lag is the consumer's.
-- =============================================================================

select
    grid.season,
    grid.entry_id,
    grid.gameweek,
    panel.cohort,
    captures.active_chip,
    captures.event_transfers,
    captures.event_transfers_cost,
    captures.automatic_subs,
    -- FPL reports a team with no valid rank as null or 0 (#219 D1)
    nullif(captures.overall_rank, 0) as overall_rank
from {{ ref('int_manager_gameweek_status') }} as grid
inner join {{ ref('stg_entry_picks_capture') }} as captures
    on captures.capture_key = grid.capture_key
inner join {{ ref('dim_manager_panel') }} as panel
    on panel.season = grid.season
   and panel.entry_id = grid.entry_id
where grid.status = 'captured'
