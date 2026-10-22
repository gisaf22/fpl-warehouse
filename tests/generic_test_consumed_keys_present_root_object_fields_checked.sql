-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: a key declared inside a root object (record_path '$.<object>', not
--          an array) is checked once per payload, in that object.
-- Origin: new in #216 (proposed AC22: entry-picks' entry_history)
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#216 AC22'}) }}

-- Two picks-shaped captures. Present in both: entry_history.points. Missing
-- from one: entry_history.overall_rank.

with captures (capture_key, run_id) as (
    values ('p1', 'r1'), ('p2', 'r1')
),

objects (capture_key, json) as (
    values
        ('p1', '{"entry_history": {"points": 56, "overall_rank": 10}, "picks": []}'::json),
        ('p2', '{"entry_history": {"points": 40}, "picks": []}'::json)
),

expected (source_name, column_name, run_id, captures, records, missing) as (
    values ('entry_picks', 'entry_history.overall_rank', 'r1', 2, 2, 1)
),

actual as (
    select source_name, column_name, run_id, captures, records, missing
    from (
        {{ consumed_key_findings(
            'entry_picks',
            [{'column': 'entry_history.points', 'key': 'points', 'record_path': '$.entry_history'},
             {'column': 'entry_history.overall_rank', 'key': 'overall_rank', 'record_path': '$.entry_history'}],
            'captures', 'objects', 'partial'
        ) }}
    )
)

(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
