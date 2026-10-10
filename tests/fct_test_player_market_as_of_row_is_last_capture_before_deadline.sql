-- Layer: fct
-- Tests: as_of (macro) over fct_player_market_snapshot
-- Asserts: for every player and every deadline of their season, the as-of
--          market row is the player's last capture strictly before the
--          deadline; a player with no capture before it gets no row.
-- Origin: new in #142 (the point-in-time data test)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#142 AC2'}) }}

-- The oracle is read from stg_player, independently of the snapshot: the
-- player's latest capture with observed_at strictly before the deadline. Each
-- deadline is the one in the latest capture, as FPL can move it (#80).
--
-- The last check keeps "never a later one" from passing vacuously: some
-- request must have captures both before and after its deadline, so a lookup
-- that took the first capture after it would return a different capture.

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
        arg_max(captures.capture_key, captures.observed_at)
            filter (where captures.observed_at <  requests.as_of_time) as capture_before,
        count(*) filter (where captures.observed_at >= requests.as_of_time) as captures_after
    from requests
    inner join {{ ref('stg_player') }} as captures
        on  captures.season = requests.season
        and captures.fpl_id = requests.fpl_id
    group by all

),

as_of as (
    {{ as_of('requests', ref('fct_player_market_snapshot'), 'observed_at',
             ['capture_key', 'observed_at', 'now_cost', 'selected_by_percent',
              'transfers_in_event', 'transfers_out_event']) }}
),

checked as (

    select
        as_of.season, as_of.fpl_id, as_of.gameweek, as_of.as_of_time,
        as_of.capture_key, as_of.observed_at,
        captures_around.capture_before
    from as_of
    inner join captures_around
        on  captures_around.season     = as_of.season
        and captures_around.fpl_id     = as_of.fpl_id
        and captures_around.as_of_time = as_of.as_of_time

)

select season, fpl_id, gameweek, as_of_time, capture_key, observed_at, capture_before,
    case
        when observed_at >= as_of_time  then 'capture at or after the deadline'
        when capture_before is null     then 'row returned with no capture before the deadline'
        when capture_key is null        then 'no row although a capture precedes the deadline'
        else                                 'not the last capture before the deadline'
    end as failure
from checked
where observed_at >= as_of_time
   or capture_key is distinct from capture_before

union all

select null, null, null, null, null, null, null,
    'no request has captures on both sides of its deadline'
where not exists (
    select 1 from captures_around
    where capture_before is not null and captures_after > 0
)
