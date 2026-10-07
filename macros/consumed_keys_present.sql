{#
    The pieces of the consumed_keys_present test (#114), split out so each can
    be tested with inline data. The test itself is
    tests/generic/consumed_keys_present.sql.
#}

{#
    One check per column declared on a source, skipping a column whose
    meta.presence_exempt gives a reason (#114 D1). The key is the name's last
    dot-segment (`elements.id` -> `id`). meta.record_path is a JSON path that
    yields the records holding the key (`$.elements[*]`, `$[*].stats[*]`);
    absent, the key sits at the top of the payload. An exemption with an empty
    reason is still checked here, and fails CI's manifest check.
#}
{% macro consumed_key_specs(columns) -%}
    {%- set specs = [] -%}
    {%- for column in columns.values() -%}
        {%- set meta = column.get('meta') or {} -%}
        {%- set reason = meta.get('presence_exempt') -%}
        {%- if not (reason and reason | trim) -%}
            {%- do specs.append({
                'column': column.name,
                'key': column.name.split('.')[-1],
                'record_path': meta.get('record_path')
            }) -%}
        {%- endif -%}
    {%- endfor -%}
    {{ return(specs) }}
{%- endmacro %}

{#
    The captures of an endpoint's latest admitted live run (#114 D3): every
    capture from the run of the newest capture, ordered by observed_at with
    run_id breaking a tie. Every one of the run's captures, not each entity's
    own latest: element-summary is one endpoint per player
    (`element-summary/{id}`), and a player not re-captured in the newest run
    would keep a removed key visible. Ported history captures (keys under
    `history/`) are never live.

    admitted: a relation with capture_key, endpoint, run_id and observed_at
              (int_admitted_capture).
    present:  optional, a relation with the capture_key of every object that
              exists. When given, a capture without bytes cannot be chosen, the
              way staging never sees one (an index entry whose payload is
              absent, as in the fixture tree's index-only run).
#}
{% macro latest_live_run_captures(admitted, endpoint, present=none) -%}
    select capture_key, run_id
    from (
        select
            capture_key,
            run_id,
            first_value(run_id) over (
                order by observed_at desc, run_id desc
            ) as latest_run_id
        from {{ admitted }}
        where starts_with(capture_key, 'raw/')
          and split_part(endpoint, '/', 1) = '{{ endpoint }}'
          {%- if present is not none %}
          and capture_key in (select capture_key from {{ present }})
          {%- endif %}
    )
    where run_id = latest_run_id
{%- endmacro %}

{#
    Findings for a source's consumed keys over one run's captures (#114).
    One row per (source, column) that fails the mode:

        removed  the key is absent from every record (error severity)
        partial  the key is absent from some records but not all (warn)

    With no capture at all, `partial` returns one row naming the source and
    `removed` returns nothing: emptiness belongs to the freshness guard (AC7).
    A column with no records (an empty array) is reported by neither.

    A key present with a null value counts as present: json_exists sees the
    key, not its value (#114 D2).

    captures: a relation with capture_key and run_id.
    objects:  a relation with capture_key and json, one row per payload.
#}
{% macro consumed_key_findings(source_name, specs, captures, objects, mode) -%}
    {%- if mode not in ('removed', 'partial') -%}
        {{ exceptions.raise_compiler_error("consumed_keys_present: mode must be 'removed' or 'partial', got " ~ mode) }}
    {%- endif -%}
    with run as (
        select min(run_id) as run_id, count(*) as captures
        from {{ captures }}
    ),

    payloads as (
        select objects.json
        from {{ objects }} as objects
        where objects.capture_key in (select capture_key from {{ captures }})
    ),

    checked as (
        {%- for spec in specs %}
        select
            '{{ spec.column }}' as column_name,
            count(rec)          as records,
            count(rec) filter (where not json_exists(rec, '$."{{ spec.key }}"'))
                                as missing
        from (
            {%- if spec.record_path %}
            select unnest(json_extract(json, '{{ spec.record_path }}')) as rec from payloads
            {%- else %}
            select json as rec from payloads
            {%- endif %}
        )
        {%- if not loop.last %}
        union all
        {%- endif %}
        {%- endfor %}
        {%- if not specs %}
        select null::varchar, 0::bigint, 0::bigint where false
        {%- endif %}
    )

    select
        '{{ source_name }}'          as source_name,
        checked.column_name,
        run.run_id,
        run.captures,
        checked.records,
        checked.missing,
        {%- if mode == 'removed' %}
        'key absent from every record' as finding
        {%- else %}
        'key absent from some records' as finding
        {%- endif %}
    from checked
    cross join run
    where run.captures > 0
      {%- if mode == 'removed' %}
      and checked.records > 0
      and checked.missing = checked.records
      {%- else %}
      and checked.missing > 0
      and checked.missing < checked.records
      {%- endif %}
    {%- if mode == 'partial' %}

    union all

    select
        '{{ source_name }}', null, null, 0, 0, 0,
        'no admitted live capture'
    from run
    where run.captures = 0
    {%- endif %}
{%- endmacro %}
