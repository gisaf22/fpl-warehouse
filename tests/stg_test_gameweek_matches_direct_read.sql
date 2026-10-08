-- Layer: stg
-- Tests: stg_gameweek
-- Asserts: stg_gameweek holds exactly the rows, values and types of the direct
--          read of bootstrap-static `events` it replaced, so reading through the
--          declared columns changed nothing.
-- Origin: new in #115
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#115 AC2'}) }}

-- `direct` is stg_gameweek as it stood before #115: it unnests `events` from the
-- source itself rather than through declared_records. Kept verbatim so the
-- comparison is against the old behaviour, not a second copy of the new. Each
-- column is compared with its type, and `except all` keeps duplicates. See
-- stg_test_gameweek_status_matches_direct_read for the pattern.

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(events) as ev
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
        cast(ev.id as integer)                     as gameweek,
        cast(ev.deadline_time as timestamp)        as deadline_time,
        cast(ev.finished as boolean)               as finished,
        cast(ev.data_checked as boolean)           as data_checked,
        cast(ev.is_current as boolean)             as is_current
    from raw
    inner join {{ ref('int_admitted_capture') }} as admitted
        on admitted.capture_key = raw.capture_key

),

{% set columns = ['capture_key', 'season', 'extraction_date', 'run_id', 'extracted_at', 'observed_at', 'gameweek', 'deadline_time', 'finished', 'data_checked', 'is_current'] %}

typed_direct as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from direct
),

typed_staged as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from {{ ref('stg_gameweek') }}
)

select 'only in direct read' as side, * from (select * from typed_direct except all select * from typed_staged)
union all
select 'only in staging' as side, * from (select * from typed_staged except all select * from typed_direct)
