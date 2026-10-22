-- Layer: int
-- Tests: int_manager_gameweek_status
-- Asserts: no panel manager is missing_after_join in any marked gameweek: a
--          manager who had joined has an admitted picks capture for every
--          gameweek ingest marked settled. Fails the build (D13).
-- Origin: new in #216 (D11, D13)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC3'}) }}

select season, entry_id, gameweek, first_active_gw
from {{ ref('int_manager_gameweek_status') }}
where status = 'missing_after_join'
