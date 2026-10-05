{#
    Passed transfer deadlines with no admitted capture in their pre-deadline
    window (#111). One row per (season, gameweek, deadline_time) missed.

    gameweeks:  a relation with season, gameweek, deadline_time, observed_at
                and run_id, one row per gameweek per capture (stg_gameweek).
                The deadline is the one in the latest capture, because FPL
                can move a deadline (#80 AC5).
    captures:   a relation with season and observed_at, one row per admitted
                capture. Any endpoint and any trigger counts.
    as_of:      the "now" a deadline must be before to have passed.

    Window: [deadline - (gate + buffer) minutes, deadline). See the
    pre_deadline_* vars in dbt_project.yml. A capture covers only its own
    season's deadlines.
#}
{% macro missed_pre_deadline_windows(gameweeks, captures, as_of=none) -%}
    {%- set window_minutes = var('pre_deadline_gate_minutes') + var('pre_deadline_buffer_minutes') -%}
    select deadlines.season, deadlines.gameweek, deadlines.deadline_time
    from (
        select season, gameweek, deadline_time
        from {{ gameweeks }}
        qualify row_number() over (
            partition by season, gameweek
            order by observed_at desc, run_id desc
        ) = 1
    ) as deadlines
    where deadlines.deadline_time >= cast('{{ var("pre_deadline_coverage_start") }}' as timestamp)
      and deadlines.deadline_time < {{ as_of if as_of else as_of_utc() }}
      and not exists (
          select 1
          from {{ captures }} as captures
          where captures.season = deadlines.season
            and captures.observed_at >= deadlines.deadline_time - interval {{ window_minutes }} minute
            and captures.observed_at < deadlines.deadline_time
      )
{%- endmacro %}
