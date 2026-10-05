-- Layer: int
-- Tests: missed_pre_deadline_windows (macro)
-- Asserts: a deadline not before the as-of instant, or before the 2026-09-24
--          coverage start, is never reported, even with no capture at all.
-- Origin: new in #111
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#111 AC4'}) }}

with gameweeks (season, gameweek, deadline_time, observed_at, run_id) as (
    values
        -- before coverage began
        ('2026-27', 5, timestamp '2026-09-18 17:30:00', timestamp '2026-10-05 07:00:00', 'r1'),
        -- exactly at the as-of instant: not yet passed
        ('2026-27', 6, timestamp '2026-10-10 10:00:00', timestamp '2026-10-05 07:00:00', 'r1'),
        -- in the future
        ('2026-27', 7, timestamp '2026-10-17 10:00:00', timestamp '2026-10-05 07:00:00', 'r1'),
        -- a closed season's deadline
        ('2025-26', 38, timestamp '2026-05-24 13:30:00', timestamp '2026-05-26 03:46:26', 'h1')
),

captures (season, observed_at) as (
    select * from (values ('2026-27', timestamp '2000-01-01 00:00:00')) where false
)

{{ missed_pre_deadline_windows('gameweeks', 'captures', "timestamp '2026-10-10 10:00:00'") }}
