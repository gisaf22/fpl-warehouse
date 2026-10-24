-- Layer: fct
-- Tests: fct_player_gameweek
-- Asserts: fixture_count_at_deadline is the last column and an INTEGER, so
--          every existing column keeps its position and the publish guard
--          reads the change as additive.
-- Origin: new in #221 (D1). The enforced contract checks names and types, not
--         where a new column sits.
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#221 AC1'}) }}

with columns as (
    select column_name, column_type, row_number() over () as position
    from (describe {{ ref('fct_player_gameweek') }})
)

select column_name as last_column, column_type
from columns
where position = (select max(position) from columns)
  and (column_name is distinct from 'fixture_count_at_deadline'
       or column_type is distinct from 'INTEGER')
