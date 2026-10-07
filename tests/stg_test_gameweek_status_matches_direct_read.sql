-- Layer: stg
-- Tests: stg_gameweek_status
-- Asserts: stg_gameweek_status holds exactly the rows, values and types of the
--          direct read of event-status it replaced, so reading through the
--          declared columns changed nothing.
-- Origin: new in #115
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#115 AC2'}) }}

-- `direct` is stg_gameweek_status as it stood before #115: it unnests `status`
-- from the source itself rather than through declared_records. Kept verbatim so
-- the comparison is against the old behaviour, not a second copy of the new.
-- Each column is compared with its type, so a cast that drifted to another
-- type fails even when the values still compare equal. `except all` keeps
-- duplicates, so a row that appears a different number of times fails too.

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(status) as st
    from {{ source('fpl_raw', 'event_status') }}

),

direct as (

    select
        admitted.capture_key,
        admitted.season,
        admitted.extraction_date,
        admitted.run_id,
        admitted.extracted_at,
        admitted.observed_at,
        cast(st.event as integer)                  as gameweek,
        cast(st.date as date)                      as match_date,
        cast(st.points as varchar)                 as points,
        cast(st.bonus_added as boolean)            as bonus_added
    from raw
    inner join {{ ref('int_admitted_capture') }} as admitted
        on admitted.capture_key = raw.capture_key

),

{% set columns = ['capture_key', 'season', 'extraction_date', 'run_id', 'extracted_at',
                  'observed_at', 'gameweek', 'match_date', 'points', 'bonus_added'] %}

typed_direct as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from direct
),

typed_staged as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from {{ ref('stg_gameweek_status') }}
)

select 'only in direct read' as side, * from (select * from typed_direct except all select * from typed_staged)
union all
select 'only in staging' as side, * from (select * from typed_staged except all select * from typed_direct)
