-- Layer: dim
-- Tests: dim_manager_panel
-- Asserts: each panel manager's first_active_gw is the first gameweek of their
--          entry-history's current[] in its latest admitted capture, and every
--          panel manager has one; the fixture holds a manager whose join week
--          is after gameweek 1, so the check is not vacuous.
-- Origin: new in #216 (D6)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC6'}) }}

with latest_capture as (

    select season, entry_id, capture_key
    from {{ ref('stg_entry_history') }}
    qualify row_number() over (
        partition by season, entry_id
        order by observed_at desc, run_id desc
    ) = 1

),

join_weeks as (

    select history.season, history.entry_id, min(history.gameweek) as first_active_gw
    from {{ ref('stg_entry_history') }} as history
    inner join latest_capture using (season, entry_id, capture_key)
    group by history.season, history.entry_id

)

select
    panel.season,
    panel.entry_id,
    join_weeks.first_active_gw as expected,
    dim.first_active_gw        as actual
from {{ ref('stg_manager_panel') }} as panel
left join join_weeks using (season, entry_id)
left join {{ ref('dim_manager_panel') }} as dim using (season, entry_id)
where dim.first_active_gw is distinct from join_weeks.first_active_gw
   or dim.first_active_gw is null

{% if target.name == 'fixtures' %}
union all
select null, null, null, null
where not exists (select 1 from {{ ref('dim_manager_panel') }} where first_active_gw > 1)
{% endif %}
