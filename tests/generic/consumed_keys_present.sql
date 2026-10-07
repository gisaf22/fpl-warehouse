{#
    Every column declared on a payload source must still exist as a key in the
    raw JSON of that source's latest admitted live run (#114). Applied twice to
    each fpl_raw payload source in models/staging/sources.yml:

        mode: removed   severity error   key absent from every record
        mode: partial   severity warn    key absent from some records; no
                                         admitted live capture; or the latest
                                         admitted run has captures without a
                                         payload file

    Both modes read int_source_key_presence, which reads the raw objects once
    per build and holds one row per declared column (#114 D1, D2, D3). So
    declaring a column is enough to cover it.
#}
{% test consumed_keys_present(model, mode) %}
    {{ config(group='warehouse_internal') }}
    {%- set presence -%}
        (select * from {{ ref('int_source_key_presence') }}
         where source_name = '{{ model.identifier }}')
    {%- endset -%}
    {{ presence_findings(presence, mode) }}
{% endtest %}
