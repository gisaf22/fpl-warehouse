-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: every column declared on a source becomes a checked key with no other
--          configuration: the key is the name's last dot-segment and the record
--          path comes from meta.record_path (absent = the payload itself).
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC3'}) }}

-- `elements.new_field` stands in for a column just added to sources.yml with
-- nothing but its name and record path.

{% set specs = consumed_key_specs({
    'elements': {'name': 'elements', 'meta': {}},
    'elements.id': {'name': 'elements.id', 'meta': {'record_path': '$.elements[*]'}},
    'elements.new_field': {'name': 'elements.new_field', 'meta': {'record_path': '$.elements[*]'}}
}) %}

with expected (column_name, key_name, record_path) as (
    values
        ('elements', 'elements', null),
        ('elements.id', 'id', '$.elements[*]'),
        ('elements.new_field', 'new_field', '$.elements[*]')
),

actual (column_name, key_name, record_path) as (
    {%- for s in specs %}
    select '{{ s.column }}', '{{ s.key }}', {{ "'" ~ s.record_path ~ "'" if s.record_path else 'null' }}
    {%- if not loop.last %} union all {% endif %}
    {%- endfor %}
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
