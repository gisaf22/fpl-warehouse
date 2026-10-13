-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: recomputing freshness from each staged capture's history alone
--          (the captures up to it, with it as the capture clock) gives every
--          gameweek already passed at that capture the freshness the model
--          serves. Once set, freshness does not change as captures accrue.
-- Origin: new in #169 (#163 S10 state rule). In the fixture tree: 2026-27
--         GW3 is set at the 2026-09-06 capture to 2026-08-31 20:36, and GW4
--         at 2026-09-14 to 2026-09-06 19:10. Without the strictly-before
--         bound GW3's value would move to a later capture.
-- Tier: integration
--
-- Recomputed here from stg_gameweek, independently of the model's SQL.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#169 AC9'}) }}

with captures as (

    select distinct season, observed_at
    from {{ ref('stg_gameweek') }}

),

-- Each gameweek's deadline as the captures up to each clock state it: the
-- newest of them by observed_at, run_id breaking a repeat.
deadline_at_clock as (

    select
        clocks.season,
        clocks.observed_at as capture_clock,
        stated.gameweek,
        stated.deadline_time
    from captures as clocks
    inner join {{ ref('stg_gameweek') }} as stated
        on stated.season = clocks.season
        and stated.observed_at <= clocks.observed_at
    qualify row_number() over (
        partition by clocks.season, clocks.observed_at, stated.gameweek
        order by stated.observed_at desc, stated.run_id desc
    ) = 1

),

freshness_at_clock as (

    select
        deadlines.season,
        deadlines.capture_clock,
        deadlines.gameweek,
        deadlines.deadline_time,
        max(earlier.observed_at) as last_capture_before_deadline_at
    from deadline_at_clock as deadlines
    left join captures as earlier
        on earlier.season = deadlines.season
        and earlier.observed_at <= deadlines.capture_clock
        and earlier.observed_at < deadlines.deadline_time
    where deadlines.deadline_time <= deadlines.capture_clock
    group by all

)

select
    recomputed.season,
    recomputed.gameweek,
    recomputed.capture_clock,
    recomputed.last_capture_before_deadline_at as recomputed_last_capture,
    served.last_capture_before_deadline_at     as served_last_capture,
    served.state_age_seconds                   as served_state_age_seconds
from freshness_at_clock as recomputed
inner join {{ ref('dim_gameweek') }} as served
    on served.season = recomputed.season
    and served.gameweek = recomputed.gameweek
where served.last_capture_before_deadline_at
        is distinct from recomputed.last_capture_before_deadline_at
   or served.state_age_seconds is distinct from cast(date_diff(
        'second',
        recomputed.last_capture_before_deadline_at,
        recomputed.deadline_time
    ) as integer)
