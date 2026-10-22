-- Layer: fct
-- Tests: fct_manager_gameweek
-- Asserts: each row's cohort is its manager's cohort in the season's panel;
--          the fixture holds both cohorts, so the check is not vacuous.
-- Origin: new in #216 (D10)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC11'}) }}

select served.season, served.entry_id, served.gameweek, served.cohort, panel.cohort as panel_cohort
from {{ ref('fct_manager_gameweek') }} as served
left join {{ ref('stg_manager_panel') }} as panel using (season, entry_id)
where served.cohort is distinct from panel.cohort

{% if target.name == 'fixtures' %}
union all
select null, null, null, required, null
from (values ('random'), ('self')) as t(required)
where required not in (select cohort from {{ ref('fct_manager_gameweek') }})
{% endif %}
