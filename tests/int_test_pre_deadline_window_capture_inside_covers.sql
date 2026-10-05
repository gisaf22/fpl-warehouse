-- Layer: int
-- Tests: missed_pre_deadline_windows (macro)
-- Asserts: a passed in-scope deadline with an admitted capture inside
--          [deadline - 125m, deadline), including exactly at the lower edge,
--          is not reported missed.
-- Origin: new in #111
-- Tier: unit
{{ config(tags=['unit'], meta={'covers': '#111 AC1'}) }}

with gameweeks (season, gameweek, deadline_time, observed_at, run_id) as (
    values
        ('2026-27', 6, timestamp '2026-10-10 10:00:00', timestamp '2026-10-10 12:00:00', 'r1'),
        ('2026-27', 7, timestamp '2026-10-17 10:00:00', timestamp '2026-10-10 12:00:00', 'r1')
),

captures (season, observed_at) as (
    values
        -- gameweek 6: exactly deadline - 125m
        ('2026-27', timestamp '2026-10-10 07:55:00'),
        -- gameweek 7: one second before the deadline
        ('2026-27', timestamp '2026-10-17 09:59:59')
)

{{ missed_pre_deadline_windows('gameweeks', 'captures', "timestamp '2026-10-20 00:00:00'") }}
