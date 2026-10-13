-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_unstaged_admitted_capture
-- =============================================================================
--
-- Purpose:
--   Admitted captures that never reached staging (#167). Staging inner-joins
--   int_admitted_capture, so a payload that is missing or unparseable drops
--   out of every model silently. Each payload staging model's relationships
--   test checks staged within admitted; this is the other direction.
--
-- Grain:
--   One row per gap: an admitted capture of an in-scope endpoint with no row
--   in any of that endpoint's staging models (G2).
--
-- Scope and severity (G1, G6), read from models/staging/sources.yml:
--   in scope   an endpoint a payload source declares in meta.endpoint, so
--              event-live, with no staging model, is out by rule.
--   staging    every stg_ model that reads that source.
--   severity   error, unless the source's meta.unstaged_capture_warn_only
--              gives the reason it only warns. An endpoint added later fails
--              by default.
--   A capture's endpoint is its family: element-summary/{id} is
--   element-summary, as in latest_live_run_captures (#114 D3).
--
-- Dependencies:
--   The staging models are read from the graph, so each needs a depends_on
--   line below. A new staging model of a payload source without one fails
--   compilation ("unable to infer all dependencies"), so none is skipped.
--
-- Not covered:
--   A capture admitted after this build's payload read but before its
--   manifest read reads as a gap (G5). The run_id names it; a rebuild clears
--   it.
-- =============================================================================

-- depends_on: {{ ref('int_admitted_capture') }}
-- depends_on: {{ ref('stg_fixture') }}
-- depends_on: {{ ref('stg_gameweek') }}
-- depends_on: {{ ref('stg_gameweek_status') }}
-- depends_on: {{ ref('stg_player') }}
-- depends_on: {{ ref('stg_player_fixture') }}
-- depends_on: {{ ref('stg_position') }}
-- depends_on: {{ ref('stg_team') }}

{%- set endpoints = [] -%}
{%- if execute -%}
{%- for source in graph.sources.values()
                  | selectattr('source_name', 'equalto', 'fpl_raw')
                  | sort(attribute='name') -%}
    {%- set endpoint = source.meta.get('endpoint') -%}
    {%- if endpoint -%}
        {%- set warn_only = source.meta.get('unstaged_capture_warn_only') -%}
        {%- if warn_only is not none and not (warn_only | string | trim) -%}
            {{ exceptions.raise_compiler_error(
                "source " ~ source.name ~ ": meta.unstaged_capture_warn_only needs a reason"
            ) }}
        {%- endif -%}
        {%- set models = [] -%}
        {%- for node in graph.nodes.values()
                        | selectattr('resource_type', 'equalto', 'model')
                        | sort(attribute='name') -%}
            {%- if node.name.startswith('stg_') and source.unique_id in node.depends_on.nodes -%}
                {%- do models.append(node.name) -%}
            {%- endif -%}
        {%- endfor -%}
        {%- do endpoints.append({
            'endpoint': endpoint,
            'severity': 'warn' if warn_only else 'error',
            'models': models
        }) -%}
    {%- endif -%}
{%- endfor -%}
{%- endif %}

with in_scope (endpoint, severity) as (

    {%- if endpoints %}
    values
        {%- for e in endpoints %}
        ('{{ e.endpoint }}', '{{ e.severity }}'){{ "," if not loop.last }}
        {%- endfor %}
    {%- else %}
    select null::varchar, null::varchar where false
    {%- endif %}

),

staged as (

    {%- set reads = [] -%}
    {%- for e in endpoints -%}
        {%- for model in e.models -%}
            {%- do reads.append(
                "select '" ~ e.endpoint ~ "' as endpoint, capture_key from " ~ ref(model)
            ) -%}
        {%- endfor -%}
    {%- endfor %}
    {%- if reads %}
    {{ reads | join('\n    union\n    ') }}
    {%- else %}
    select null::varchar as endpoint, null::varchar as capture_key where false
    {%- endif %}

)

select
    in_scope.endpoint,
    admitted.season,
    admitted.run_id,
    admitted.capture_key,
    admitted.observed_at,
    in_scope.severity
from {{ ref('int_admitted_capture') }} as admitted
inner join in_scope
    on in_scope.endpoint = split_part(admitted.endpoint, '/', 1)
where not exists (
    select 1
    from staged
    where staged.endpoint = in_scope.endpoint
      and staged.capture_key = admitted.capture_key
)
