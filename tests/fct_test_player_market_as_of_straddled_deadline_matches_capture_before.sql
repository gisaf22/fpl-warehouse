-- Layer: fct
-- Tests: as_of (macro) over fct_player_market_snapshot
-- Asserts: player 427, whose price reads 80, 80, 79, 79 across the four live
--          captures, gets the price of the capture just before each of the
--          2026-27 gameweek 3 and 4 deadlines: 80, then 79.
-- Origin: new in #142 (AC4 on the fixture, checked 2026-10-09)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#142 AC4'}) }}

-- The change is real, not synthetic: it falls between the 2026-08-31 and
-- 2026-09-06 captures, which straddle the gameweek 3 deadline (2026-09-04
-- 17:30). The pinned prices keep the comparison from passing when both sides
-- are wrong the same way, and a missing result row fails too.
--
-- Fixtures target only: the values are the tree's.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with expected_price (gameweek, now_cost) as (
    values (3, 80), (4, 79)
),

requests as (

    select season, 427 as fpl_id, gameweek, deadline_time as as_of_time
    from {{ ref('stg_gameweek') }}
    where season = '2026-27' and gameweek in (3, 4)
    qualify row_number() over (
        partition by gameweek
        order by observed_at desc, run_id desc
    ) = 1

),

capture_before as (

    select requests.gameweek, captures.capture_key, captures.now_cost
    from requests
    inner join {{ ref('stg_player') }} as captures
        on  captures.season = requests.season
        and captures.fpl_id = requests.fpl_id
        and captures.observed_at < requests.as_of_time
    qualify row_number() over (
        partition by requests.gameweek
        order by captures.observed_at desc, captures.run_id desc
    ) = 1

),

as_of as (
    {{ as_of('requests', ref('fct_player_market_snapshot'), 'observed_at',
             ['capture_key', 'now_cost']) }}
)

select expected_price.gameweek, expected_price.now_cost as expected_now_cost,
    capture_before.now_cost as capture_now_cost, as_of.now_cost as as_of_now_cost,
    capture_before.capture_key as capture_before_key, as_of.capture_key as as_of_capture_key
from expected_price
left join capture_before on capture_before.gameweek = expected_price.gameweek
left join as_of          on as_of.gameweek          = expected_price.gameweek
where capture_before.now_cost is distinct from expected_price.now_cost
   or as_of.now_cost          is distinct from capture_before.now_cost
   or as_of.capture_key       is distinct from capture_before.capture_key

{% endif %}
