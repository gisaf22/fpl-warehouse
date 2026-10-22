-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_manager_gameweek_points
-- =============================================================================
--
-- Purpose:
--   FPL's own points total for each captured manager-gameweek beside the total
--   rebuilt from the picks (#216 D7, amended by O3): the sum over the 15 picks
--   of multiplier x the player's fct_player_gameweek points, a blank gameweek
--   (NULL points) counting 0. The multiplier carries the captain, the chip and
--   the automatic subs, which FPL has already applied. The transfer cost is
--   not in FPL's points. Read only by the reconciliation test; not served (D9).
-- =============================================================================

select
    grid.season,
    grid.entry_id,
    grid.gameweek,
    captures.active_chip,
    captures.points                                                  as fpl_points,
    sum(picks.multiplier * coalesce(players.total_points, 0))        as rebuilt_points
from {{ ref('int_manager_gameweek_status') }} as grid
inner join {{ ref('stg_entry_picks_capture') }} as captures
    on captures.capture_key = grid.capture_key
inner join {{ ref('stg_entry_picks') }} as picks
    on picks.capture_key = grid.capture_key
left join {{ ref('fct_player_gameweek') }} as players
    on players.season = grid.season
   and players.gameweek = grid.gameweek
   and players.fpl_id = picks.fpl_id
where grid.status = 'captured'
group by grid.season, grid.entry_id, grid.gameweek, captures.active_chip, captures.points
