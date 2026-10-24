-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: a 2026-27 gameweek in no event-status capture serves ranked_count
--          only when its deadline is before 2026-08-29, when capture history
--          began. Then the served value equals the season's first staged
--          bootstrap-static capture's, and that capture reports the gameweek
--          finished and data_checked. This checks where the fallback applies
--          and what it serves, not that the value is FPL's ratified count:
--          nothing in the capture history can show that.
-- Origin: new in #219 (D2). In the fixture GW1 is finished and data_checked in
--         the 08-29 capture, with 8,903,411. GW5 is also in no event-status
--         capture, but its deadline is after the cutoff and it is unfinished:
--         a fallback that does not check both serves its 0.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC6'}) }}

with without_status as (

    select dim.season, dim.gameweek, dim.deadline_time, dim.ranked_count
    from {{ ref('dim_gameweek') }} as dim
    left join {{ ref('int_gameweek_status') }} as status
        on status.season = dim.season
       and status.gameweek = dim.gameweek
    where dim.season = '2026-27'
      and status.gameweek is null

),

first_capture as (

    select season, gameweek, ranked_count, finished, data_checked
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at, run_id
    ) = 1

),

checked as (

    select
        without_status.*,
        without_status.deadline_time < timestamp '2026-08-29 00:00:00' as before_history,
        first_capture.ranked_count as first_capture_ranked_count,
        first_capture.finished,
        first_capture.data_checked
    from without_status
    left join first_capture using (season, gameweek)

)

select 'before capture history: not the first capture''s finished, data_checked value' as reason,
       season, gameweek, ranked_count, first_capture_ranked_count
from checked
where before_history
  and (ranked_count is distinct from first_capture_ranked_count
       or not coalesce(finished and data_checked, false))

union all

select 'after the cutoff with no event-status: served', season, gameweek, ranked_count, first_capture_ranked_count
from checked
where not before_history
  and ranked_count is not null

{% if target.name == 'fixtures' %}
union all
select 'fixture lacks a gameweek on each side of the cutoff with no event-status', null, null, null, null
where not exists (select 1 from checked where before_history)
   or not exists (select 1 from checked where not before_history)
{% endif %}
