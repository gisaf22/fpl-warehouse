-- Layer: stg
-- Tests: stg_player
-- Asserts: stg_player holds exactly the rows, values and types of the direct
--          read of bootstrap-static `elements` it replaced, so reading through the
--          declared columns changed nothing.
-- Origin: new in #115
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#115 AC2'}) }}

-- `direct` is stg_player as it stood before #115: it unnests `elements` from the
-- source itself rather than through declared_records. Kept verbatim so the
-- comparison is against the old behaviour, not a second copy of the new. Each
-- column is compared with its type, and `except all` keeps duplicates. See
-- stg_test_gameweek_status_matches_direct_read for the pattern.

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(elements) as e
    from {{ source('fpl_raw', 'bootstrap_static') }}

),

direct as (

    select
        admitted.capture_key,
        admitted.season,
        admitted.extraction_date,
        admitted.run_id,
        admitted.extracted_at,
        admitted.observed_at,
        cast(e.id as integer)                      as fpl_id,
        cast(e.web_name as varchar)                as web_name,
        cast(e.code as integer)                    as player_code,
        cast(e.element_type as integer)            as position_id,
        cast(e.total_points as integer)            as total_points
    from raw
    inner join {{ ref('int_admitted_capture') }} as admitted
        on admitted.capture_key = raw.capture_key

),

{% set columns = ['capture_key', 'season', 'extraction_date', 'run_id', 'extracted_at', 'observed_at', 'fpl_id', 'web_name', 'player_code', 'position_id', 'total_points'] %}

typed_direct as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from direct
),

typed_staged as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from {{ ref('stg_player') }}
)

select 'only in direct read' as side, * from (select * from typed_direct except all select * from typed_staged)
union all
select 'only in staging' as side, * from (select * from typed_staged except all select * from typed_direct)
