-- Layer: int
-- Tests: int_capture_admission
-- Asserts: every capture of a run the seed marks local is not admitted, with
--          reason not_production, and every capture of the history port with a
--          usable verdict is admitted.
-- Origin: new in #97 (C1c of #87, decisions D2, D3, D5)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#97 AC2'}) }}

-- 07eb06 is excluded by its seed row, never by its id: no model names it. Its
-- captures also have a null season, so the reason proves the run, not the
-- season, is what excluded them.

with admission as (

    select admission.*, seed.origin_kind as seed_kind
    from {{ ref('int_capture_admission') }} as admission
    inner join {{ ref('seed_run_origin') }} as seed
        on seed.run_id = admission.run_id

)

select capture_key, run_id, 'local run admitted or misreasoned' as failure
from admission
where seed_kind = 'local'
  and (admitted or unadmitted_reason is distinct from 'not_production')

union all

select capture_key, run_id, 'history port capture not admitted'
from admission
where seed_kind = 'history_port'
  and not admitted
  and unadmitted_reason not in ('unusable', 'null_season')

{% if target.name == 'fixtures' %}

-- The fixture holds both cases (LOCAL_RUN and the history run in
-- tests/fixtures/build_fixtures.py), so an empty side fails here instead of
-- passing without having checked anything.
union all

select null, null, 'fixture has no ' || kind || ' capture to check'
from (values ('local'), ('history_port')) as kinds (kind)
where kind not in (select seed_kind from admission)

{% endif %}
