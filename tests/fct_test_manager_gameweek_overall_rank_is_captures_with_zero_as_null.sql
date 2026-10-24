-- Layer: fct
-- Tests: fct_manager_gameweek
-- Asserts: each served overall_rank is its winning capture's, with 0 served
--          as NULL; a staged null stays NULL.
-- Origin: new in #219 (D1). The fixture's 1276382 has a staged 0 (GW2, GW3), a
--         staged null (GW4) and a rank (GW1), so the check is not vacuous.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC1'}) }}

with expected as (

    select
        grid.season,
        grid.entry_id,
        grid.gameweek,
        nullif(captures.overall_rank, 0) as overall_rank
    from {{ ref('int_manager_gameweek_status') }} as grid
    inner join {{ ref('stg_entry_picks_capture') }} as captures
        on captures.capture_key = grid.capture_key
    where grid.status = 'captured'

),

actual as (

    select season, entry_id, gameweek, overall_rank
    from {{ ref('fct_manager_gameweek') }}

)

(select 'expected only' as side, * from expected except select 'expected only', * from actual)
union all
(select 'served only', * from actual except select 'served only', * from expected)

{% if target.name == 'fixtures' %}
union all
select 'no served week from a staged 0, a staged null and a rank in the fixture', null, null, null, null
where not exists (
        select 1 from {{ ref('int_manager_gameweek_status') }} as grid
        inner join {{ ref('stg_entry_picks_capture') }} as captures using (capture_key)
        where grid.status = 'captured' and captures.overall_rank = 0)
   or not exists (
        select 1 from {{ ref('int_manager_gameweek_status') }} as grid
        inner join {{ ref('stg_entry_picks_capture') }} as captures using (capture_key)
        where grid.status = 'captured' and captures.overall_rank is null)
   or not exists (select 1 from {{ ref('fct_manager_gameweek') }} where overall_rank > 0)
{% endif %}
