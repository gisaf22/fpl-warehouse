-- Layer: generic
-- Tests: consumed_keys_present (tests/generic/consumed_keys_present.sql)
-- Asserts: when the latest admitted live run has captures with no payload
--          file, the newest captures that have one are checked instead, and
--          the partial (warn) mode reports the latest run and how many of its
--          captures lack a file; the removed (error) mode does not.
-- Origin: new in #114 (D3 amended on review of #116)
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#114 AC1'}) }}

-- r2 is the newest run and has two captures; neither has a file. r1 is
-- older and its one capture does.

with admitted (capture_key, endpoint, run_id, observed_at) as (
    values
        ('raw/fpl/fixtures/2026-10-01/r1/payload.json', 'fixtures', 'r1', timestamp '2026-10-01 07:00:00'),
        ('raw/fpl/fixtures/2026-10-02/r2/payload.json', 'fixtures', 'r2', timestamp '2026-10-02 07:00:00'),
        ('raw/fpl/fixtures/2026-10-02/r2/other.json',   'fixtures', 'r2', timestamp '2026-10-02 07:00:01')
),

present (capture_key) as (
    values ('raw/fpl/fixtures/2026-10-01/r1/payload.json')
),

chosen as (
    {{ latest_live_run_captures('admitted', 'fixtures', 'present') }}
),

gap as (
    {{ latest_live_run_missing_bytes('admitted', 'fixtures', 'present') }}
),

presence as (
    select
        'fixtures' as source_name, 'event' as column_name,
        (select min(run_id) from chosen) as run_id,
        (select count(*) from chosen) as captures,
        10 as records, 0 as missing,
        (select run_id from gap) as latest_run_id,
        coalesce((select captures_without_bytes from gap), 0) as latest_run_missing_bytes
),

expected (mode, source_name, run_id, missing, checked_run) as (
    values ('partial', 'fixtures', 'r2', 2, 'r1')
),

actual as (
    select 'partial' as mode, f.source_name, f.run_id, f.missing, (select run_id from presence)
    from ({{ presence_findings('presence', 'partial') }}) as f
    union all
    select 'removed', f.source_name, f.run_id, f.missing, (select run_id from presence)
    from ({{ presence_findings('presence', 'removed') }}) as f
)

(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', * from actual)
union all
(select 'reported, not expected', * from actual
 except select 'reported, not expected', * from expected)
