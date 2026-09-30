-- Layer: fct
-- Tests: fct_player_fixture, fct_player_gameweek, dim_fixture, dim_team, dim_player
-- Asserts: the three served tables that carried `round` carry `gameweek
--          INTEGER` at the same position instead, and no served table has a
--          `round` column.
-- Origin: new in #89
-- Tier: integration
{{ config(tags=['integration'], meta={'covers': '#89 AC2'}) }}

-- Reads the built tables' real columns, not schema.yml, so it checks what a
-- consumer of the published parquet would see. Positions are those `round`
-- held before the rename (fixture build of main, 2026-09-30): a rename keeps
-- a column's place, so a consumer reading by position is unaffected.
--
-- dim_team and dim_player must stay as they are. Their enforced contracts
-- already fail the build on any column change; here they are held to having
-- neither name, so a stray rename into them fails too.

with served_columns as (

    select table_name, column_name, data_type, ordinal_position
    from information_schema.columns
    where table_name in (
        '{{ ref("fct_player_fixture").identifier }}',
        '{{ ref("fct_player_gameweek").identifier }}',
        '{{ ref("dim_fixture").identifier }}',
        '{{ ref("dim_team").identifier }}',
        '{{ ref("dim_player").identifier }}'
    )
      and column_name in ('round', 'gameweek')

),

expected (table_name, column_name, data_type, ordinal_position) as (

    values
        ('fct_player_fixture',  'gameweek', 'INTEGER', 7),
        ('fct_player_gameweek', 'gameweek', 'INTEGER', 3),
        ('dim_fixture',         'gameweek', 'INTEGER', 3)

)

select
    coalesce(expected.table_name, served_columns.table_name) as table_name,
    coalesce(expected.column_name, served_columns.column_name) as column_name,
    case
        when served_columns.table_name is null
            then 'expected gameweek INTEGER at position '
                || expected.ordinal_position || ', not found'
        else 'unexpected ' || served_columns.column_name || ' '
            || served_columns.data_type || ' at position '
            || served_columns.ordinal_position
    end as failure
from expected
full outer join served_columns
    on  served_columns.table_name = expected.table_name
    and served_columns.column_name = expected.column_name
    and served_columns.data_type = expected.data_type
    and served_columns.ordinal_position = expected.ordinal_position
where expected.table_name is null
   or served_columns.table_name is null
