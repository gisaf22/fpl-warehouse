-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: ranked_count is the last column, so every existing column keeps its
--          position and the publish guard reads the change as additive.
-- Origin: new in #219 (D2). The enforced contract checks names and types, not
--         where a new column sits.
-- Tier: unit
{{ config(group='warehouse_internal', tags=['unit'], meta={'covers': '#219 AC3'}) }}

with columns as (
    select column_name, row_number() over () as position
    from (describe {{ ref('dim_gameweek') }})
)

select arg_max(column_name, position) as last_column
from columns
having arg_max(column_name, position) is distinct from 'ranked_count'
