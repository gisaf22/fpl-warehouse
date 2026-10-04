{#
    The capture index's key for an object, from the filename DuckDB reports
    for it (#95). The one place a payload's filename becomes an index key.

    The key is the object's path from its tree's root, which is what ingest's
    manifests and backfill catalog record:

        raw/fpl/{endpoint}/.../payload.json                (live tree)
        history/{season}/fpl/{endpoint}/.../payload.json   (a ported season)

    Whatever precedes that — `s3://fpl-data-safari/`, a local `raw_root`, or
    the fixture trees under tests/fixtures — is dropped. The segment before
    `/fpl/` decides which tree: a season-shaped segment is a history season,
    anything else the live tree.

    Staging calls it with no argument, on the source's own `filename` column,
    and joins the result to int_admitted_capture (#104). It is the only place
    a model reads an object's path: CI's validate job fails on `filename`
    anywhere else in models/ or tests/ (#88 E8).
#}
{% macro capture_key_from_filename(column='filename') %}
    case
        when regexp_matches(
                regexp_extract({{ column }}, '([^/]+)/fpl/', 1), '^\d{4}-\d{2}$'
             )
            then 'history/' || regexp_extract({{ column }}, '([^/]+/fpl/.*)$', 1)
        else 'raw/' || regexp_extract({{ column }}, '[^/]+/(fpl/.*)$', 1)
    end
{%- endmacro %}
