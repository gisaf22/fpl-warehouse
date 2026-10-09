-- Layer: stg
-- Tests: stg_player
-- Asserts: stg_player carries each player status field under its staged name,
--          with its declared type.
-- Origin: new in #125
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#125 AC1'}) }}

-- A field left uncast would come through as whatever DuckDB inferred from the
-- JSON (a struct member type, or JSON for a key that is null in every record),
-- so the type is asserted here, not assumed. Reads the model's metadata only.

-- depends_on: {{ ref('stg_player') }}

with expected (column_name, data_type) as (
    values
        ('status',                       'VARCHAR'),
        ('chance_of_playing_this_round', 'INTEGER'),
        ('chance_of_playing_next_round', 'INTEGER'),
        ('news',                         'VARCHAR'),
        ('news_added',                   'TIMESTAMP'),
        ('can_select',                   'BOOLEAN'),
        ('removed',                      'BOOLEAN'),
        ('team_fpl_id',                  'INTEGER'),
        ('position_id',                  'INTEGER'),
        ('player_code',                  'INTEGER')
),

actual as (
    select column_name, data_type
    from information_schema.columns
    where table_schema = '{{ ref("stg_player").schema }}'
      and table_name = '{{ ref("stg_player").identifier }}'
)

select expected.column_name, expected.data_type as expected_type, actual.data_type as actual_type
from expected
left join actual using (column_name)
where actual.data_type is distinct from expected.data_type
