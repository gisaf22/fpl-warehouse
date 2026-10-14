-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: the built fct_player_gameweek has no deadline_time column;
--          dim_gameweek is its only served home.
-- Origin: new in #186 (#133 S9, S19)
-- Tier: integration
{{ config(tags=['integration'], meta={'covers': '#186 AC3'}) }}

-- Reads the built table's real columns, not schema.yml, so it checks what a
-- consumer of the published parquet would see.

select table_name, column_name, data_type, ordinal_position
from information_schema.columns
where table_name = '{{ ref("fct_player_gameweek").identifier }}'
  and column_name = 'deadline_time'
