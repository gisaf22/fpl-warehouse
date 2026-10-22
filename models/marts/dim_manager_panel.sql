-- =============================================================================
-- Layer: dim_ (marts, private)
-- Model: dim_manager_panel
-- =============================================================================
--
-- Purpose:
--   One row per (season, entry_id): a panel manager, their cohort and their
--   join week (#216 D6, D10). Private: not served (D9).
--
-- Join week (D6, amended by O1):
--   The manager's first marked gameweek with an admitted picks capture. A
--   capture in an unmarked gameweek does not count (D4). NULL when the
--   manager has none: every marked gameweek then reads not_yet_joined (AC1),
--   and int_test_manager_panel_without_join_week_warns names them (N1).
--   History is not read: over half the panel's entry-history captures are in
--   a run that never finalized (gisaf22/fpl-ingest#126).
-- =============================================================================

with join_weeks as (

    select captures.season, captures.entry_id, min(captures.gameweek) as first_active_gw
    from {{ ref('stg_entry_picks_capture') }} as captures
    inner join {{ ref('stg_entry_picks_settlement') }} as markers
        on markers.season = captures.season
       and markers.gameweek = captures.gameweek
    group by captures.season, captures.entry_id

)

select
    panel.season,
    panel.entry_id,
    panel.cohort,
    join_weeks.first_active_gw
from {{ ref('stg_manager_panel') }} as panel
left join join_weeks
    on join_weeks.season = panel.season
   and join_weeks.entry_id = panel.entry_id
