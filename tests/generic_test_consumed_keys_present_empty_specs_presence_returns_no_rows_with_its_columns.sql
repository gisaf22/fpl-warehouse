-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: consumed_key_presence called with no specs returns zero rows, with the
--          columns (names, order and types) of a call with specs.
-- Origin: new in #149
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#149 AC1'}) }}

-- One element-summary capture whose payload holds the key, so the call with
-- specs has a record to read and the empty call has data it must not report.

{% set specs = [{'column': 'history.minutes', 'key': 'minutes', 'record_path': '$.history[*]'}] %}

with captures (capture_key, run_id) as (
    values ('k1', 'r1')
),

objects (capture_key, json) as (
    values ('k1', '{"history": [{"minutes": 90}]}'::json)
),

expected as (
    select row_number() over () as position, column_name, column_type
    from (describe ({{ consumed_key_presence('element_summary', specs, 'captures', 'objects') }}))
),

actual as (
    select row_number() over () as position, column_name, column_type
    from (describe ({{ consumed_key_presence('element_summary', [], 'captures', 'objects') }}))
)


(select 'expected column, not returned' as problem, * from expected
 except select 'expected column, not returned', * from actual)
union all
(select 'returned column, not expected', * from actual
 except select 'returned column, not expected', * from expected)
union all
select 'row returned', null, cast(count(*) as varchar), null
from ({{ consumed_key_presence('element_summary', [], 'captures', 'objects') }})
having count(*) > 0
