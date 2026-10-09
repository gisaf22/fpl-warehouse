-- Layer: dim
-- Tests: player_status_as_of (macro) over dim_player_status_history
-- Asserts: as of the 2026-27 gameweek 1 and 2 deadlines, which predate the
--          first capture (2026-08-29), no player gets a state.
-- Origin: new in #128
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#128 AC2'}) }}

-- Literal season on purpose: the claim is about 2026-27's capture history,
-- which began after its gameweek 2 deadline. The two "has no ..." checks keep
-- the test from passing on an empty request set.

with deadlines as (

    select gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    where season = '2026-27' and gameweek in (1, 2)
    qualify row_number() over (
        partition by gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

requests as (

    select players.season, players.fpl_id, deadlines.gameweek, deadlines.deadline_time as as_of_time
    from (
        select distinct season, fpl_id from {{ ref('stg_player') }} where season = '2026-27'
    ) as players
    cross join deadlines

),

as_of as (
    {{ player_status_as_of('requests') }}
)

select 'state returned before the first capture' as failure, gameweek, fpl_id
from as_of
where valid_from is not null or status is not null

union all

select 'has no 2026-27 gameweek 1 and 2 deadlines', null, null
where (select count(*) from deadlines) <> 2

union all

select 'has no 2026-27 players', null, null
where not exists (select 1 from requests)
