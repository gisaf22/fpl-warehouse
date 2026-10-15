-- Layer: stg
-- Tests: stg_player_history_capture
-- Asserts: each history[] record staged at capture grain carries exactly the
--          fields declared at $.history[*] in sources.yml, so reading history
--          at the payload root exposes no undeclared field (#115, #175 AC3).
-- Origin: new in #175 (proposed AC3)
-- Tier: integration. Every real history field is declared, so the fixture
--       tree carries one synthetic undeclared field (SYNTHETIC_UNDECLARED in
--       tests/fixtures/build_fixtures.py, fpl_id 611's R4 capture); without
--       the root read's trim to declared fields this lists it.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#175 AC3'}) }}

{%- set declared = [] -%}
{%- if execute -%}
{%- for node in graph.sources.values()
      if node.source_name == 'fpl_raw' and node.name == 'element_summary' -%}
    {%- for column in node.columns.values()
          if (column.meta or {}).get('record_path') == '$.history[*]' -%}
        {%- do declared.append(column.name.split('.')[-1]) -%}
    {%- endfor -%}
{%- endfor -%}
{%- endif %}

with declared (field) as (
    values {% for key in declared %}('{{ key }}'){{ "," if not loop.last }}{% endfor %}
),

staged as (
    select distinct unnest(json_keys(to_json(history[1]))) as field
    from {{ ref('stg_player_history_capture') }}
    where len(history) > 0
)

(select 'staged, not declared' as problem, field from staged
 except
 select 'staged, not declared', field from declared)
union all
(select 'declared, not staged', field from declared
 except
 select 'declared, not staged', field from staged)
