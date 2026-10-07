-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: the latest admitted live run per endpoint is the one checked, with all of
--          its captures: a key present only in an older run's capture of
--          another player still errors, and history-port captures are ignored.
-- Origin: new in #114
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC1'}) }}

-- Player 1 was last captured in r1, whose payload still has `bps`. Player 2
-- was captured in r2, the newest live run, without it. A per-player "latest
-- capture" would include player 1's r1 object and downgrade the removal to a
-- partial warning; the newest run alone must report it as removed. A later
-- history-port capture and another endpoint's newer run must not be chosen.

with admitted (capture_key, endpoint, run_id, observed_at) as (
    values
        ('raw/fpl/element-summary/1/2026-10-01/r1/payload.json', 'element-summary/1', 'r1', timestamp '2026-10-01 07:00:00'),
        ('raw/fpl/element-summary/2/2026-10-02/r2/payload.json', 'element-summary/2', 'r2', timestamp '2026-10-02 07:00:00'),
        ('raw/fpl/bootstrap-static/2026-10-03/r3/payload.json', 'bootstrap-static', 'r3', timestamp '2026-10-03 07:00:00'),
        ('history/2025-26/fpl/element-summary/1/2026-10-04/h1/payload.json', 'element-summary/1', 'h1', timestamp '2026-10-04 07:00:00')
),

captures as (
    {{ latest_live_run_captures('admitted', 'element-summary') }}
),

objects (capture_key, json) as (
    values
        ('raw/fpl/element-summary/1/2026-10-01/r1/payload.json', '{"history": [{"bps": 10}]}'::json),
        ('raw/fpl/element-summary/2/2026-10-02/r2/payload.json', '{"history": [{"minutes": 90}]}'::json),
        ('history/2025-26/fpl/element-summary/1/2026-10-04/h1/payload.json', '{"history": [{"bps": 3}]}'::json)
),

expected (source_name, column_name, run_id, captures, records, missing) as (
    values ('element_summary', 'history.bps', 'r2', 1, 1, 1)
),

actual as (
    select source_name, column_name, run_id, captures, records, missing
    from (
        {{ consumed_key_findings(
            'element_summary',
            [{'column': 'history.bps', 'key': 'bps', 'record_path': '$.history[*]'}],
            'captures', 'objects', 'removed'
        ) }}
    )
)


(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
