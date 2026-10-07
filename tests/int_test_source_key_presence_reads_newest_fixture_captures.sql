-- Layer: int
-- Tests: int_source_key_presence
-- Asserts: against the fixture tree, each payload source is read from its
--          newest admitted live run with payload files, a run with captures
--          lacking a file is named with their count, and every declared column
--          is a key in every record read.
-- Origin: new in #114, replacing the fixture test of the generic test, which
--         read the raw objects itself before int_source_key_presence existed
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#114 AC1'}) }}

-- Fixture-only: the expected runs are facts about tests/fixtures/raw
-- (tests/fixtures/build_fixtures.py). 20261003T052050Z-fa64a9 is the
-- index-only run (INDEX_22_RUN): bootstrap-static and fixtures are indexed
-- there with no payload. 20260914T211204Z-a730c3 is the newest run with files,
-- and its catalog adds a synthetic element-summary capture (fpl_id 9999, a
-- failed revalidation, still admitted) with no payload. event-status's newest
-- run has every file.

{% if target.name != 'fixtures' %}

select null as source_name where false

{% else %}

with expected (source_name, run_id, latest_run_id, latest_run_missing_bytes) as (
    values
        ('bootstrap_static', '20260914T211204Z-a730c3', '20261003T052050Z-fa64a9', 1),
        ('element_summary',  '20260914T211204Z-a730c3', '20260914T211204Z-a730c3', 1),
        ('event_status',     '20260914T211204Z-a730c3', null,                      0),
        ('fixtures',         '20260914T211204Z-a730c3', '20261003T052050Z-fa64a9', 1)
),

actual as (
    select distinct source_name, run_id, latest_run_id, latest_run_missing_bytes
    from {{ ref('int_source_key_presence') }}
)

(select 'expected, not found' as problem, source_name, run_id, latest_run_id,
        cast(latest_run_missing_bytes as bigint), null as column_name
 from expected
 except
 select 'expected, not found', *, null from actual)
union all
(select 'found, not expected', *, null from actual
 except
 select 'found, not expected', source_name, run_id, latest_run_id,
        cast(latest_run_missing_bytes as bigint), null
 from expected)
union all
select 'declared key missing or unread', source_name, run_id, latest_run_id,
       latest_run_missing_bytes, column_name
from {{ ref('int_source_key_presence') }}
where records = 0 or missing > 0

{% endif %}
