-- Layer: stg
-- Tests: stg_player_fixture against source fpl_raw.fixtures
-- Asserts: both fixtures of player 233's synthetic round-2 double gameweek
--          resolve to a fixture in round 2 of the same season.
-- Origin: new in #36 — keeps the double-gameweek case exercised once team per
--         fixture (#43) resolves a player's team through the fixture row. A
--         history fixture with no fixture row would have no team.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#36 AC2'}) }}

-- Group membership is required: this test ref()s stg_player_fixture, which is
-- access: private to warehouse_internal.
--
-- Fixtures target only — the double is synthetic (SYNTHETIC_DGW in
-- tests/fixtures/build_fixtures.py) and exists nowhere in the live bucket.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with double_gameweek as (

    select distinct season, fixture_id, round
    from {{ ref('stg_player_fixture') }}
    where season = '{{ var("season") }}'
      and fpl_id = 233
      and round = 2

),

fixtures as (

    select distinct
        {{ season_from_filename() }} as season,
        cast(id as integer)          as fixture_id,
        cast(event as integer)       as round
    from {{ source('fpl_raw', 'fixtures') }}

)

-- Precondition first: without two round-2 fixtures there is no double to
-- check, and the lookup below would pass on nothing.
select
    'player 233 has ' || count(*) || ' round-2 fixtures, expected 2'
        as failure,
    null::integer as fixture_id
from double_gameweek
having count(*) != 2

union all

select
    'history fixture has no round-2 fixture row' as failure,
    double_gameweek.fixture_id
from double_gameweek
left join fixtures using (season, fixture_id, round)
where fixtures.fixture_id is null

{% endif %}
