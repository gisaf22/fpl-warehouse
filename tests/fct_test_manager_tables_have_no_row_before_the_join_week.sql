-- Layer: fct
-- Tests: fct_manager_gameweek, fct_manager_pick
-- Asserts: neither served table has a row for a gameweek before the manager's
--          join week (absent, never a NULL row), and fct_manager_gameweek holds
--          exactly the grid's captured rows; the fixture holds a late joiner,
--          so the check is not vacuous.
-- Origin: new in #216 (D5)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC5'}) }}

with served as (

    select 'fct_manager_gameweek' as model, season, entry_id, gameweek
    from {{ ref('fct_manager_gameweek') }}
    union all
    select distinct 'fct_manager_pick', season, entry_id, gameweek
    from {{ ref('fct_manager_pick') }}

),

captured as (

    select season, entry_id, gameweek
    from {{ ref('int_manager_gameweek_status') }}
    where status = 'captured'

)

-- A served manager-gameweek the grid does not hold as captured.
select served.model, served.season, served.entry_id, served.gameweek, 'not captured' as problem
from served
where (served.season, served.entry_id, served.gameweek)
      not in (select season, entry_id, gameweek from captured)

union all

-- A captured manager-gameweek missing from either served table.
select models.model, captured.season, captured.entry_id, captured.gameweek, 'missing'
from captured
cross join (values ('fct_manager_gameweek'), ('fct_manager_pick')) as models(model)
where (models.model, captured.season, captured.entry_id, captured.gameweek)
      not in (select model, season, entry_id, gameweek from served)

{% if target.name == 'fixtures' %}
union all
select 'int_manager_gameweek_status', null, null, null, 'no late joiner in the fixture'
where not exists (
    select 1 from {{ ref('int_manager_gameweek_status') }} where status = 'not_yet_joined'
)
{% endif %}
