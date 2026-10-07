-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: against the fixture tree, the removed mode reads bootstrap-static's
--          newest admitted live capture and reports a declared key absent
--          from it, and only that key.
-- Origin: new in #114
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#114 AC1'}) }}

-- `elements.id` is in every element of every capture; `elements.no_such_key`
-- is in none. The newest live bootstrap-static run in tests/fixtures/raw is
-- 20261003T052050Z-fa64a9 (one capture, 2026-10-03).

with expected (source_name, column_name, run_id, captures, missing_equals_records) as (
    values ('bootstrap_static', 'elements.no_such_key', '20261003T052050Z-fa64a9', 1, true)
),

actual as (
    select source_name, column_name, run_id, captures, missing = records and records > 0
    from (
        {{ test_consumed_keys_present(
            model=source('fpl_raw', 'bootstrap_static'),
            mode='removed',
            columns={
                'elements.id': {'name': 'elements.id', 'meta': {'record_path': '$.elements[*]'}},
                'elements.no_such_key': {'name': 'elements.no_such_key', 'meta': {'record_path': '$.elements[*]'}}
            }
        ) }}
    )
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
