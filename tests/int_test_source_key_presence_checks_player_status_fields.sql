-- Layer: int
-- Tests: int_source_key_presence
-- Asserts: every bootstrap-static element field that player status history
--          needs is declared on the source and checked for presence in the
--          latest admitted live run, so both consumed_keys_present tests on
--          bootstrap_static cover it.
-- Origin: new in #124
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#124 AC1'}) }}

-- int_source_key_presence holds one row per declared column, read by both the
-- removed (error) and partial (warn) tests, so a row with records read is the
-- proof a field is covered. A field that is undeclared has no row.

with expected (column_name) as (
    values
        ('elements.status'),
        ('elements.chance_of_playing_this_round'),
        ('elements.chance_of_playing_next_round'),
        ('elements.news'),
        ('elements.news_added'),
        ('elements.can_select'),
        ('elements.removed'),
        ('elements.team'),
        ('elements.element_type'),
        ('elements.code')
)

select expected.column_name, 'not checked for presence' as problem
from expected
left join {{ ref('int_source_key_presence') }} as presence
    on presence.source_name = 'bootstrap_static'
   and presence.column_name = expected.column_name
   and presence.records > 0
where presence.column_name is null
