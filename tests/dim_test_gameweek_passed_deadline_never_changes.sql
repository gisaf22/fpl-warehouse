-- Layer: dim
-- Tests: stg_gameweek (dim_gameweek's input)
-- Asserts: no staged capture states a different deadline_time for a gameweek
--          whose deadline had already passed by an earlier staged capture of
--          its season. A deadline moved before it passed is allowed.
-- Origin: new in #169 (#163 S14a). It keeps dim_gameweek's freshness fixed
--         once set (S10): the model holds one deadline per gameweek, so the
--         change is visible only in its input. If it fires, deadline history
--         (S2's later slice) is the fix. In the fixture tree 2026-27 GW17-20
--         move before their deadlines and must not fire it.
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#169 AC8'}) }}

-- "Passed by an earlier capture" uses that season's newest staged capture
-- before the changing one: the capture clock as it stood then.
with captures as (

    select distinct season, observed_at
    from {{ ref('stg_gameweek') }}

),

stated as (

    select
        season,
        gameweek,
        capture_key,
        observed_at,
        deadline_time,
        lag(deadline_time) over (
            partition by season, gameweek
            order by observed_at, run_id
        ) as previous_deadline_time
    from {{ ref('stg_gameweek') }}

)

select
    stated.season,
    stated.gameweek,
    stated.previous_deadline_time,
    stated.deadline_time,
    stated.capture_key,
    stated.observed_at,
    max(captures.observed_at) as clock_before_this_capture
from stated
inner join captures
    on captures.season = stated.season
    and captures.observed_at < stated.observed_at
where stated.previous_deadline_time is not null
  and stated.deadline_time is distinct from stated.previous_deadline_time
group by all
having stated.previous_deadline_time <= max(captures.observed_at)
