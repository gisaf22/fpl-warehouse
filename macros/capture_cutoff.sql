{#
    capture_cutoff_files()

    Test-only (#190). A staging pre-hook. With the `capture_cutoff` var unset it
    renders nothing, so a normal build runs no hook at all. Set to a date, it
    lists each fpl_raw payload source the model reads, in the live tree and every
    ported history season, keeps the payloads whose date directory (the
    extraction date) is before the cutoff, and stores that file list in a DuckDB
    variable, `capture_cutoff_files_<source>`. The source's external_location
    reads that variable instead of its globs, so a cutoff build reads only those
    payloads.

    A file list rather than date-pattern globs (#190 D1 revised): DuckDB reads
    every file a glob matches even when a filter excludes it, and a glob list
    fails outright if any one pattern matches nothing. The variable is set on
    the model's own connection, which is where its read runs.

    Each source names its glob below its tree's root in `meta.capture_glob`. An
    empty list (a cutoff before every capture) fails the read, loudly.
#}
{% macro capture_cutoff_files() %}
    {%- set cutoff = var("capture_cutoff", "") | string -%}
    {%- if cutoff and execute -%}
        {%- if target.name == "fixtures" -%}
            {%- set roots = ["tests/fixtures/raw", "tests/fixtures/history/*"] -%}
        {%- else -%}
            {%- set history_root = var("history_root", var("dev_history_root") if target.name == "dev" else "") -%}
            {%- set roots = [var("raw_root")] + ([history_root ~ "/*"] if history_root else []) -%}
        {%- endif -%}
        {%- for uid in model.depends_on.nodes if uid.startswith("source.fpl_warehouse.fpl_raw.") -%}
            {%- set source_node = graph.sources[uid] -%}
            {%- set glob = source_node.meta.get("capture_glob") -%}
            {%- if glob %}
set variable capture_cutoff_files_{{ source_node.name }} = (
    select list(file order by file)
    from (
        {%- for root in roots %}
        select file from glob('{{ root }}/{{ glob }}'){{ " union all" if not loop.last }}
        {%- endfor %}
    )
    where string_split(file, '/')[-3] < '{{ cutoff }}'
);
            {%- endif -%}
        {%- endfor -%}
    {%- endif -%}
{% endmacro %}
