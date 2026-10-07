-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: a key present in every record but null in some of them is reported by neither
--          mode: presence is about the key, not its value.
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC2'}) }}

with captures (capture_key, run_id) as (
    values ('k1', 'r1')
),

objects (capture_key, json) as (
    values ('k1', '{"history": [{"bps": null}, {"bps": 4}]}'::json)
)

{% set specs = [{'column': 'history.bps', 'key': 'bps', 'record_path': '$.history[*]'}] %}
select 'partial' as mode, * from ({{ consumed_key_findings('element_summary', specs, 'captures', 'objects', 'partial') }})
union all
select 'removed', * from ({{ consumed_key_findings('element_summary', specs, 'captures', 'objects', 'removed') }})
