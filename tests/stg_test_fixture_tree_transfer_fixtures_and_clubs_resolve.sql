-- Layer: stg
-- Tests: stg_player_fixture against sources fpl_raw.fixtures and
--        fpl_raw.bootstrap_static (teams)
-- Asserts: every history fixture of player 166 — who changed clubs between
--          rounds 1 and 2 — resolves to a fixture in its round, the club the
--          player played for is resolvable on both sides of the move, and both
--          clubs exist as teams in that season.
-- Origin: new in #36 — the transfer is the case team per fixture (#43) exists
--         to get right, so the tree must be able to resolve both clubs.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#36 AC3'}) }}

-- Group membership is required: this test ref()s stg_player_fixture, which is
-- access: private to warehouse_internal.
--
-- The club per fixture is taken from the fixture's own home/away side via the
-- history row's `was_home` — as-of, never from bootstrap's current team.
--
-- Every staged capture is used, not only the latest, so the retracted
-- former-club row (fixture 16) is looked up too. It must resolve as well.
--
-- Fixtures target only, like the rest of the tree-shape assertions.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with history as (

    select distinct season, fixture_id, round, was_home
    from {{ ref('stg_player_fixture') }}
    where season = '{{ var("season") }}'
      and fpl_id = 166

),

fixtures as (

    select distinct
        {{ season_from_filename() }} as season,
        cast(id as integer)          as fixture_id,
        cast(event as integer)       as round,
        cast(team_h as integer)      as team_h,
        cast(team_a as integer)      as team_a
    from {{ source('fpl_raw', 'fixtures') }}

),

teams as (

    select distinct season, cast(t.id as integer) as team_fpl_id
    from (
        select {{ season_from_filename() }} as season, unnest(teams) as t
        from {{ source('fpl_raw', 'bootstrap_static') }}
    )

),

resolved as (

    select
        history.fixture_id,
        fixtures.fixture_id as matched_fixture_id,
        case when history.was_home then fixtures.team_h else fixtures.team_a end
            as club_fpl_id,
        history.season
    from history
    left join fixtures using (season, fixture_id, round)

)

select 'history fixture has no fixture row in its round' as failure, fixture_id
from resolved
where matched_fixture_id is null

union all

select 'club is not a team in this season' as failure, resolved.fixture_id
from resolved
left join teams
    on teams.season = resolved.season
   and teams.team_fpl_id = resolved.club_fpl_id
where resolved.matched_fixture_id is not null
  and teams.team_fpl_id is null

union all

-- Both sides of the move: fewer than two distinct clubs means the transfer is
-- not visible through the fixture data, and #43 would have nothing to prove.
select
    'player 166 resolves to ' || count(distinct club_fpl_id)
        || ' club(s), expected at least 2' as failure,
    null::integer as fixture_id
from resolved
having count(distinct club_fpl_id) < 2

{% endif %}
