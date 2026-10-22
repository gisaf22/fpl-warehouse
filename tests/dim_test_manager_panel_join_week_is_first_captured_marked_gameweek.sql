-- Layer: dim
-- Tests: dim_manager_panel
-- Asserts: each panel manager's first_active_gw is their first marked gameweek
--          with an admitted picks capture, and NULL when they have none; the
--          fixture holds a manager whose join week is after gameweek 1, so the
--          check is not vacuous.
-- Origin: new in #216 (D6, amended by O1: the join week comes from picks)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC6'}) }}

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
    join_weeks.first_active_gw as expected,
    dim.first_active_gw        as actual
from {{ ref('stg_manager_panel') }} as panel
left join join_weeks using (season, entry_id)
left join {{ ref('dim_manager_panel') }} as dim using (season, entry_id)
where dim.entry_id is null
   or dim.first_active_gw is distinct from join_weeks.first_active_gw

{% if target.name == 'fixtures' %}
union all
select null, null, null, null
where not exists (select 1 from {{ ref('dim_manager_panel') }} where first_active_gw > 1)
{% endif %}
