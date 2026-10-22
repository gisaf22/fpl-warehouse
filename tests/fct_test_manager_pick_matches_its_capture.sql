-- Layer: fct
-- Tests: fct_manager_pick
-- Asserts: each served pick equals the winning capture's pick in the same slot
--          (player, captain, vice-captain), and is flagged as automatically
--          substituted in or out exactly when the capture's automatic_subs
--          names it; the fixture holds an automatic-sub week, so the flags are
--          not checked vacuously.
-- Origin: new in #216 (D9)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC9'}) }}

with winning as (

    select season, entry_id, gameweek, capture_key
    from {{ ref('int_manager_gameweek_status') }}
    where status = 'captured'

),

subs as (

    select captures.capture_key, unnest(captures.automatic_subs) as sub
    from {{ ref('stg_entry_picks_capture') }} as captures

),

expected as (

    select
        winning.season,
        winning.entry_id,
        winning.gameweek,
        picks.slot,
        picks.fpl_id,
        picks.is_captain,
        picks.is_vice_captain,
        exists (select 1 from subs where subs.capture_key = picks.capture_key
                and subs.sub.fpl_id_in = picks.fpl_id)  as is_auto_sub_in,
        exists (select 1 from subs where subs.capture_key = picks.capture_key
                and subs.sub.fpl_id_out = picks.fpl_id) as is_auto_sub_out
    from winning
    inner join {{ ref('stg_entry_picks') }} as picks
        on picks.capture_key = winning.capture_key

),

actual as (

    select season, entry_id, gameweek, slot, fpl_id, is_captain, is_vice_captain,
           is_auto_sub_in, is_auto_sub_out
    from {{ ref('fct_manager_pick') }}

),

differences as (

    (select 'expected only' as side, * from expected except select 'expected only', * from actual)
    union all
    (select 'served only', * from actual except select 'served only', * from expected)

)

select * from differences

{% if target.name == 'fixtures' %}
union all
select 'no automatic sub in the fixture', null, null, null, null, null, null, null, null, null
where not exists (select 1 from {{ ref('fct_manager_pick') }} where is_auto_sub_in)
{% endif %}
