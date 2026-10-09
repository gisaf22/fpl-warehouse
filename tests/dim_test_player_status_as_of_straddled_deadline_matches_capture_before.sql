-- Layer: dim
-- Tests: player_status_as_of (macro) over dim_player_status_history
-- Asserts: player 427, whose captures read a -> d -> a across the 2026-27
--          gameweek 3 deadline, gets the tracked fields of the capture just
--          before each of the gameweek 3 and 4 deadlines: d, then a.
-- Origin: new in #128 (AC4 on the fixture, decided 2026-10-09)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#128 AC4'}) }}

-- The d is synthetic, set in the 2026-08-31 capture only
-- (build_fixtures.py, SYNTHETIC_STATUS); the 2026-09-06 capture after the
-- gameweek 3 deadline is a again. The pinned statuses keep the comparison
-- from passing when both sides are wrong the same way, and a missing result
-- row fails too.
--
-- Fixtures target only: the values are the tree's. The real deadline check
-- is GW6's post-merge query on #128.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with expected_status (gameweek, status) as (
    values (3, 'd'), (4, 'a')
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

    select requests.gameweek, captures.*
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
    {{ player_status_as_of('requests') }}
)

select expected_status.gameweek, expected_status.status as expected_status,
    capture_before.status as capture_status, as_of.status as as_of_status
from expected_status
left join capture_before on capture_before.gameweek = expected_status.gameweek
left join as_of          on as_of.gameweek          = expected_status.gameweek
where capture_before.status is distinct from expected_status.status
   or as_of.status is distinct from capture_before.status
   or as_of.chance_of_playing_this_round is distinct from capture_before.chance_of_playing_this_round
   or as_of.chance_of_playing_next_round is distinct from capture_before.chance_of_playing_next_round
   or as_of.news         is distinct from capture_before.news
   or as_of.can_select   is distinct from capture_before.can_select
   or as_of.removed      is distinct from capture_before.removed
   or as_of.team_fpl_id  is distinct from capture_before.team_fpl_id
   or as_of.position_id  is distinct from capture_before.position_id

{% endif %}
