{#
    The season an object belongs to, read from its own key.

    Both trees put the endpoint under a `/fpl/` segment, and the segment
    immediately before it is what distinguishes them:

        {raw_root}/fpl/element-summary/...            -> `raw`      (live)
        {history_root}/2025-26/fpl/element-summary/... -> `2025-26`  (history)

    So a season-shaped segment there means the object came from a history
    season and states its own season; anything else means the live tree, whose
    season is the `season` var. That is the same rule under every target — the
    checked-in fixture trees mirror both layouts (tests/fixtures/raw/fpl/... and
    tests/fixtures/history/{season}/fpl/...).

    Reading it from the key rather than from a per-source constant is what lets
    one source relation carry both trees. It also means adding a second history
    season is a data change, exactly as CLAUDE.md's "Season is part of the
    grain" intends.
#}
{% macro season_from_filename() %}
    case
        when regexp_matches(
                regexp_extract(filename, '([^/]+)/fpl/', 1), '^\d{4}-\d{2}$'
             )
            then regexp_extract(filename, '([^/]+)/fpl/', 1)
        else '{{ var('season') }}'
    end
{%- endmacro %}
