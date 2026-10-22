-- Layer: stg
-- Tests: stg_entry_picks_capture, stg_entry_picks
-- Asserts: no staged row comes from a capture under raw/fpl/_invalid/; the
--          fixture's index holds pre-join 404s there, so the check is not
--          vacuous.
-- Origin: new in #216 (D11; raw contract 2.5.0 invalid captures)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#216 AC14'}) }}

with staged as (

    select 'stg_entry_picks_capture' as model, capture_key from {{ ref('stg_entry_picks_capture') }}
    union all
    select 'stg_entry_picks', capture_key from {{ ref('stg_entry_picks') }}

)

select model, capture_key
from staged
where capture_key like 'raw/fpl/\_invalid/%' escape '\'

{% if target.name == 'fixtures' %}
union all
select 'no invalid entry-picks capture in the fixture index', null
where not exists (
    select 1 from {{ ref('base_capture_index') }}
    where capture_key like 'raw/fpl/\_invalid/%' escape '\'
      and split_part(endpoint, '/', 1) = 'entry-picks'
)
{% endif %}
