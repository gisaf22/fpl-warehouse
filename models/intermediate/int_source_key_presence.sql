-- =============================================================================
-- Layer: int_ (intermediate)
-- Model: int_source_key_presence
-- =============================================================================
--
-- Purpose:
--   Whether each consumed source field is still a key in the raw JSON of its
--   endpoint's latest admitted live run (#114). Read once per build here, so
--   the two consumed_keys_present tests on each source (removed, partial)
--   read this table rather than the raw objects twice.
--
-- Grain:
--   One row per (source_name, column_name): every column declared on an
--   fpl_raw payload source in models/staging/sources.yml (one with
--   meta.endpoint), except a column exempt with a reason in
--   meta.presence_exempt.
--
-- Which captures:
--   The endpoint's latest admitted live run that has payload files: every
--   capture of the run of the newest capture with a file (#114 D3). When the
--   latest admitted run has captures with no file, latest_run_id names it and
--   latest_run_missing_bytes counts them, and the partial test warns.
--
-- Columns:
--   run_id, captures          the run checked and how many captures were read;
--                             null and 0 when the source has no admitted live
--                             capture.
--   records, missing          records holding the key's record path, and those
--                             without the key. A key holding null is present.
--   latest_run_id,            the latest admitted live run, when it has
--   latest_run_missing_bytes  captures without a file; else null and 0.
--
-- Reads object paths:
--   Each chosen capture's path is its capture_key under the live root. This
--   model and stg_test_fixture_tree_reads_no_s3_object are the only places
--   that read a path (CLAUDE.md, "Layering").
-- =============================================================================

{{ config(materialized='table') }}

-- depends_on: {{ ref('int_admitted_capture') }}
{%- set admitted = ref('int_admitted_capture') -%}
{%- set root = 'tests/fixtures/raw' if target.name == 'fixtures' else var('raw_root') -%}
{%- set parts = [] -%}

{%- if execute -%}
{%- for node in graph.sources.values()
                | selectattr('source_name', 'equalto', 'fpl_raw')
                | sort(attribute='name') -%}
    {%- set endpoint = node.meta.get('endpoint') -%}
    {%- set specs = consumed_key_specs(node.columns) if endpoint else [] -%}
    {%- if specs -%}

        {%- set candidates_sql -%}
            with present as materialized (
                select {{ capture_key_from_filename('file') }} as capture_key
                from glob('{{ root }}/fpl/{{ endpoint }}/**/payload.json')
            )
            select 'chosen' as kind, capture_key, run_id, null::bigint as n
            from ({{ latest_live_run_captures(admitted, endpoint, 'present') }})
            union all
            select 'gap', null, run_id, captures_without_bytes
            from ({{ latest_live_run_missing_bytes(admitted, endpoint, 'present') }})
        {%- endset -%}
        {%- set candidates = run_query(candidates_sql) -%}

        {%- set chosen = [] -%}
        {%- set gap = {'run_id': none, 'n': 0} -%}
        {%- for row in candidates.rows -%}
            {%- if row['kind'] == 'chosen' -%}
                {%- do chosen.append(row) -%}
            {%- else -%}
                {%- do gap.update({'run_id': row['run_id'], 'n': row['n']}) -%}
            {%- endif -%}
        {%- endfor -%}

        {%- set captures -%}
            {%- if chosen -%}
            (select * from (values
                {%- for row in chosen %}
                ('{{ row["capture_key"] }}', '{{ row["run_id"] }}'){{ "," if not loop.last }}
                {%- endfor %}
            ) as c(capture_key, run_id))
            {%- else -%}
            (select null::varchar as capture_key, null::varchar as run_id where false)
            {%- endif -%}
        {%- endset -%}

        {%- set objects -%}
            {%- if chosen -%}
            (select {{ capture_key_from_filename() }} as capture_key, json
             from read_json_objects(
                 [
                 {%- for row in chosen -%}
                     {#- A live key is `raw/...`, rooted at the tree raw_root points to. -#}
                     '{{ root }}/{{ row["capture_key"][4:] }}'{{ ", " if not loop.last }}
                 {%- endfor -%}
                 ],
                 format = 'unstructured',
                 filename = true
             ))
            {%- else -%}
            (select null::varchar as capture_key, null::json as json where false)
            {%- endif -%}
        {%- endset -%}

        {%- set part -%}
            select
                *,
                {{ "'" ~ gap.run_id ~ "'" if gap.run_id else 'null' }}::varchar as latest_run_id,
                {{ gap.n }}::bigint as latest_run_missing_bytes
            from ({{ consumed_key_presence(node.name, specs, captures, objects) }})
        {%- endset -%}
        {%- do parts.append(part) -%}
    {%- endif -%}
{%- endfor -%}
{%- endif -%}

{%- if parts %}
{{ parts | join('\nunion all\n') }}
{%- else %}
select
    null::varchar as source_name,
    null::varchar as column_name,
    null::varchar as run_id,
    0::bigint     as captures,
    0::bigint     as records,
    0::bigint     as missing,
    null::varchar as latest_run_id,
    0::bigint     as latest_run_missing_bytes
where false
{%- endif %}
