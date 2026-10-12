-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: consumed_key_findings called with no specs returns zero rows in both
--          modes, with the columns (names, order and types) of a call with specs.
-- Origin: new in #149
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#149 AC1'}) }}

-- One element-summary capture whose payload holds the key, so the call with
-- specs has a record to read and the empty call has data it must not report.

{% set specs = [{'column': 'history.minutes', 'key': 'minutes', 'record_path': '$.history[*]'}] %}
{% set modes = ['removed', 'partial'] %}

with captures (capture_key, run_id) as (
    values ('k1', 'r1')
),

objects (capture_key, json) as (
    values ('k1', '{"history": [{"minutes": 90}]}'::json)
)
{%- for mode in modes %},

expected_{{ mode }} as (
    select row_number() over () as position, column_name, column_type
    from (describe ({{ consumed_key_findings('element_summary', specs, 'captures', 'objects', mode) }}))
),

actual_{{ mode }} as (
    select row_number() over () as position, column_name, column_type
    from (describe ({{ consumed_key_findings('element_summary', [], 'captures', 'objects', mode) }}))
)
{%- endfor %}

{% for mode in modes %}
(select '{{ mode }}: expected column, not returned' as problem, * from expected_{{ mode }}
 except select '{{ mode }}: expected column, not returned', * from actual_{{ mode }})
union all
(select '{{ mode }}: returned column, not expected', * from actual_{{ mode }}
 except select '{{ mode }}: returned column, not expected', * from expected_{{ mode }})
union all
select '{{ mode }}: row returned', null, cast(count(*) as varchar), null
from ({{ consumed_key_findings('element_summary', [], 'captures', 'objects', mode) }})
having count(*) > 0
{%- if not loop.last %}
union all
{%- endif %}
{% endfor %}
