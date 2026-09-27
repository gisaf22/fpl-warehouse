-- Layer: fct
-- Tests: fct_player_fixture
-- Asserts: every row's team is one of its fixture's two sides, and the row's
--          opponent is the other side.
-- Origin: new in #43
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#43 AC2'}) }}

-- Group membership is required: dim_fixture is access: private.
--
-- The opponent comes from the player's own history row and the sides from the
-- fixture, so this checks the team against a value it was not derived from. A
-- double gameweek (player 233, fixtures 12 and 999) is two rows, each checked
-- against its own fixture. A row whose fixture is missing from dim_fixture
-- fails here too.

select
    fct_player_fixture.season,
    fct_player_fixture.fpl_id,
    fct_player_fixture.fixture_id,
    fct_player_fixture.team_fpl_id,
    fct_player_fixture.opponent_team_fpl_id,
    dim_fixture.team_h_fpl_id,
    dim_fixture.team_a_fpl_id
from {{ ref('fct_player_fixture') }} as fct_player_fixture
left join {{ ref('dim_fixture') }} as dim_fixture
    on  dim_fixture.season = fct_player_fixture.season
    and dim_fixture.fixture_id = fct_player_fixture.fixture_id
where not coalesce(
    (fct_player_fixture.team_fpl_id = dim_fixture.team_h_fpl_id
        and fct_player_fixture.opponent_team_fpl_id = dim_fixture.team_a_fpl_id)
    or (fct_player_fixture.team_fpl_id = dim_fixture.team_a_fpl_id
        and fct_player_fixture.opponent_team_fpl_id = dim_fixture.team_h_fpl_id),
    false
)
