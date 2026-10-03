-- Layer: stg
-- Tests: every staging model
-- Asserts: no staging model outputs a `round` column, stg_event_status is gone
--          and stg_gameweek_status exists — the project says gameweek from
--          staging onward.
-- Origin: new in #101 (C2a of #88), finishing #89's rename
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#101 AC1'}) }}

-- Models are read from dbt's graph, not from the database file, so a table
-- left behind by an older build cannot satisfy or fail the check.

{% set staging = [] %}
{% if execute %}
    {% for node in graph.nodes.values()
          if node.resource_type == 'model' and node.fqn[1] == 'staging' %}
        {% do staging.append(node.name) %}
    {% endfor %}
{% endif %}

select table_name as model, 'has a round column' as failure
from information_schema.columns
where column_name = 'round'
  and table_name in (
      {%- for name in staging %}'{{ name }}'{{ ', ' if not loop.last }}{% endfor -%}
  )

union all

select 'stg_event_status', 'still a model'
where {{ 'true' if 'stg_event_status' in staging else 'false' }}

union all

select 'stg_gameweek_status', 'is not a model'
where {{ 'false' if 'stg_gameweek_status' in staging else 'true' }}
