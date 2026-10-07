-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: a key missing from some records but present in others is reported by
--          the partial (warn) mode with the missing count, and not by the
--          removed (error) mode.
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC8'}) }}

with captures (capture_key, run_id) as (
    values ('k1', 'r1'), ('k2', 'r1')
),

objects (capture_key, json) as (
    values
        ('k1', '{"history": [{"bps": 10}, {"minutes": 0}]}'::json),
        ('k2', '{"history": [{"minutes": 45}]}'::json)
),

expected (mode, source_name, column_name, run_id, captures, records, missing) as (
    values ('partial', 'element_summary', 'history.bps', 'r1', 2, 3, 2)
),

actual as (
    {% set specs = [{'column': 'history.bps', 'key': 'bps', 'record_path': '$.history[*]'}] %}
    select 'partial' as mode, source_name, column_name, run_id, captures, records, missing
    from ({{ consumed_key_findings('element_summary', specs, 'captures', 'objects', 'partial') }})
    union all
    select 'removed', source_name, column_name, run_id, captures, records, missing
    from ({{ consumed_key_findings('element_summary', specs, 'captures', 'objects', 'removed') }})
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
