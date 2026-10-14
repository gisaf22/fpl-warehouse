-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: a gameweek with two or more fixtures carries, in each of its 27
--          measures, the sum of its fixture rows in fct_player_fixture; and at
--          least one such gameweek exists.
-- Origin: new in #186 (#133 S17), which NULLs the measures where nothing was
--         observed and must leave double gameweeks as they were.
-- Tier: integration
{{ config(tags=['integration'], meta={'covers': '#186 AC2'}) }}

-- The expected values are recomputed here from the fixture rows, as the model
-- computed them before #186: integers summed, ICT summed then rounded to one
-- place. fct_test_player_gameweek_single_fixture_matches_fact covers
-- fixture_count = 1.
--
-- The second branch fails a build with no double gameweek at all, so this test
-- cannot pass by having nothing to check. The fixture tree holds three:
-- 2025-26 fpl_id 4 gameweek 26 and 166 gameweek 33, 2026-27 fpl_id 233
-- gameweek 2.

with expected as (

    select
        season,
        fpl_id,
        gameweek,
        sum(minutes)                         as minutes,
        sum(starts)                          as starts,
        sum(total_points)                    as total_points,
        sum(bonus)                           as bonus,
        sum(bps)                             as bps,
        sum(goals_scored)                    as goals_scored,
        sum(assists)                         as assists,
        sum(clean_sheets)                    as clean_sheets,
        sum(goals_conceded)                  as goals_conceded,
        sum(own_goals)                       as own_goals,
        sum(penalties_saved)                 as penalties_saved,
        sum(penalties_missed)                as penalties_missed,
        sum(yellow_cards)                    as yellow_cards,
        sum(red_cards)                       as red_cards,
        sum(saves)                           as saves,
        sum(clearances_blocks_interceptions) as clearances_blocks_interceptions,
        sum(recoveries)                      as recoveries,
        sum(tackles)                         as tackles,
        sum(defensive_contribution)          as defensive_contribution,
        sum(expected_goals)                  as expected_goals,
        sum(expected_assists)                as expected_assists,
        sum(expected_goal_involvements)      as expected_goal_involvements,
        sum(expected_goals_conceded)         as expected_goals_conceded,
        round(sum(influence), 1)             as influence,
        round(sum(creativity), 1)            as creativity,
        round(sum(threat), 1)                as threat,
        round(sum(ict_index), 1)             as ict_index
    from {{ ref('fct_player_fixture') }}
    group by season, fpl_id, gameweek
    having count(*) >= 2

),

doubles as (

    select *
    from {{ ref('fct_player_gameweek') }}
    where fixture_count >= 2

)

select
    doubles.season,
    doubles.fpl_id,
    doubles.gameweek,
    'measure differs from the sum of its fixtures' as failure
from doubles
left join expected using (season, fpl_id, gameweek)
where expected.fpl_id is null
   or doubles.minutes                         is distinct from expected.minutes
   or doubles.starts                          is distinct from expected.starts
   or doubles.total_points                    is distinct from expected.total_points
   or doubles.bonus                           is distinct from expected.bonus
   or doubles.bps                             is distinct from expected.bps
   or doubles.goals_scored                    is distinct from expected.goals_scored
   or doubles.assists                         is distinct from expected.assists
   or doubles.clean_sheets                    is distinct from expected.clean_sheets
   or doubles.goals_conceded                  is distinct from expected.goals_conceded
   or doubles.own_goals                       is distinct from expected.own_goals
   or doubles.penalties_saved                 is distinct from expected.penalties_saved
   or doubles.penalties_missed                is distinct from expected.penalties_missed
   or doubles.yellow_cards                    is distinct from expected.yellow_cards
   or doubles.red_cards                       is distinct from expected.red_cards
   or doubles.saves                           is distinct from expected.saves
   or doubles.clearances_blocks_interceptions is distinct from expected.clearances_blocks_interceptions
   or doubles.recoveries                      is distinct from expected.recoveries
   or doubles.tackles                         is distinct from expected.tackles
   or doubles.defensive_contribution          is distinct from expected.defensive_contribution
   or abs(doubles.expected_goals             - expected.expected_goals)             > 0.0001
   or abs(doubles.expected_assists           - expected.expected_assists)           > 0.0001
   or abs(doubles.expected_goal_involvements - expected.expected_goal_involvements) > 0.0001
   or abs(doubles.expected_goals_conceded    - expected.expected_goals_conceded)    > 0.0001
   or abs(doubles.influence                  - expected.influence)                  > 0.0001
   or abs(doubles.creativity                 - expected.creativity)                 > 0.0001
   or abs(doubles.threat                     - expected.threat)                     > 0.0001
   or abs(doubles.ict_index                  - expected.ict_index)                  > 0.0001
   or doubles.expected_goals             is null
   or doubles.expected_assists           is null
   or doubles.expected_goal_involvements is null
   or doubles.expected_goals_conceded    is null
   or doubles.influence                  is null
   or doubles.creativity                 is null
   or doubles.threat                     is null
   or doubles.ict_index                  is null

union all

select
    null,
    null,
    null,
    'no gameweek with two or more fixtures to check'
where not exists (select 1 from doubles)
