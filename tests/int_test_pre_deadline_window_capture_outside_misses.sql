-- Layer: int
-- Tests: missed_pre_deadline_windows (macro)
-- Asserts: a passed in-scope deadline whose only captures are outside
--          [deadline - 125m, deadline) or from another season is reported,
--          with its season, gameweek and deadline.
-- Origin: new in #111
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#111 AC2'}) }}

with gameweeks (season, gameweek, deadline_time, observed_at, run_id) as (
    values
        ('2026-27', 6, timestamp '2026-10-10 10:00:00', timestamp '2026-10-10 12:00:00', 'r1')
),

captures (season, observed_at) as (
    values
        -- one second before the window opens
        ('2026-27', timestamp '2026-10-10 07:54:59'),
        -- exactly at the deadline, which is exclusive
        ('2026-27', timestamp '2026-10-10 10:00:00'),
        -- after the deadline
        ('2026-27', timestamp '2026-10-10 11:00:00'),
        -- inside the window, but another season's capture
        ('2025-26', timestamp '2026-10-10 09:00:00')
),

expected (season, gameweek, deadline_time) as (
    values ('2026-27', 6, timestamp '2026-10-10 10:00:00')
),

actual as (
    {{ missed_pre_deadline_windows('gameweeks', 'captures', "timestamp '2026-10-20 00:00:00'") }}
)

(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', season, gameweek, deadline_time from actual)
union all
(select 'reported, not expected', season, gameweek, deadline_time from actual
 except select 'reported, not expected', * from expected)
