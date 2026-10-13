-- Layer: int
-- Tests: int_unstaged_admitted_capture
-- Asserts: against the fixture tree, the unstaged admitted captures are
--          exactly the three known gaps, each at its endpoint's severity, and
--          no capture of an endpoint without a staging source is listed.
-- Origin: new in #167 (G4, G6)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#167 AC2'}) }}

-- Fixture-only: the expected rows are facts about tests/fixtures/raw
-- (tests/fixtures/build_fixtures.py, CAPTURE INDEX). 20261003T052050Z-fa64a9
-- is the index-only 2.2.0 run: its bootstrap-static and fixtures captures
-- have no payload. fpl_id 9999 is the synthetic failed revalidation, admitted
-- with no payload. event-live/04 is admitted with no payload too, but no
-- staging model reads event-live, so it must not appear.

{% if target.name != 'fixtures' %}

select null as capture_key where false

{% else %}

with expected (endpoint, season, run_id, capture_key, severity) as (
    values
        ('bootstrap-static', '2026-27', '20261003T052050Z-fa64a9',
         'raw/fpl/bootstrap-static/2026-10-03/20261003T052050Z-fa64a9/payload.json', 'error'),
        ('fixtures', '2026-27', '20261003T052050Z-fa64a9',
         'raw/fpl/fixtures/2026-10-03/20261003T052050Z-fa64a9/payload.json', 'error'),
        ('element-summary', '2026-27', '20260914T211204Z-a730c3',
         'raw/fpl/element-summary/9999/2026-09-14/20260914T211204Z-a730c3/payload.json', 'warn')
),

actual as (
    select endpoint, season, run_id, capture_key, severity
    from {{ ref('int_unstaged_admitted_capture') }}
)

(select 'expected, not found' as problem, * from expected
 except all
 select 'expected, not found', * from actual)
union all
(select 'found, not expected', * from actual
 except all
 select 'found, not expected', * from expected)

{% endif %}
