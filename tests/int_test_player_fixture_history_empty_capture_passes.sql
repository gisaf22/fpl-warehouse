-- Layer: int
-- Tests: int_player_fixture_history_mismatch, int_unstaged_admitted_capture
-- Asserts: an admitted element-summary capture with an empty history[] is
--          staged at capture grain expecting 0 rows, stages no
--          stg_player_fixture row, and is listed by neither guard (#175 AC2a).
-- Origin: new in #175
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#175 AC2a'}) }}

-- Fixture-only: fpl_id 655's capture in 20260910T191141Z-9d8de9 is one of the
-- 31 pre-debut captures #175 AC1 measured on live S3, kept verbatim in
-- tests/fixtures/raw (build_fixtures.py, EMPTY_HISTORY).

{% if target.name != 'fixtures' %}

select null as problem where false

{% else %}

{% set key = 'raw/fpl/element-summary/655/2026-09-10/20260910T191141Z-9d8de9/payload.json' %}

select 'not staged at capture grain with 0 expected rows' as problem
where not exists (
    select 1 from {{ ref('stg_player_history_capture') }}
    where capture_key = '{{ key }}' and history_count = 0
)
union all
select 'has stg_player_fixture rows'
where exists (select 1 from {{ ref('stg_player_fixture') }} where capture_key = '{{ key }}')
union all
select 'listed as a history count mismatch'
where exists (
    select 1 from {{ ref('int_player_fixture_history_mismatch') }} where capture_key = '{{ key }}'
)
union all
select 'listed as an unstaged admitted capture'
where exists (
    select 1 from {{ ref('int_unstaged_admitted_capture') }} where capture_key = '{{ key }}'
)

{% endif %}
