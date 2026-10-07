{#
    declared_records(table, record_path)

    Reads one record path of an fpl_raw payload source and selects exactly the
    columns declared at that path in models/staging/sources.yml, each named by
    its key (the column name's last dot-segment, as #114 D1 defines it), plus
    the capture's `capture_key`. Payload staging models read their source only
    through this macro (#115), so a field nobody declared cannot be read: a
    reference to it fails the build with DuckDB's binder error naming the field,
    and every field staging reads is covered by consumed_keys_present (#114).

    Supported record paths (#115 D2):
      '$.<array>[*]'  one row per element of a top-level array, unnested
      '$[*]'          the payload is itself an array; one row per element
    Any other path is a compile error naming it.

    Renames and casts stay in the staging model, in its own select over this
    output.
#}
{% macro declared_records(table, record_path) %}
    {%- set relation = source('fpl_raw', table) -%}
    {%- set nested = modules.re.fullmatch('\$\.([A-Za-z_][A-Za-z0-9_]*)\[\*\]', record_path) -%}
    {%- if not nested and record_path != '$[*]' -%}
        {{ exceptions.raise_compiler_error(
            "declared_records: record path " ~ record_path ~ " on fpl_raw." ~ table
            ~ " is not supported; use '$.<array>[*]' or '$[*]'") }}
    {%- endif -%}

    {%- set keys = [] -%}
    {%- if execute -%}
        {%- for node in graph.sources.values()
              if node.source_name == 'fpl_raw' and node.name == table -%}
            {%- for column in node.columns.values()
                  if (column.meta or {}).get('record_path') == record_path -%}
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
