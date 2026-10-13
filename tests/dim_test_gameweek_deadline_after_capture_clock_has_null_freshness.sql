-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: a gameweek whose deadline is after its season's capture clock (the
--          newest staged bootstrap-static capture's observed_at) has NULL
--          freshness.
-- Origin: new in #169 (#163 S10, S12). In the fixture tree: 2026-27 GW5
--         (deadline 2026-09-18 17:30), after the newest staged capture
--         (2026-09-14 21:12) but before the admitted capture with no payload
--         (2026-10-03 05:20), so a clock read from int_admitted_capture
--         would count it as passed.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#169 AC7'}) }}

with capture_clock as (

    select season, max(observed_at) as capture_clock
    from {{ ref('stg_gameweek') }}
    group by season

)

select gameweeks.*, capture_clock.capture_clock
from {{ ref('dim_gameweek') }} as gameweeks
inner join capture_clock
    on capture_clock.season = gameweeks.season
where gameweeks.deadline_time > capture_clock.capture_clock
  and (gameweeks.last_capture_before_deadline_at is not null
       or gameweeks.state_age_seconds is not null)
