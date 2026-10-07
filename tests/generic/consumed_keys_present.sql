{#
    Every column declared on a payload source must still exist as a key in the
    raw JSON of that source's latest admitted live run (#114). Applied twice to
    each fpl_raw payload source in models/staging/sources.yml:

        mode: removed   severity error   key absent from every record
        mode: partial   severity warn    key absent from some records, or no
                                         admitted live capture at all

    A key present with a null value passes: presence is read from the raw
    objects with json_exists, not from the typed columns, where a missing key
    and a null look the same (#114 D2).

    The columns checked are the source's declared columns, read from the graph
    at compile time, so declaring a column is enough to cover it (#114 D1).
    `columns` overrides them, in the same shape, for a test of this test.

    The source's meta.endpoint names its capture-index endpoint
    (`element-summary` matches `element-summary/{id}`). Only that endpoint's
    latest admitted live run with bytes is read (a glob of the endpoint's
    live prefix lists which exist), object by object, from the paths of its
    capture keys: this file and stg_test_fixture_tree_reads_no_s3_object are
    the two places that read an object's path (CLAUDE.md, "Layering").
#}
{% test consumed_keys_present(model, mode, columns=none) %}
    {{ config(group='warehouse_internal') }}
    {%- set admitted = ref('int_admitted_capture') -%}

    {%- if not execute -%}
        select 1 where false
    {%- else -%}
        {%- set node = (graph.sources.values()
                        | selectattr('source_name', 'equalto', 'fpl_raw')
                        | selectattr('name', 'equalto', model.identifier)
                        | list) -%}
        {%- if node | length != 1 -%}
            {{ exceptions.raise_compiler_error("consumed_keys_present: no fpl_raw source named " ~ model.identifier) }}
        {%- endif -%}
        {%- set node = node[0] -%}
        {%- set endpoint = node.meta.get('endpoint') -%}
        {%- if not endpoint -%}
            {{ exceptions.raise_compiler_error("consumed_keys_present: source " ~ node.name ~ " has no meta.endpoint") }}
        {%- endif -%}
        {%- set specs = consumed_key_specs(columns if columns is not none else node.columns) -%}

        {%- set root = 'tests/fixtures/raw' if target.name == 'fixtures' else var('raw_root') -%}
        {%- set present -%}
            (select {{ capture_key_from_filename('file') }} as capture_key
             from glob('{{ root }}/fpl/{{ endpoint }}/**/payload.json'))
        {%- endset -%}
        {%- set latest = run_query(latest_live_run_captures(admitted, endpoint, present)) -%}
        {%- set paths = [] -%}
        {%- for row in latest.rows -%}
            {#- A live key is `raw/...`, rooted at the tree raw_root points to. -#}
            {%- do paths.append("'" ~ root ~ "/" ~ row['capture_key'][4:] ~ "'") -%}
        {%- endfor -%}

        {%- set captures -%}
            ({{ latest_live_run_captures(admitted, endpoint, present) }})
        {%- endset -%}
        {%- set objects -%}
            {%- if paths -%}
            (select {{ capture_key_from_filename() }} as capture_key, json
             from read_json_objects(
                 [{{ paths | join(', ') }}],
                 format = 'unstructured',
                 filename = true
             ))
            {%- else -%}
            (select null::varchar as capture_key, null::json as json where false)
            {%- endif -%}
        {%- endset -%}

        select * from (
            {{ consumed_key_findings(node.name, specs, captures, objects, mode) }}
        )
    {%- endif -%}
{% endtest %}
