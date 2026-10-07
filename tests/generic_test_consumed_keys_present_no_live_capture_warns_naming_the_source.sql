-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: with no admitted live capture, the removed mode reports nothing and the
--          partial (warn) mode reports one row naming the source.
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC7'}) }}

with captures (capture_key, run_id) as (
    select 'k', 'r' where false
),

objects (capture_key, json) as (
    select 'k', '{}'::json where false
),

expected (mode, source_name, finding) as (
    values ('partial', 'event_status', 'no admitted live capture')
),

actual as (
    {% set specs = [{'column': 'status', 'key': 'status', 'record_path': none}] %}
    select 'partial' as mode, source_name, finding
    from ({{ consumed_key_findings('event_status', specs, 'captures', 'objects', 'partial') }})
    union all
    select 'removed', source_name, finding
    from ({{ consumed_key_findings('event_status', specs, 'captures', 'objects', 'removed') }})
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
