-- Layer: stg
-- Tests: sources fpl_raw.fixtures and fpl_raw.bootstrap_static (teams,
--        element_types)
-- Asserts: the checked-in capture carries at least one fixture, team and
--          position row for the live season and for the ported 2025-26
--          season.
-- Origin: new in #36 — the staging and dimension models for fixtures, teams
--         and positions (#37, #38 onward) build against this tree on every PR.
-- Tier: integration
{{ config(group='warehouse_internal', tags=['integration'], meta={'covers': '#36 AC1'}) }}

-- Reads the sources, not staging: what is asserted is the tree itself. Each
-- payload's season comes from the capture index (#104).
--
-- Fixtures target only. On `dev` the seasons present depend on whether
-- history_root is set for that run, which is not what this test is about.

{% if target.name != 'fixtures' %}

select null as failure where false

{% else %}

with expected as (

    select unnest(['{{ var("season") }}', '2025-26']) as season

),

fixtures as (

    select admitted.season, count(*) as n
    from (
        select {{ capture_key_from_filename() }} as capture_key
        from {{ source('fpl_raw', 'fixtures') }}
    ) as raw
    inner join {{ ref('int_admitted_capture') }} as admitted using (capture_key)
    group by 1

),

teams as (

    select season, count(*) as n
    from (
        select admitted.season, raw.t
        from (
            select {{ capture_key_from_filename() }} as capture_key, unnest(teams) as t
            from {{ source('fpl_raw', 'bootstrap_static') }}
        ) as raw
        inner join {{ ref('int_admitted_capture') }} as admitted using (capture_key)
    )
    group by 1

),

positions as (

    select season, count(*) as n
    from (
        select admitted.season, raw.p
        from (
            select {{ capture_key_from_filename() }} as capture_key, unnest(element_types) as p
            from {{ source('fpl_raw', 'bootstrap_static') }}
        ) as raw
        inner join {{ ref('int_admitted_capture') }} as admitted using (capture_key)
    )
    group by 1

)

select
    expected.season,
    coalesce(fixtures.n, 0)  as fixture_rows,
    coalesce(teams.n, 0)     as team_rows,
    coalesce(positions.n, 0) as position_rows
from expected
left join fixtures  using (season)
left join teams     using (season)
left join positions using (season)
where coalesce(fixtures.n, 0) = 0
   or coalesce(teams.n, 0) = 0
   or coalesce(positions.n, 0) = 0

{% endif %}
