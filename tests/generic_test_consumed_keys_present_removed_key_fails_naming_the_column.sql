-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: a declared key absent from every record of the latest capture is reported
--          by the removed mode, naming the source, column, run and counts.
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC1'}) }}

-- Two element-summary captures from one run. `minutes` is in every history
-- record; `bps` is in none, as if FPL removed it.

with captures (capture_key, run_id) as (
    values ('k1', 'r1'), ('k2', 'r1')
),

objects (capture_key, json) as (
    values
        ('k1', '{"history": [{"minutes": 90}, {"minutes": 0}]}'::json),
        ('k2', '{"history": [{"minutes": 45}]}'::json)
),

expected (source_name, column_name, run_id, captures, records, missing) as (
    values ('element_summary', 'history.bps', 'r1', 2, 3, 3)
),

actual as (
    select source_name, column_name, run_id, captures, records, missing
    from (
        {{ consumed_key_findings(
            'element_summary',
            [{'column': 'history.minutes', 'key': 'minutes', 'record_path': '$.history[*]'},
             {'column': 'history.bps', 'key': 'bps', 'record_path': '$.history[*]'}],
            'captures', 'objects', 'removed'
        ) }}
    )
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
