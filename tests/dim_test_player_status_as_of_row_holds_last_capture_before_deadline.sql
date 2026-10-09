-- Layer: dim
-- Tests: player_status_as_of (macro) over dim_player_status_history
-- Asserts: for every player and every deadline of their season, the as-of row
--          is the one whose interval contains the player's last capture
--          before the deadline, opened before it; a player with no capture
--          before the deadline gets no state.
-- Origin: new in #128 (the point-in-time data test)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#128 AC1'}) }}

-- The oracle is read from stg_player, independently of the history model:
-- the player's latest capture with observed_at strictly before the deadline.
-- Each deadline is the one in the latest capture, as FPL can move it (#80).
--
-- The last check keeps "never a later one" from passing vacuously: some
-- player's state must change across some deadline, so a lookup that took the
-- first capture after a deadline would return a different status. In the
-- fixture tree that is player 427 across gameweek 3 (build_fixtures.py,
-- SYNTHETIC_STATUS).

with deadlines as (

    select season, gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    qualify row_number() over (
        partition by season, gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

requests as (

    select players.season, players.fpl_id, deadlines.gameweek, deadlines.deadline_time as as_of_time
    from (select distinct season, fpl_id from {{ ref('stg_player') }}) as players
    inner join deadlines on deadlines.season = players.season

),

captures_around as (

    select
        requests.season,
        requests.fpl_id,
        requests.as_of_time,
        max(captures.observed_at) filter (where captures.observed_at <  requests.as_of_time) as last_before,
        arg_max(captures.status, captures.observed_at)
            filter (where captures.observed_at <  requests.as_of_time)                      as status_before,
        arg_min(captures.status, captures.observed_at)
            filter (where captures.observed_at >= requests.as_of_time)                      as status_after
    from requests
    inner join {{ ref('stg_player') }} as captures
        on  captures.season = requests.season
        and captures.fpl_id = requests.fpl_id
    group by all

),

as_of as (
    {{ player_status_as_of('requests') }}
),

checked as (

    select
        as_of.season, as_of.fpl_id, as_of.gameweek, as_of.as_of_time,
        as_of.valid_from, as_of.valid_to, as_of.status,
        captures_around.last_before
    from as_of
    inner join captures_around
        on  captures_around.season     = as_of.season
        and captures_around.fpl_id     = as_of.fpl_id
        and captures_around.as_of_time = as_of.as_of_time

)

select season, fpl_id, gameweek, as_of_time, valid_from, valid_to, status, last_before,
    case
        when valid_from >= as_of_time                      then 'row opened at or after the deadline'
        when last_before is null                           then 'state returned with no capture before the deadline'
        when valid_from is null                            then 'no state although a capture precedes the deadline'
        else                                                    'row does not contain the last capture before the deadline'
    end as failure
from checked
where valid_from >= as_of_time
   or (last_before is null and (valid_from is not null or status is not null))
   or (last_before is not null and valid_from is null)
   or (last_before is not null and not (
           valid_from <= last_before and (valid_to is null or last_before < valid_to)
       ))

union all

select null, null, null, null, null, null, null, null,
    'no player changes state across a deadline'
where not exists (
    select 1 from captures_around
    where status_before is not null
      and status_after  is not null
      and status_before <> status_after
)
