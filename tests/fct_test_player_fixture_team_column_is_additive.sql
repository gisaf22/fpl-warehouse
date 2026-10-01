-- Layer: fct
-- Tests: fct_player_fixture, fct_player_gameweek
-- Asserts: fct_player_fixture's columns are its staging columns, then
--          is_ratified, then team_fpl_id, each with its existing name, type
--          and position; and fct_player_gameweek has no team column.
-- Origin: new in #43
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#43 AC5'}) }}

-- Reads each table's column list, not its rows. Before #43 the fact was
-- exactly stg_player_fixture's columns plus is_ratified (the model's header
-- says so), so any existing column renamed, retyped, dropped or moved fails
-- here, as does team_fpl_id anywhere but last. Team is not on the gameweek
-- fact (decision 5 on #32): a player transferred between the two fixtures of
-- a double has no single team.

{% set fct = ref('fct_player_fixture') %}
{% set stg = ref('stg_player_fixture') %}
{% set gw = ref('fct_player_gameweek') %}

with staging_columns as (

    select ordinal_position, column_name, data_type
    from information_schema.columns
    where table_schema = '{{ stg.schema }}'
      and table_name = '{{ stg.identifier }}'

),

expected as (

    -- Boundary mapping (#89): the fact serves staging's `round` as `gameweek`,
    -- at the same position and type. #88 renames it in staging and removes
    -- this case.
    select
        ordinal_position,
        case when column_name = 'round' then 'gameweek' else column_name end
            as column_name,
        data_type
    from staging_columns

    union all

    select max(ordinal_position) + 1, 'is_ratified', 'BOOLEAN'
    from staging_columns

    union all

    select max(ordinal_position) + 2, 'team_fpl_id', 'INTEGER'
    from staging_columns

),

actual as (

    select ordinal_position, column_name, data_type
    from information_schema.columns
    where table_schema = '{{ fct.schema }}'
      and table_name = '{{ fct.identifier }}'

)

select
    'fct_player_fixture column differs' as failure,
    coalesce(expected.ordinal_position, actual.ordinal_position) as ordinal_position,
    expected.column_name as expected_column,
    expected.data_type   as expected_type,
    actual.column_name   as actual_column,
    actual.data_type     as actual_type
from expected
full outer join actual
    on actual.ordinal_position = expected.ordinal_position
where expected.column_name is distinct from actual.column_name
   or expected.data_type is distinct from actual.data_type

union all

select
    'fct_player_gameweek has a team column' as failure,
    ordinal_position,
    null, null,
    column_name,
    data_type
from information_schema.columns
where table_schema = '{{ gw.schema }}'
  and table_name = '{{ gw.identifier }}'
  and column_name like '%team%'
