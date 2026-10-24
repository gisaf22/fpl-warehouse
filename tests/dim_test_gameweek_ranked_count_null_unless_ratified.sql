-- Layer: dim
-- Tests: dim_gameweek
-- Asserts: ranked_count is non-null exactly for the ratified gameweeks of the
--          seasons it is served for, and NULL for every other row. Ratified
--          is int_gameweek_status's verdict, or the dated fallback: a 2026-27
--          gameweek in no event-status capture whose deadline is before
--          2026-08-29, when capture history began. 2025-26 is not served: it
--          has no ratification signal and no consumer.
-- Origin: new in #219 (D2, D3). In the fixture GW4 is in event-status but
--         still 'p', with a provisional 10,674,677, and GW5-38 read 0; all
--         must be NULL. The 2025-26 capture holds GW1 = 9,469,118, which must
--         not be served. 2026-27 GW1-3 must be non-null.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC5'}) }}

with served as (

    select
        dim.season,
        dim.gameweek,
        dim.deadline_time,
        dim.ranked_count,
        status.is_ratified,
        status.gameweek is not null as in_event_status
    from {{ ref('dim_gameweek') }} as dim
    left join {{ ref('int_gameweek_status') }} as status
        on status.season = dim.season
       and status.gameweek = dim.gameweek

),

expected as (

    select
        *,
        coalesce(is_ratified, false)
            or (season = '2026-27'
                and not in_event_status
                and deadline_time < timestamp '2026-08-29 00:00:00') as should_be_served
    from served

)

select
    case when should_be_served then 'ratified but NULL' else 'served before ratification or for an unserved season' end as reason,
    season,
    gameweek,
    ranked_count
from expected
where should_be_served <> (ranked_count is not null)

{% if target.name == 'fixtures' %}
union all
select 'fixture lacks a served gameweek, an unratified one in event-status, or a 2025-26 row', null, null, null
where not exists (select 1 from expected where should_be_served)
   or not exists (select 1 from expected where in_event_status and not is_ratified)
   or not exists (select 1 from expected where season = '2025-26')
{% endif %}
