-- Layer: fct
-- Tests: as_of (macro) over fct_player_market_snapshot
-- Asserts: as of the 2026-27 gameweek 1 and 2 deadlines, which predate the
--          first capture (2026-08-29), and as of every 2025-26 deadline, which
--          all predate that season's one end-of-season capture, no player gets
--          a market row.
-- Origin: new in #142
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#142 AC3'}) }}

-- Literal seasons on purpose: the claim is about each season's capture
-- history. The "has no ..." checks keep the test from passing on an empty
-- request set, and the last one from passing on a snapshot that is itself
-- empty for the season.

with deadlines as (

    select season, gameweek, deadline_time
    from {{ ref('stg_gameweek') }}
    where (season = '2026-27' and gameweek in (1, 2))
       or season = '2025-26'
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

as_of as (
    {{ as_of('requests', ref('fct_player_market_snapshot'), 'observed_at',
             ['capture_key', 'observed_at', 'now_cost', 'selected_by_percent',
              'transfers_in_event', 'transfers_out_event', 'total_players']) }}
)

select 'market row returned before the first capture' as failure, season, gameweek, fpl_id
from as_of
where capture_key is not null or now_cost is not null

union all

select 'has no 2026-27 gameweek 1 and 2 deadlines', null, null, null
where (select count(*) from deadlines where season = '2026-27') <> 2

union all

select 'has no 2025-26 deadlines', null, null, null
where (select count(*) from deadlines where season = '2025-26') = 0

union all

select 'has no requests for ' || season, season, null, null
from (values ('2026-27'), ('2025-26')) as seasons (season)
where not exists (select 1 from requests where requests.season = seasons.season)
