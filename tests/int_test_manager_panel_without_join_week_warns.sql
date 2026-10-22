-- Layer: int
-- Tests: dim_manager_panel, stg_entry_picks_settlement
-- Asserts: no panel manager is without a join week in a season that has
--          marked gameweeks. Ingest keeps a manager only if they had picks at
--          the draw, so a kept manager with no admitted capture in any marked
--          gameweek means a capture is missing (D6's limit). Warns; the
--          scheduled build's job summary and an annotation name each manager.
-- Origin: new in #216 (N1, D13)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], severity='warn', meta={'covers': '#216 AC1'}) }}

select panel.season, panel.entry_id, panel.cohort
from {{ ref('dim_manager_panel') }} as panel
where panel.first_active_gw is null
  and exists (
      select 1
      from {{ ref('stg_entry_picks_settlement') }} as markers
      where markers.season = panel.season
  )
