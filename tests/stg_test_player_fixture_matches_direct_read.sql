-- Layer: stg
-- Tests: stg_player_fixture
-- Asserts: stg_player_fixture holds exactly the rows, values and types of the
--          direct read of element-summary `history` it replaced, so reading
--          through the declared columns changed nothing.
-- Origin: new in #115
-- Tier: integration
-- Fixture tree only (#115 D4): on a live target it re-reads every raw
-- payload, 689s for element-summary in served_diff run 37723026491.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#115 AC2'},
          enabled=(target.name == 'fixtures')) }}

-- `direct` is stg_player_fixture as it stood before #115: it unnests
-- `history` from the source itself rather than through declared_records. Kept
-- verbatim so the comparison is against the old behaviour, not a second copy
-- of the new. Each column is compared with its type, and `except all` keeps
-- duplicates. See stg_test_gameweek_status_matches_direct_read for the pattern.

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(history) as h
    from {{ source('fpl_raw', 'element_summary') }}

),

direct as (

    select
        admitted.capture_key,
        admitted.season,
        admitted.extraction_date,
        admitted.run_id,
        admitted.extracted_at,
        admitted.observed_at,
        cast(h.element             as integer)   as fpl_id,
        cast(h.fixture             as integer)   as fixture_id,
        cast(h.round               as integer)   as gameweek,
        cast(h.opponent_team       as integer)   as opponent_team_fpl_id,
        cast(h.was_home            as boolean)   as was_home,
        cast(h.kickoff_time        as timestamp) as kickoff_time,
        cast(h.team_h_score        as integer)   as team_h_score,
        cast(h.team_a_score        as integer)   as team_a_score,
        cast(h.minutes             as integer)   as minutes,
        cast(h.starts              as integer)   as starts,
        cast(h.total_points        as integer)   as total_points,
        cast(h.bonus               as integer)   as bonus,
        cast(h.bps                 as integer)   as bps,
        cast(h.goals_scored        as integer)   as goals_scored,
        cast(h.assists             as integer)   as assists,
        cast(h.clean_sheets        as integer)   as clean_sheets,
        cast(h.goals_conceded      as integer)   as goals_conceded,
        cast(h.own_goals           as integer)   as own_goals,
        cast(h.penalties_saved     as integer)   as penalties_saved,
        cast(h.penalties_missed    as integer)   as penalties_missed,
        cast(h.yellow_cards        as integer)   as yellow_cards,
        cast(h.red_cards           as integer)   as red_cards,
        cast(h.saves               as integer)   as saves,
        cast(h.clearances_blocks_interceptions as integer) as clearances_blocks_interceptions,
        cast(h.recoveries          as integer)   as recoveries,
        cast(h.tackles             as integer)   as tackles,
        cast(h.defensive_contribution as integer) as defensive_contribution,
        cast(h.expected_goals              as double) as expected_goals,
        cast(h.expected_assists            as double) as expected_assists,
        cast(h.expected_goal_involvements  as double) as expected_goal_involvements,
        cast(h.expected_goals_conceded     as double) as expected_goals_conceded,
        cast(h.influence           as double)    as influence,
        cast(h.creativity          as double)    as creativity,
        cast(h.threat              as double)    as threat,
        cast(h.ict_index           as double)    as ict_index,
        cast(h.value               as integer)   as value,
        cast(h.selected            as integer)   as selected,
        cast(h.transfers_in        as integer)   as transfers_in,
        cast(h.transfers_out       as integer)   as transfers_out,
        cast(h.transfers_balance   as integer)   as transfers_balance,
        cast(h.modified            as boolean)   as modified
    from raw
    inner join {{ ref('int_admitted_capture') }} as admitted
        on admitted.capture_key = raw.capture_key

),

{% set columns = ['capture_key', 'season', 'extraction_date', 'run_id', 'extracted_at',
                  'observed_at', 'fpl_id', 'fixture_id', 'gameweek',
                  'opponent_team_fpl_id', 'was_home', 'kickoff_time',
                  'team_h_score', 'team_a_score', 'minutes', 'starts',
                  'total_points', 'bonus', 'bps', 'goals_scored', 'assists',
                  'clean_sheets', 'goals_conceded', 'own_goals',
                  'penalties_saved', 'penalties_missed', 'yellow_cards',
                  'red_cards', 'saves', 'clearances_blocks_interceptions',
                  'recoveries', 'tackles', 'defensive_contribution',
                  'expected_goals', 'expected_assists',
                  'expected_goal_involvements', 'expected_goals_conceded',
                  'influence', 'creativity', 'threat', 'ict_index', 'value',
                  'selected', 'transfers_in', 'transfers_out',
                  'transfers_balance', 'modified'] %}

typed_direct as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from direct
),

typed_staged as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from {{ ref('stg_player_fixture') }}
)

select 'only in direct read' as side, * from (select * from typed_direct except all select * from typed_staged)
union all
select 'only in staging' as side, * from (select * from typed_staged except all select * from typed_direct)
