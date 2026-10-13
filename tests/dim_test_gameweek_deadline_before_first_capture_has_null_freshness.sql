-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: a gameweek whose deadline precedes its season's first staged
--          bootstrap-static capture has NULL freshness: it has passed, but
--          no capture was taken before it.
-- Origin: new in #169 (#163 S13). In the fixture tree: 2026-27 GW1
--         (2026-08-21 17:30) and GW2 (2026-08-28 17:30), before the first
--         2026-27 capture at 2026-08-29 19:11.
-- Tier: integration
--
-- "Reads as passed" has no column of its own (S13): such a deadline is below
-- the season's first capture, so it is below the capture clock too.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#169 AC4'}) }}

with first_capture as (

    select season, min(observed_at) as first_observed_at
    from {{ ref('stg_gameweek') }}
    group by season

)

select gameweeks.*, first_capture.first_observed_at
from {{ ref('dim_gameweek') }} as gameweeks
inner join first_capture
    on first_capture.season = gameweeks.season
where gameweeks.deadline_time < first_capture.first_observed_at
  and (gameweeks.last_capture_before_deadline_at is not null
       or gameweeks.state_age_seconds is not null)
