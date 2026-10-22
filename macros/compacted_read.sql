{#
    payload_roots()

    The trees a payload source reads, as roots its `meta.capture_glob` sits
    below: the live tree, then every ported history season. Under `fixtures`
    the checked-in trees; otherwise `raw_root` and, when set, `history_root`
    (default `dev_history_root` under `dev`, none elsewhere, #180). Returns
    {"raw": <live root>, "history": <history season glob root or none>}.
    Mirrors the globs sources.yml spells out, which cannot call a macro.
#}
{% macro payload_roots() %}
    {%- if target.name == "fixtures" -%}
        {{ return({"raw": "tests/fixtures/raw", "history": "tests/fixtures/history/*"}) }}
    {%- endif -%}
    {%- set history_root = var("history_root", var("dev_history_root") if target.name == "dev" else "") -%}
    {{ return({"raw": var("raw_root"), "history": (history_root ~ "/*") if history_root else none}) }}
{% endmacro %}


{#
    element_summary_raw_read()

    Today's all-raw read of element-summary (before #194): every payload in the
    live tree and the history seasons, in one read_json. The read the source
    renders under `staging_read_mode: raw`, for a test to compare against.
#}
{% macro element_summary_raw_read() %}
    {%- set roots = payload_roots() -%}
    {%- set glob = "fpl/element-summary/*/*/*/payload.json" -%}
    read_json(['{{ roots.raw }}/{{ glob }}'{% if roots.history %}, '{{ roots.history }}/{{ glob }}'{% endif %}], union_by_name = true, filename = true)
{%- endmacro %}


{#
    compacted_read()

    A staging pre-hook (#194, #78 W8/W10). On a model that reads
    fpl_raw.element_summary, it sets the DuckDB variable `element_summary_read`
    to the SQL the source runs through query():

        read_parquet(<compaction manifest's days>, union_by_name = true)
        union all by name read_json(<raw tail>, union_by_name = true, filename = true)
        union all by name read_json(<history seasons' glob>, ...)

    Only parts with files are included: DuckDB fails a read of zero files.

    - The manifest is `_manifest/date=<D>.json` under the compacted root
      (`compacted_root`; default `tests/fixtures/compacted` under `fixtures`,
      `dev_compacted_root` otherwise). A manifest that cannot be parsed or does
      not name its own day fails the build; so does a listed day with no
      `part.parquet` (D1). A root with no manifests reads every day from raw.
    - The raw tail is every live payload whose capture day (its key's date
      segment) is not a manifest day: unclosed days, days not yet compacted, and
      failed days whose parquet has no manifest. Derived here from one listing.
    - Not with `capture_cutoff` set or `staging_read_mode: raw`: the source then
      reads raw directly and this renders nothing.

    The variable is set on the model's own connection, where its read runs;
    nothing else can read it (DuckDB variables are per connection).
#}
{% macro compacted_read() %}
    {%- set cutoff = var("capture_cutoff", "") | string -%}
    {%- set mode = var("staging_read_mode", "") | string -%}
    {%- if execute and not cutoff and mode != "raw"
          and "source.fpl_warehouse.fpl_raw.element_summary" in model.depends_on.nodes -%}
        {%- set override = "To read every day from raw on a manual dispatch or a local run, set the dbt var staging_read_mode: raw." -%}
        {%- set croot = var("compacted_root", "tests/fixtures/compacted" if target.name == "fixtures" else var("dev_compacted_root")) | string -%}
        {%- set base = croot.rstrip("/") ~ "/fpl/element-summary" -%}

        {#- Manifests: read as text, so an unreadable one gets a clear error. -#}
        {%- set manifests = run_query("select file from glob('" ~ base ~ "/_manifest/date=*.json') order by file").columns[0].values() | list -%}
        {%- set days = [] -%}
        {%- if manifests -%}
            {%- set read = run_query(
                "select filename, try(json_extract_string(content, '$.capture_day')) as day "
                ~ "from read_text(['" ~ manifests | join("', '") ~ "']) order by filename") -%}
            {%- for row in read.rows -%}
                {%- set named = row[0].split("date=")[-1][:-5] -%}
                {%- if row[1] != named -%}
                    {{ exceptions.raise_compiler_error("compacted read: manifest " ~ row[0]
                        ~ " is unreadable or does not name its day " ~ named ~ ". " ~ override) }}
                {%- endif -%}
                {%- do days.append(named) -%}
            {%- endfor -%}
        {%- endif -%}

        {%- set parquets = [] -%}
        {%- if days -%}
            {%- set present = run_query("select file from glob('" ~ base ~ "/date=*/part.parquet')").columns[0].values() | list -%}
            {%- for day in days -%}
                {%- set path = base ~ "/date=" ~ day ~ "/part.parquet" -%}
                {%- if path not in present -%}
                    {{ exceptions.raise_compiler_error("compacted read: day " ~ day
                        ~ " is in the compaction manifest but its part.parquet is missing: "
                        ~ path ~ ". " ~ override) }}
                {%- endif -%}
                {%- do parquets.append(path) -%}
            {%- endfor -%}
        {%- endif -%}

        {%- set roots = payload_roots() -%}
        {%- set glob = "fpl/element-summary/*/*/*/payload.json" -%}
        {%- do run_query(
            "set variable element_summary_raw_tail = (select list(file order by file) from glob('"
            ~ roots.raw ~ "/" ~ glob ~ "') where not list_contains(" ~ sql_list(days)
            ~ ", string_split(file, '/')[-3]))") -%}
        {%- set tail = run_query("select coalesce(len(getvariable('element_summary_raw_tail')), 0)").columns[0].values()[0] -%}

        {%- set parts = [] -%}
        {%- if parquets -%}
            {%- do parts.append("select * from read_parquet(getvariable('element_summary_compacted'), union_by_name = true, hive_partitioning = false)") -%}
        {%- endif -%}
        {%- if tail > 0 -%}
            {%- do parts.append("select * from read_json(getvariable('element_summary_raw_tail'), union_by_name = true, filename = true)") -%}
        {%- endif -%}
        {%- if roots.history -%}
            {%- do parts.append("select * from read_json('" ~ roots.history ~ "/" ~ glob ~ "', union_by_name = true, filename = true)") -%}
        {%- endif -%}
        {%- if not parts -%}
            {{ exceptions.raise_compiler_error("compacted read: element-summary has no compacted day, raw payload or history capture to read") }}
        {%- endif %}
set variable element_summary_compacted = {{ sql_list(parquets) }};
set variable element_summary_read = '{{ parts | join(" union all by name ") | replace("'", "''") }}';
    {%- endif -%}
{% endmacro %}


{#- A list of strings as a DuckDB VARCHAR[] literal; [] when empty. -#}
{% macro sql_list(values) -%}
    {%- if values -%}['{{ values | join("', '") }}']{%- else -%}[]{%- endif -%}::varchar[]
{%- endmacro %}


{#
    entry_picks_raw_read()

    Every entry-picks payload in the live tree, in one read_json: the read the
    source renders under `staging_read_mode: raw`, for a test to compare the
    compacted read against (#216 AC16). Picks have no history-port season.
#}
{% macro entry_picks_raw_read() %}
    read_json('{{ payload_roots().raw }}/fpl/entry-picks/*/*/*/*/*/payload.json', union_by_name = true, filename = true)
{%- endmacro %}


{#
    entry_picks_compacted_read()

    A staging pre-hook (#216 D8), the entry-picks counterpart of
    compacted_read(). On a model that reads fpl_raw.entry_picks it sets the
    DuckDB variable `entry_picks_read` to the SQL the source runs through
    query():

        read_parquet(<compaction manifest's gameweeks>, union_by_name = true)
        union all by name read_json(<raw tail>, union_by_name = true, filename = true)

    - A compacted gameweek has `_manifest/season=<S>/gameweek=<G>.json` under
      `<compacted_root>/fpl/entry-picks`, written by
      scripts/compact_entry_picks.py. A manifest that cannot be parsed or does
      not name its own season and gameweek fails the build; so does a listed
      gameweek with no `part.parquet`. A root with no manifests reads raw.
    - The raw tail is every payload whose (season, gameweek) has no manifest:
      unsettled gameweeks and settled ones not yet compacted.
    - Not with `staging_read_mode: raw`: the source then reads raw directly.
    - Each part is typed separately, through entry_picks_typed(), before the
      union: types are inferred per read, so a gameweek whose `active_chip` or
      `automatic_subs` are all empty reads them as JSON where another reads
      VARCHAR or STRUCT, and DuckDB cannot union the two.
#}
{% macro entry_picks_compacted_read() %}
    {%- set mode = var("staging_read_mode", "") | string -%}
    {%- if execute and mode != "raw"
          and "source.fpl_warehouse.fpl_raw.entry_picks" in model.depends_on.nodes -%}
        {%- set croot = var("compacted_root", "tests/fixtures/compacted" if target.name == "fixtures" else var("dev_compacted_root")) | string -%}
        {%- set base = croot.rstrip("/") ~ "/fpl/entry-picks" -%}

        {%- set manifests = run_query("select file from glob('" ~ base ~ "/_manifest/season=*/gameweek=*.json') order by file").columns[0].values() | list -%}
        {%- set parts_named = [] -%}
        {%- if manifests -%}
            {%- set read = run_query(
                "select filename, try(json_extract_string(content, '$.season')) as season, "
                ~ "try(json_extract(content, '$.gameweek')::integer) as gameweek "
                ~ "from read_text(['" ~ manifests | join("', '") ~ "']) order by filename") -%}
            {%- for row in read.rows -%}
                {%- set season = row[0].split("season=")[-1].split("/")[0] -%}
                {%- set gameweek = row[0].split("gameweek=")[-1][:-5] -%}
                {%- if row[1] != season or (row[2] | string) != gameweek -%}
                    {{ exceptions.raise_compiler_error("compacted read: manifest " ~ row[0]
                        ~ " is unreadable or does not name its season " ~ season ~ " and gameweek " ~ gameweek
                        ~ ". To read every payload from raw on a manual dispatch or a local run, set the dbt var staging_read_mode: raw.") }}
                {%- endif -%}
                {%- do parts_named.append(season ~ "/" ~ gameweek) -%}
            {%- endfor -%}
        {%- endif -%}

        {%- set parquets = [] -%}
        {%- if parts_named -%}
            {%- set present = run_query("select file from glob('" ~ base ~ "/season=*/gameweek=*/part.parquet')").columns[0].values() | list -%}
            {%- for named in parts_named -%}
                {%- set path = base ~ "/season=" ~ named.split("/")[0] ~ "/gameweek=" ~ named.split("/")[1] ~ "/part.parquet" -%}
                {%- if path not in present -%}
                    {{ exceptions.raise_compiler_error("compacted read: entry-picks " ~ named
                        ~ " is in the compaction manifest but its part.parquet is missing: " ~ path) }}
                {%- endif -%}
                {%- do parquets.append(path) -%}
            {%- endfor -%}
        {%- endif -%}

        {#- .../entry-picks/<season>/<gw>/<entry>/<day>/<run_id>/payload.json -#}
        {%- do run_query(
            "set variable entry_picks_raw_tail = (select list(file order by file) from glob('"
            ~ payload_roots().raw ~ "/fpl/entry-picks/*/*/*/*/*/payload.json') where not list_contains("
            ~ sql_list(parts_named) ~ ", string_split(file, '/')[-6] || '/' || string_split(file, '/')[-5]))") -%}
        {%- set tail = run_query("select coalesce(len(getvariable('entry_picks_raw_tail')), 0)").columns[0].values()[0] -%}

        {%- set parts = [] -%}
        {%- for path in parquets -%}
            {%- do parts.append(entry_picks_typed("read_parquet('" ~ path ~ "', hive_partitioning = false)")) -%}
        {%- endfor -%}
        {%- if tail > 0 -%}
            {%- do parts.append(entry_picks_typed("read_json(getvariable('entry_picks_raw_tail'), union_by_name = true, filename = true)")) -%}
        {%- endif -%}
        {%- if not parts -%}
            {{ exceptions.raise_compiler_error("compacted read: entry-picks has no compacted gameweek or raw payload to read") }}
        {%- endif %}
set variable entry_picks_read = '{{ parts | join(" union all ") | replace("'", "''") }}';
    {%- endif -%}
{% endmacro %}


{#
    entry_picks_typed(read)

    `read` (a relation over entry-picks payloads, with `filename`) as one row
    per payload with exactly the declared fields, every leaf VARCHAR, through
    json_transform. The shape is built from the entry_picks source's declared
    columns (#114, #115): a root column with no record_path is a leaf, its
    fields declared at '$.<name>[*]' make it a list of structs, and at
    '$.<name>' a struct (#216 AC22). Staging casts every leaf. An undeclared
    field is not in the shape, so it cannot be read.
#}
{% macro entry_picks_typed(read) -%}
    {%- set node = graph.sources["source.fpl_warehouse.fpl_raw.entry_picks"] -%}
    {%- set roots = [] -%}
    {%- set children = {} -%}
    {%- for column in node.columns.values() -%}
        {%- set path = (column.meta or {}).get("record_path") -%}
        {%- if not path -%}
            {%- do roots.append(column.name) -%}
        {%- else -%}
            {%- do children.setdefault(column.name.split(".")[0], []).append(column.name.split(".")[-1]) -%}
        {%- endif -%}
    {%- endfor -%}
    {%- set shape = {} -%}
    {%- for root in roots -%}
        {%- set fields = children.get(root) -%}
        {%- set path = (node.columns[root ~ "." ~ fields[0]].meta or {}).get("record_path") if fields else none -%}
        {%- set leaves = {} -%}
        {%- for field in fields or [] -%}{%- do leaves.update({field: "VARCHAR"}) -%}{%- endfor -%}
        {%- if not fields -%}
            {%- do shape.update({root: "VARCHAR"}) -%}
        {%- elif path.endswith("[*]") -%}
            {%- do shape.update({root: [leaves]}) -%}
        {%- else -%}
            {%- do shape.update({root: leaves}) -%}
        {%- endif -%}
    {%- endfor -%}
    select filename, typed.*
    from (
        select filename, json_transform(to_json(struct_pack(
            {%- for root in roots %}
            "{{ root }}" := "{{ root }}"{{ "," if not loop.last }}
            {%- endfor %}
        )), '{{ tojson(shape) }}') as typed
        from {{ read }}
    )
{%- endmacro %}
