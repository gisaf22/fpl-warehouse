-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: keys are checked both at the top level of a payload and inside nested
--          record arrays (one level and two levels deep).
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC1'}) }}

-- One bootstrap-shaped capture and one fixtures-shaped capture are checked
-- separately. Missing: top-level `teams`, nested `elements[].code`, and the
-- doubly nested `stats[].identifier`. Present: top-level `elements`,
-- `elements[].id`, fixture `event`.

with captures (capture_key, run_id) as (
    values ('b1', 'r1')
),

objects (capture_key, json) as (
    values ('b1', '{"elements": [{"id": 1}, {"id": 2}], "events": []}'::json)
),

fixture_captures (capture_key, run_id) as (
    values ('f1', 'r1')
),

fixture_objects (capture_key, json) as (
    values ('f1', '[{"event": 1, "stats": [{"value": 1}]}, {"event": 2, "stats": [{"value": 0}]}]'::json)
),

expected (source_name, column_name, run_id, captures, records, missing) as (
    values
        ('bootstrap_static', 'teams', 'r1', 1, 1, 1),
        ('bootstrap_static', 'elements.code', 'r1', 1, 2, 2),
        ('fixtures', 'stats.identifier', 'r1', 1, 2, 2)
),

actual as (
    select source_name, column_name, run_id, captures, records, missing
    from (
        {{ consumed_key_findings(
            'bootstrap_static',
            [{'column': 'elements', 'key': 'elements', 'record_path': none},
             {'column': 'teams', 'key': 'teams', 'record_path': none},
             {'column': 'elements.id', 'key': 'id', 'record_path': '$.elements[*]'},
             {'column': 'elements.code', 'key': 'code', 'record_path': '$.elements[*]'}],
            'captures', 'objects', 'removed'
        ) }}
    )
    union all
    select source_name, column_name, run_id, captures, records, missing
    from (
        {{ consumed_key_findings(
            'fixtures',
            [{'column': 'event', 'key': 'event', 'record_path': '$[*]'},
             {'column': 'stats.identifier', 'key': 'identifier', 'record_path': '$[*].stats[*]'}],
            'fixture_captures', 'fixture_objects', 'removed'
        ) }}
    )
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
