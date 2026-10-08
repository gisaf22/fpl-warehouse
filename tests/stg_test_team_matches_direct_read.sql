-- Layer: stg
-- Tests: stg_team
-- Asserts: stg_team holds exactly the rows, values and types of the direct
--          read of bootstrap-static `teams` it replaced, so reading through the
--          declared columns changed nothing.
-- Origin: new in #115
-- Tier: integration
-- Fixture tree only (#115 D4): on a live target it re-reads every raw
-- payload, 689s for element-summary in served_diff run 37723026491.
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#115 AC2'},
          enabled=(target.name == 'fixtures')) }}

-- `direct` is stg_team as it stood before #115: it unnests `teams` from the
-- source itself rather than through declared_records. Kept verbatim so the
-- comparison is against the old behaviour, not a second copy of the new. Each
-- column is compared with its type, and `except all` keeps duplicates. See
-- stg_test_gameweek_status_matches_direct_read for the pattern.

with raw as (

    select
        {{ capture_key_from_filename() }} as capture_key,
        unnest(teams) as t
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
        cast(t.id as integer)                      as team_fpl_id,
        cast(t.code as integer)                    as team_code,
        cast(t.name as varchar)                    as team_name,
        cast(t.short_name as varchar)              as team_short_name,
        cast(t.strength as integer)                as strength
    from raw
    inner join {{ ref('int_admitted_capture') }} as admitted
        on admitted.capture_key = raw.capture_key

),

{% set columns = ['capture_key', 'season', 'extraction_date', 'run_id', 'extracted_at', 'observed_at', 'team_fpl_id', 'team_code', 'team_name', 'team_short_name', 'strength'] %}

typed_direct as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from direct
),

typed_staged as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from {{ ref('stg_team') }}
)

select 'only in direct read' as side, * from (select * from typed_direct except all select * from typed_staged)
union all
select 'only in staging' as side, * from (select * from typed_staged except all select * from typed_direct)
