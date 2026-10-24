-- Layer: fct
-- Tests: fct_manager_gameweek, dim_gameweek
-- Asserts: every served overall_rank is NULL or between 1 and the
--          ranked_count of the same (season, gameweek); a gameweek whose
--          ranked_count is NULL is skipped.
-- Origin: new in #219 (D1, D2). In the fixture 10187394's GW3 rank of
--         10,365,313 is above GW2's count of 9,904,815, so a ranked_count
--         shifted by one gameweek fails; an unmapped 0 (1276382 GW2-3) fails
--         the lower bound.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#219 AC2'}) }}

with checked as (

    select
        manager.season,
        manager.entry_id,
        manager.gameweek,
        manager.overall_rank,
        dim.ranked_count
    from {{ ref('fct_manager_gameweek') }} as manager
    inner join {{ ref('dim_gameweek') }} as dim
        on dim.season = manager.season
       and dim.gameweek = manager.gameweek
    where dim.ranked_count is not null

)

select 'rank outside 1..ranked_count' as reason, *
from checked
where overall_rank is not null
  and (overall_rank < 1 or overall_rank > ranked_count)

{% if target.name == 'fixtures' %}
union all
select 'no ranked week with a ranked_count in the fixture', null, null, null, null, null
where not exists (select 1 from checked where overall_rank is not null)
{% endif %}
