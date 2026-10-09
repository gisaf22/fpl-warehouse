{#
    declared_records(table, record_path)

    Reads one record path of an fpl_raw payload source and selects exactly the
    columns declared at that path in models/staging/sources.yml, each named by
    its key (the column name's last dot-segment, as #114 D1 defines it), plus
    the capture's `capture_key`. Payload staging models read their source only
    through this macro (#115), so a field nobody declared cannot be read: a
    reference to it fails the build with DuckDB's binder error naming the field,
    and every field staging reads is covered by consumed_keys_present (#114).

    Supported record paths (#115 D2, #140 D1):
      '$.<array>[*]'  one row per element of a top-level array, unnested
      '$[*]'          the payload is itself an array; one row per element
      '$'             the payload root; one row per payload. Reads the columns
                      declared with no record_path, which #114 already checks
                      for presence at the top of the payload (e.g.
                      bootstrap-static's total_players)
    Any other path is a compile error naming it.

    Renames and casts stay in the staging model, in its own select over this
    output.

    dbt compiles a unit test with an empty graph, so the declarations cannot
    be read there; only then does the macro pass through every column the
    mocked source gives. A mock holds only the columns its test lists. The
    unit test is identified by the node's resource_type, never by the empty
    graph alone: an empty graph anywhere else is a compile error naming this
    macro, so the restriction cannot silently lapse where raw data is read.
#}
{% macro declared_records(table, record_path) %}
    {%- set relation = source('fpl_raw', table) -%}
    {%- set nested = modules.re.fullmatch('\$\.([A-Za-z_][A-Za-z0-9_]*)\[\*\]', record_path) -%}
    {%- if not nested and record_path not in ('$[*]', '$') -%}
        {{ exceptions.raise_compiler_error(
            "declared_records: record path " ~ record_path ~ " on fpl_raw." ~ table
            ~ " is not supported; use '$.<array>[*]', '$[*]' or '$'") }}
    {%- endif -%}

    {%- set keys = [] -%}
    {%- set unit_test = execute and declared_records_passes_through(model.resource_type, graph) -%}
    {%- if execute and not unit_test -%}
        {%- for node in graph.sources.values()
              if node.source_name == 'fpl_raw' and node.name == table -%}
            {#- A root column is declared with no record_path at all. -#}
            {%- for column in node.columns.values()
                  if (column.meta or {}).get('record_path', '$') == record_path -%}
                {%- do keys.append(column.name.split('.')[-1]) -%}
            {%- endfor -%}
        {%- endfor -%}
        {%- if not keys -%}
            {{ exceptions.raise_compiler_error(
                "declared_records: fpl_raw." ~ table ~ " declares no column at record path "
                ~ record_path) }}
        {%- endif -%}
    {%- endif -%}

    {%- set record = 'rec' if nested else 'payload' %}
    select
        {{ capture_key_from_filename() }} as capture_key
        {%- if unit_test %},
        {{ record }}.*
        {%- endif %}
        {%- for key in keys %},
        {{ record }}."{{ key }}" as "{{ key }}"
        {%- endfor %}
    from
    {%- if nested %} (
        select filename, unnest({{ nested.group(1) }}) as rec
        from {{ relation }}
    )
    {%- else %} {{ relation }} as payload
    {%- endif %}
{% endmacro %}

{#
    declared_records_passes_through(resource_type, graph)

    True only for a unit test (resource_type 'unit_test'), whose graph dbt
    leaves empty. False when the graph is populated. Any other node with an
    empty graph is a compile error. Called as a run-operation, it logs which
    route it took, which is how scripts/tests exercise both routes.
#}
{% macro declared_records_passes_through(resource_type, graph) %}
    {%- if resource_type == 'unit_test' -%}
        {%- set through = true -%}
    {%- elif not graph -%}
        {{ exceptions.raise_compiler_error(
            "declared_records: the dbt graph is empty outside a unit test (resource_type "
            ~ resource_type ~ "), so the declared columns cannot be read") }}
    {%- else -%}
        {%- set through = false -%}
    {%- endif -%}
    {%- if flags.WHICH == 'run-operation' -%}
        {%- do log('declared_records ' ~ ('passes through' if through else 'reads declarations'), info=True) -%}
    {%- endif -%}
    {{ return(through) }}
{% endmacro %}
