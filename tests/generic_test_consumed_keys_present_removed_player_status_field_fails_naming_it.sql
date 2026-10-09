-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: when any one of the player status fields is missing from every
--          element of the latest admitted live bootstrap-static run, the
--          removed (error) mode reports that field, and only that field.
-- Origin: new in #124
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#124 AC2'}) }}

-- Fixture-only: it reads every bootstrap-static capture once per field, which
-- is cheap over tests/fixtures/raw and not over the live tree. The live build
-- runs the real removed test over the real payload instead.
--
-- For each field, the fixture's latest run is re-served with that key dropped
-- from every element, as if FPL had removed it, and checked against the specs
-- the source declares. An undeclared field has no spec and is never reported,
-- so it fails here too.

{% set fields = [
    'status', 'chance_of_playing_this_round', 'chance_of_playing_next_round',
    'news', 'news_added', 'can_select', 'removed', 'team', 'element_type', 'code'
] %}

{%- set specs = [] -%}
{%- if execute -%}
    {%- for node in graph.sources.values()
          if node.source_name == 'fpl_raw' and node.name == 'bootstrap_static' -%}
        {%- for spec in consumed_key_specs(node.columns)
              if spec.record_path == '$.elements[*]' and spec.key in fields -%}
            {%- do specs.append(spec) -%}
        {%- endfor -%}
    {%- endfor -%}
{%- endif -%}

{% if target.name != 'fixtures' %}

select null as column_name where false

{% else %}

with records as (
    {{ declared_records('bootstrap_static', '$.elements[*]') }}
),

captures as (
    {{ latest_live_run_captures(
        ref('int_admitted_capture'), 'bootstrap-static',
        '(select distinct capture_key from records)') }}
),

{%- for field in fields %}

without_{{ field }} as (
    select
        records.capture_key,
        json_object('elements', json_group_array(
            json_merge_patch(to_json(records), '{"{{ field }}": null}')
        )) as json
    from records
    where records.capture_key in (select capture_key from captures)
    group by records.capture_key
),
{%- endfor %}

expected (column_name, finding) as (
    values
    {%- for field in fields %}
        ('elements.{{ field }}', 'key absent from every record'){{ "," if not loop.last }}
    {%- endfor %}
),

actual as (
    {%- for field in fields %}
    select column_name, finding
    from ({{ consumed_key_findings('bootstrap_static', specs, 'captures', 'without_' ~ field, 'removed') }})
    {%- if not loop.last %}
    union all
    {%- endif %}
    {%- endfor %}
)

(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)

{% endif %}
