-- Layer: int
-- Tests: int_manager_gameweek_status, fct_manager_gameweek, fct_manager_pick
-- Asserts: a gameweek without a settlement marker has no row in the grid or in
--          either served table, though its picks are staged; and the fixture
--          stages a capture of such a gameweek, so the check is not vacuous.
-- Origin: new in #216 (D4)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC4'}) }}

with marked as (

    select season, gameweek from {{ ref('stg_entry_picks_settlement') }}

),

rows_by_model as (

    select 'int_manager_gameweek_status' as model, season, gameweek
    from {{ ref('int_manager_gameweek_status') }}
    union all
    select 'fct_manager_gameweek', season, gameweek
    from {{ ref('fct_manager_gameweek') }}
    union all
    select 'fct_manager_pick', season, gameweek
    from {{ ref('fct_manager_pick') }}

)

select distinct model, season, gameweek
from rows_by_model
where (season, gameweek) not in (select season, gameweek from marked)

{% if target.name == 'fixtures' %}
union all
select 'no staged capture of an unmarked gameweek in the fixture', null, null
where not exists (
    select 1
    from {{ ref('stg_entry_picks_capture') }} as captures
    where (captures.season, captures.gameweek) not in (select season, gameweek from marked)
)
{% endif %}
