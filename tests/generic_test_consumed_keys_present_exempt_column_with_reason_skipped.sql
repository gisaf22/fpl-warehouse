-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: a column with a non-empty meta.presence_exempt reason is not checked;
--          the other columns still are.
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC4'}) }}

{% set specs = consumed_key_specs({
    'elements.id': {'name': 'elements.id', 'meta': {'record_path': '$.elements[*]'}},
    'elements.news': {'name': 'elements.news', 'meta': {'record_path': '$.elements[*]', 'presence_exempt': 'FPL omits it for players with no news'}}
}) %}

with expected (column_name) as (
    values ('elements.id')
),

actual (column_name) as (
    {%- for s in specs %}
    select '{{ s.column }}'
    {%- if not loop.last %} union all {% endif %}
    {%- endfor %}
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
