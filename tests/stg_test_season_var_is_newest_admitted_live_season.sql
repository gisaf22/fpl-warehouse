-- Layer: stg
-- Tests: int_admitted_capture (the `season` var against the index)
-- Asserts: the `season` var equals the newest season among admitted live
--          captures, so the var cannot drift from the data (E5).
-- Origin: new in #104 (C2d of #88)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#104 AC8'}) }}

with newest as (
    select max(admitted.season) as season
    from {{ ref('int_admitted_capture') }} as admitted
    inner join {{ ref('base_capture_index') }} as captures
        on captures.capture_key = admitted.capture_key
    where captures.scope is distinct from 'history'
)

select '{{ var("season") }}' as season_var, newest.season as newest_admitted_live_season
from newest
where newest.season is distinct from '{{ var("season") }}'
