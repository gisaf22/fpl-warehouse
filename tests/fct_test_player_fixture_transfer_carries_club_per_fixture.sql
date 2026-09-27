-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: player 166, who changed clubs between rounds 1 and 2 of 2026-27,
--          carries the old club on the fixture before the move and the new
--          club on every fixture after it.
-- Origin: new in #43
-- Tier: integration
{{ config(tags=['integration'], meta={'covers': '#43 AC1'}) }}

-- Expected clubs are the fixture tree's, read from each fixture's home and
-- away sides and the player's opponent (tests/fixtures/build_fixtures.py, 166):
-- round 1's fixture 10 was played for club 6, and rounds 2-4 (fixtures 20, 25,
-- 31) for club 2. The retracted fixture 16 is not in the fact.
--
-- Resolving the team once per player, at build time, is known bug 1 in
-- CLAUDE.md: it would give fixture 10 the new club. A missing row fails too,
-- so the test cannot pass by matching nothing.
--
-- Fixtures target only: the values are the tree's, like the other tree-shape
-- assertions.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with expected (fixture_id, team_fpl_id) as (

    values (10, 6), (20, 2), (25, 2), (31, 2)

)

select
    expected.fixture_id,
    expected.team_fpl_id              as expected_team_fpl_id,
    fct_player_fixture.team_fpl_id    as actual_team_fpl_id
from expected
left join {{ ref('fct_player_fixture') }} as fct_player_fixture
    on  fct_player_fixture.season = '{{ var("season") }}'
    and fct_player_fixture.fpl_id = 166
    and fct_player_fixture.fixture_id = expected.fixture_id
where fct_player_fixture.team_fpl_id is distinct from expected.team_fpl_id

{% endif %}
