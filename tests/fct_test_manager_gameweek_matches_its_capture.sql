-- Layer: fct
-- Tests: fct_manager_gameweek
-- Asserts: each served manager-gameweek equals its winning capture: active
--          chip, transfers, transfer cost and the automatic substitutions; the
--          fixture holds a week with a transfer cost and one with automatic
--          subs, so the check is not vacuous.
-- Origin: new in #216 (D9)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC10'}) }}

with expected as (

    select
        grid.season,
        grid.entry_id,
        grid.gameweek,
        captures.active_chip,
        captures.event_transfers,
        captures.event_transfers_cost,
        list_sort(captures.automatic_subs) as automatic_subs
    from {{ ref('int_manager_gameweek_status') }} as grid
    inner join {{ ref('stg_entry_picks_capture') }} as captures
        on captures.capture_key = grid.capture_key
    where grid.status = 'captured'

),

actual as (

    select season, entry_id, gameweek, active_chip, event_transfers,
           event_transfers_cost, list_sort(automatic_subs) as automatic_subs
    from {{ ref('fct_manager_gameweek') }}

)

(select 'expected only' as side, * from expected except select 'expected only', * from actual)
union all
(select 'served only', * from actual except select 'served only', * from expected)

{% if target.name == 'fixtures' %}
union all
select 'no transfer cost and automatic sub week in the fixture', null, null, null, null, null, null, null
where not exists (select 1 from {{ ref('fct_manager_gameweek') }} where event_transfers_cost > 0)
   or not exists (select 1 from {{ ref('fct_manager_gameweek') }} where len(automatic_subs) > 0)
{% endif %}
