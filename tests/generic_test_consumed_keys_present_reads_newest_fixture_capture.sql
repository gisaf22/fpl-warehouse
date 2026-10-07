-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: against the fixture tree, the removed mode reads bootstrap-static's
--          newest admitted live capture that has bytes and reports a declared key absent
--          from it, and only that key.
-- Origin: new in #114
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#114 AC1'}) }}
-- depends_on: {{ ref('int_admitted_capture') }}

-- `elements.id` is in every element of every capture; `elements.no_such_key`
-- is in none. The newest live bootstrap-static run in tests/fixtures/raw is
-- 20260914T211204Z-a730c3 (one capture, 2026-09-14): 20261003T052050Z-fa64a9 is
-- newer but index-only, with no payload in the tree, so it cannot be read..

-- Fixture-only: the expected run is a fact about tests/fixtures/raw. Against
-- live data the newest run is a different one every build, and the declared
-- columns are covered there by the applied source tests instead.

{% if target.name != 'fixtures' %}

select null as source_name where false

{% else %}

with expected (source_name, column_name, run_id, captures, missing_equals_records) as (
    values ('bootstrap_static', 'elements.no_such_key', '20260914T211204Z-a730c3', 1, true)
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

{% endif %}
