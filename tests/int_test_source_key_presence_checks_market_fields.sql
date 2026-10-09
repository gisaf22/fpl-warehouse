-- Layer: int
-- Tests: int_source_key_presence
-- Asserts: every bootstrap-static field the player market snapshot needs —
--          four element fields and the root total_players — is declared on
--          the source and checked for presence in the latest admitted live
--          run, so both consumed_keys_present tests on bootstrap_static
--          cover it.
-- Origin: new in #139, modelled on
--         tests/int_test_source_key_presence_checks_player_status_fields.sql
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#139 AC1'}) }}

-- int_source_key_presence holds one row per declared column, read by both the
-- removed (error) and partial (warn) tests, so a row with records read is the
-- proof a field is covered. A field that is undeclared has no row.

with expected (column_name) as (
    values
        ('elements.now_cost'),
        ('elements.selected_by_percent'),
        ('elements.transfers_in_event'),
        ('elements.transfers_out_event'),
        ('total_players')
)

select expected.column_name, 'not checked for presence' as problem
from expected
left join {{ ref('int_source_key_presence') }} as presence
    on presence.source_name = 'bootstrap_static'
   and presence.column_name = expected.column_name
   and presence.records > 0
where presence.column_name is null
