-- Layer: int
-- Tests: missed_pre_deadline_windows (macro)
-- Asserts: when a gameweek's deadline moved between captures, the window is
--          taken from the latest capture's deadline.
-- Origin: new in #111, as #80 AC5
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#111 AC5'}) }}

with gameweeks (season, gameweek, deadline_time, observed_at, run_id) as (
    values
        -- gameweek 6 moved from Saturday 10:00 to Friday 18:30
        ('2026-27', 6, timestamp '2026-10-10 10:00:00', timestamp '2026-10-01 07:00:00', 'r1'),
        ('2026-27', 6, timestamp '2026-10-09 18:30:00', timestamp '2026-10-05 07:00:00', 'r2'),
        -- gameweek 7 moved the other way; its only capture fits the old deadline
        ('2026-27', 7, timestamp '2026-10-17 10:00:00', timestamp '2026-10-01 07:00:00', 'r1'),
        ('2026-27', 7, timestamp '2026-10-17 14:00:00', timestamp '2026-10-05 07:00:00', 'r2')
),

captures (season, observed_at) as (
    values
        -- inside the new gameweek 6 window only
        ('2026-27', timestamp '2026-10-09 17:00:00'),
        -- inside the old gameweek 7 window only
        ('2026-27', timestamp '2026-10-17 09:00:00')
),

expected (season, gameweek, deadline_time) as (
    values ('2026-27', 7, timestamp '2026-10-17 14:00:00')
),

actual as (
    {{ missed_pre_deadline_windows('gameweeks', 'captures', "timestamp '2026-10-20 00:00:00'") }}
)

(select 'expected, not reported' as problem, * from expected
 except select 'expected, not reported', season, gameweek, deadline_time from actual)
union all
(select 'reported, not expected', season, gameweek, deadline_time from actual
 except select 'reported, not expected', * from expected)
