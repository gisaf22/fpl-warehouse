-- Layer: stg
-- Tests: stg_fixture
-- Asserts: stg_fixture holds exactly the rows, values and types of the direct
--          read of fixtures it replaced, so reading through the declared
--          columns at the top-level `$[*]` path changed nothing.
-- Origin: new in #115
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#115 AC2'}) }}

-- `direct` is stg_fixture as it stood before #115: it selects `*` from the
-- source itself rather than through declared_records. Kept verbatim so the
-- comparison is against the old behaviour, not a second copy of the new. Each
-- column is compared with its type, and `except all` keeps duplicates. See
-- stg_test_gameweek_status_matches_direct_read for the pattern.

with direct as (

    select
        admitted.capture_key,
        admitted.season,
        admitted.extraction_date,
        admitted.run_id,
        admitted.extracted_at,
        admitted.observed_at,
        cast(id as integer)                        as fixture_id,
        cast(event as integer)                     as gameweek,
        cast(kickoff_time as timestamp)            as kickoff_time,
        cast(team_h as integer)                    as team_h_fpl_id,
        cast(team_a as integer)                    as team_a_fpl_id,
        cast(team_h_score as integer)              as team_h_score,
        cast(team_a_score as integer)              as team_a_score,
        cast(finished as boolean)                  as finished,
        cast(team_h_difficulty as integer)         as team_h_difficulty,
        cast(team_a_difficulty as integer)         as team_a_difficulty
    from (
        select {{ capture_key_from_filename() }} as capture_key, *
        from {{ source('fpl_raw', 'fixtures') }}
    ) as raw
    inner join {{ ref('int_admitted_capture') }} as admitted
        on admitted.capture_key = raw.capture_key

),

{% set columns = ['capture_key', 'season', 'extraction_date', 'run_id', 'extracted_at',
                  'observed_at', 'fixture_id', 'gameweek', 'kickoff_time', 'team_h_fpl_id',
                  'team_a_fpl_id', 'team_h_score', 'team_a_score', 'finished',
                  'team_h_difficulty', 'team_a_difficulty'] %}

typed_direct as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from direct
),

typed_staged as (
    select {% for c in columns %}{{ c }}, typeof({{ c }}) as {{ c }}_type{{ ',' if not loop.last }}{% endfor %}
    from {{ ref('stg_fixture') }}
)

select 'only in direct read' as side, * from (select * from typed_direct except all select * from typed_staged)
union all
select 'only in staging' as side, * from (select * from typed_staged except all select * from typed_direct)
