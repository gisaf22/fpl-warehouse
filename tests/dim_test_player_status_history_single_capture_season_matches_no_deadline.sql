-- Layer: dim
-- Tests: dim_player_status_history
-- Asserts: 2025-26, whose only capture is the end-of-season snapshot of
--          2026-05-26, has history rows, and none of them is in force at any
--          of its gameweek deadlines: an as-of lookup at a 2025-26 deadline
--          matches nothing, by design (no backdating).
-- Origin: new in #126 (example under AC4)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#126 AC4'}) }}

-- A row backdated to the season's start, or to the first deadline, would be
-- in force at a deadline and fail this. The two "has no ..." checks keep the
-- test from passing on an empty season.
--
-- Literal season on purpose: the claim is true only while 2025-26's sole
-- capture postdates its deadlines. If 2025-26 is ever re-ported with captures
-- from during the season, delete this test rather than re-dating it.

with deadlines as (

    select distinct gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    where season = '2025-26'

),

history as (

    select * from {{ ref('dim_player_status_history') }}
    where season = '2025-26'

)

select 'row in force at a deadline' as failure, deadlines.gameweek, history.fpl_id
from deadlines
inner join history
    on  history.valid_from <= deadlines.deadline_time
    and (history.valid_to is null or deadlines.deadline_time < history.valid_to)

union all

select 'has no 2025-26 deadlines', null, null
where not exists (select 1 from deadlines)

union all

select 'has no 2025-26 history rows', null, null
where not exists (select 1 from history)
