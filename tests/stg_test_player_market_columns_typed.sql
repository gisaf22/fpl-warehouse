-- Layer: stg
-- Tests: stg_player
-- Asserts: stg_player carries each market field and total_players under its
--          staged name, with its declared type.
-- Origin: new in #140, modelled on tests/stg_test_player_status_columns_typed.sql
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#140 AC1'}) }}

-- A field left uncast would come through as whatever DuckDB inferred from the
-- JSON (BIGINT for the numbers, VARCHAR for selected_by_percent), so the type
-- is asserted here, not assumed. DECIMAL(4,1) holds every published ownership
-- figure exactly: one decimal place, 0.0 to 100.0 (#140 D2). Reads the model's
-- metadata only.

-- depends_on: {{ ref('stg_player') }}

with expected (column_name, data_type) as (
    values
        ('now_cost',            'INTEGER'),
        ('selected_by_percent', 'DECIMAL(4,1)'),
        ('transfers_in_event',  'INTEGER'),
        ('transfers_out_event', 'INTEGER'),
        ('total_players',       'INTEGER')
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
