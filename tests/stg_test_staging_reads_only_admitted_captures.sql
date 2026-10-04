-- Layer: stg
-- Tests: stg_player_fixture, stg_player, stg_position, stg_team, stg_gameweek,
--        stg_fixture, stg_gameweek_status
-- Asserts: every capture a payload staging model holds is admitted; none is
--          unadmitted or missing from the capture index.
-- Origin: new in #104 (C2d of #88)
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#104 AC1'}) }}

with staged as (
    {% for model in ['stg_player_fixture', 'stg_player', 'stg_position', 'stg_team',
                     'stg_gameweek', 'stg_fixture', 'stg_gameweek_status'] %}
    select distinct '{{ model }}' as model, capture_key from {{ ref(model) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select staged.model, staged.capture_key,
       coalesce(admission.unadmitted_reason, 'not in the capture index') as failure
from staged
left join {{ ref('int_capture_admission') }} as admission
    on admission.capture_key = staged.capture_key
where admission.admitted is distinct from true

{% if target.name == 'fixtures' %}
-- Non-vacuity, fixture build only: the tree must hold at least one payload of
-- an unadmitted capture (the local run's, see LOCAL_RUN_PAYLOAD_FPL_ID in
-- tests/fixtures/build_fixtures.py), or the check above has nothing to
-- exclude. Not run against live S3, where it would re-read every payload.
union all

select null, null, 'no unadmitted capture with a payload to test against'
where not exists (
    select 1
    from (
        select {{ capture_key_from_filename() }} as capture_key
        from {{ source('fpl_raw', 'element_summary') }}
    ) as payloads
    inner join {{ ref('int_capture_admission') }} as admission
        on admission.capture_key = payloads.capture_key
    where not admission.admitted
)
{% endif %}
