{#
  Served diff (#102). Run by .github/workflows/served_diff.yml as two
  run-operations:

  - served_diff_export, under `dev` after a `dbt build`, writes the nine served
    tables to OUT_DIR as parquet, plus build.json: the build's wall-clock
    seconds and the newest run_id its staging read. It publishes nothing.
  - served_diff, under the `served_diff` target, loads two exported
    directories into that target's DuckDB as schemas served_before and
    served_after, so both sides are visible in one connection. It then
    compares each table per season with audit_helper. The markdown report goes
    to stdout. It raises, and the command exits 1, on any difference, a missing
    table, or two builds that read different newest run_ids (inconclusive).

  The tables compared are every table either side exported, plus every table
  listed below, not the list alone. The diff job runs main's copy of this
  macro, so a table new on head is one main's list does not name; run
  38184504573 skipped one that way and reported "identical" (#154). A table on
  one side only is compared against an empty table of the same columns, so
  each of its rows is reported as only after (new on head) or only before
  (gone from head). A table not listed here is ordered by all its columns.

  audit_helper compares with set EXCEPT, which cannot see a change in how often
  an identical row repeats. Each season's row counts are therefore compared as
  well. Every served table has a unique key, so a repeated row is itself a
  defect.
#}

{% macro served_diff_tables() %}
  {# Each served table's key, for compare_all_columns' per-column breakdown. #}
  {{ return({
    'fct_player_fixture': ['season', 'fpl_id', 'fixture_id'],
    'fct_player_gameweek': ['season', 'fpl_id', 'gameweek'],
    'dim_team': ['season', 'team_fpl_id'],
    'dim_player': ['season', 'fpl_id'],
    'dim_fixture': ['season', 'fixture_id'],
    'dim_player_status_history': ['season', 'fpl_id', 'valid_from'],
    'fct_player_market_snapshot': ['season', 'fpl_id', 'capture_key'],
    'dim_fixture_schedule_history': ['season', 'fixture_id', 'valid_from'],
    'dim_gameweek': ['season', 'gameweek'],
    'fct_manager_pick': ['season', 'entry_id', 'gameweek', 'slot'],
    'fct_manager_gameweek': ['season', 'entry_id', 'gameweek'],
  }) }}
{% endmacro %}

{% macro served_diff_export(out_dir, seconds) %}
  {% set staging = ['stg_player_fixture', 'stg_player', 'stg_team', 'stg_position',
                    'stg_gameweek', 'stg_fixture', 'stg_gameweek_status'] %}
  {% for table in served_diff_tables() %}
    {% do run_query("copy main." ~ table ~ " to '" ~ out_dir ~ "/" ~ table ~ ".parquet' (format parquet)") %}
  {% endfor %}
  {% set newest %}
    select max(run_id) from (
      {% for model in staging %}
        select max(run_id) as run_id from main.{{ model }}{% if not loop.last %} union all{% endif %}
      {% endfor %}
    )
  {% endset %}
  {% do run_query(
    "copy (select " ~ (seconds | int) ~ " as seconds, (" ~ newest ~ ") as newest_run_id) to '"
    ~ out_dir ~ "/build.json' (format json)"
  ) %}
  {{ print("exported " ~ (served_diff_tables() | length) ~ " served tables to " ~ out_dir) }}
{% endmacro %}

{% macro served_diff(before, after, shown_rows=20) %}
  {% set out = [] %}
  {% set meta = run_query(
    "select b.seconds, b.newest_run_id, a.seconds, a.newest_run_id "
    ~ "from read_json('" ~ before ~ "/build.json') b, read_json('" ~ after ~ "/build.json') a"
  ).rows[0] %}
  {% do out.extend([
    '### Served diff', '',
    '| | before | after |', '|---|---|---|',
    '| build seconds | ' ~ meta[0] ~ ' | ' ~ meta[2] ~ ' |',
    '| newest run_id | `' ~ meta[1] ~ '` | `' ~ meta[3] ~ '` |', '',
  ]) %}

  {% if meta[1] != meta[3] %}
    {% do out.append('**Inconclusive:** the two builds read different newest run_ids, '
                     ~ 'so an ingest run landed between them. Re-dispatch.') %}
    {{ print(out | join('\n')) }}
    {% do exceptions.raise_compiler_error('served diff inconclusive: newest run_ids differ') %}
  {% endif %}

  {% do run_query('create schema if not exists served_before; create schema if not exists served_after') %}

  {% set failures = [] %}
  {% set table_rows = ['| table | season | before rows | after rows | only before | only after |',
                       '|---|---|---|---|---|---|'] %}
  {% set details = [] %}

  {% set listed = served_diff_tables() %}
  {% set exported = run_query(
    "select parse_filename(file, true) from glob('" ~ before ~ "/*.parquet') "
    ~ "union select parse_filename(file, true) from glob('" ~ after ~ "/*.parquet') order by 1"
  ).columns[0].values() %}
  {% set tables = ((listed.keys() | list) + (exported | list)) | unique | list %}

  {% for table in tables %}
    {% set present = run_query(
      "select (select count(*) from glob('" ~ before ~ "/" ~ table ~ ".parquet')), "
      ~ "(select count(*) from glob('" ~ after ~ "/" ~ table ~ ".parquet'))"
    ).rows[0] %}
    {% set one_sided = (present[0] == 0) != (present[1] == 0) %}
    {% if present[0] == 0 and present[1] == 0 %}
      {% do failures.append(table) %}
      {% do out.append('**Missing:** `' ~ table ~ '` is absent from both sides.') %}
    {% else %}

    {% set sides = [('served_before', before, present[0]), ('served_after', after, present[1])] %}
    {% for side, dir, exists in sides if exists %}
      {% do run_query('create or replace table ' ~ side ~ '.' ~ table
                      ~ " as select * from read_parquet('" ~ dir ~ '/' ~ table ~ ".parquet')") %}
    {% endfor %}
    {% if one_sided %}
      {# A difference even with no rows: the table set itself changed. #}
      {% do failures.append(table) %}
      {% set absent = 'served_before' if present[0] == 0 else 'served_after' %}
      {% set source = 'served_after' if present[0] == 0 else 'served_before' %}
      {% do run_query('create or replace table ' ~ absent ~ '.' ~ table
                      ~ ' as select * from ' ~ source ~ '.' ~ table ~ ' limit 0') %}
      {% do out.append(('**New on head:** `' ~ table ~ '` is absent from before; each of its rows is only after.')
                       if present[0] == 0 else
                       ('**Gone from head:** `' ~ table ~ '` is absent from after; each of its rows is only before.')) %}
    {% endif %}
    {% if table in listed %}
      {% set key = listed[table] %}
    {% else %}
      {% set key = run_query(
        "select column_name from duckdb_columns() where schema_name = 'served_after' "
        ~ "and table_name = '" ~ table ~ "' order by column_index"
      ).columns[0].values() | list %}
    {% endif %}

    {% set shape = run_query(
      "select count(*) from ((select column_name, data_type, column_index from duckdb_columns() "
      ~ "where schema_name = 'served_before' and table_name = '" ~ table ~ "') "
      ~ "except all (select column_name, data_type, column_index from duckdb_columns() "
      ~ "where schema_name = 'served_after' and table_name = '" ~ table ~ "')) d"
    ).rows[0][0] %}
    {% set shape_back = run_query(
      "select count(*) from ((select column_name, data_type, column_index from duckdb_columns() "
      ~ "where schema_name = 'served_after' and table_name = '" ~ table ~ "') "
      ~ "except all (select column_name, data_type, column_index from duckdb_columns() "
      ~ "where schema_name = 'served_before' and table_name = '" ~ table ~ "')) d"
    ).rows[0][0] %}
    {% if shape or shape_back %}
      {% do failures.append(table) %}
      {% do out.append('**Columns differ:** `' ~ table ~ '` has a different column list or types; rows not compared.') %}
    {% else %}

    {% set seasons = run_query(
      'select season from served_before.' ~ table ~ ' union select season from served_after.' ~ table ~ ' order by 1'
    ).columns[0].values() %}
    {% set table_differs = [] %}
    {% for season in seasons %}
      {% set a_query = 'select * from served_before.' ~ table ~ " where season = '" ~ season ~ "'" %}
      {% set b_query = 'select * from served_after.' ~ table ~ " where season = '" ~ season ~ "'" %}
      {% set counts = run_query('select (select count(*) from (' ~ a_query ~ ')), (select count(*) from (' ~ b_query ~ '))').rows[0] %}
      {% set summary = run_query(audit_helper.compare_queries(a_query, b_query, summarize=true)) %}
      {% set only = {'before': 0, 'after': 0} %}
      {% for r in summary.rows %}
        {% if r['in_a'] and not r['in_b'] %}{% do only.update({'before': r['count']}) %}{% endif %}
        {% if r['in_b'] and not r['in_a'] %}{% do only.update({'after': r['count']}) %}{% endif %}
      {% endfor %}
      {% do table_rows.append('| ' ~ table ~ ' | ' ~ season ~ ' | ' ~ counts[0] ~ ' | ' ~ counts[1]
                              ~ ' | ' ~ only['before'] ~ ' | ' ~ only['after'] ~ ' |') %}
      {% if only['before'] or only['after'] or counts[0] != counts[1] %}
        {% do table_differs.append(season) %}
        {% do details.extend(['', '#### `' ~ table ~ '` ' ~ season]) %}
        {% if counts[0] != counts[1] and not (only['before'] or only['after']) %}
          {% do details.append('- row counts differ with no distinct row on one side only: a row repeats a different number of times') %}
        {% endif %}
        {% set rows = run_query(audit_helper.compare_queries(a_query, b_query, primary_key=key | join(', '),
                                                              summarize=false, limit=shown_rows)) %}
        {% for r in rows.rows %}
          {% set values = [] %}
          {% for c in rows.column_names if c not in ('in_a', 'in_b') %}{% do values.append(r[c] ~ '') %}{% endfor %}
          {% do details.append('- ' ~ ('only before' if r['in_a'] else 'only after') ~ ': `(' ~ values | join(', ') ~ ')`') %}
        {% endfor %}
        {% if (only['before'] + only['after']) > shown_rows %}
          {% do details.append('- … ' ~ (only['before'] + only['after'] - shown_rows) ~ ' more') %}
        {% endif %}
      {% endif %}
    {% endfor %}

    {% if table_differs and one_sided %}
      {% do failures.append(table) %}
      {% do details.extend(['', '`' ~ table ~ '` is on one side only, so no key matches across sides.']) %}
    {% elif table_differs %}
      {% do failures.append(table) %}
      {# Which columns the differences are in, matched on the table's key. #}
      {% set columns = run_query(audit_helper.compare_all_columns(
        api.Relation.create(database=target.database, schema='served_before', identifier=table),
        api.Relation.create(database=target.database, schema='served_after', identifier=table),
        primary_key="concat_ws('|', " ~ key | join(', ') ~ ")",
        summarize=true)) %}
      {% set changed = [] %}
      {% for r in columns.rows if r['conflicting_values'] %}
        {% do changed.append(r['column_name'] | lower) %}
      {% endfor %}
      {% do details.extend(['', '`' ~ table ~ '` columns with differing values on matching keys: '
                            ~ (changed | join(', ') if changed else 'none (rows added or removed only)')]) %}
    {% endif %}
    {% endif %}{# shape #}
    {% endif %}{# present #}
  {% endfor %}

  {% do out.extend(table_rows) %}
  {% do out.extend(details) %}
  {% do out.extend(['', '**Result:** ' ~ ('differs' if failures else 'identical')]) %}
  {{ print(out | join('\n')) }}
  {% if failures %}
    {% do exceptions.raise_compiler_error('served output differs: ' ~ failures | unique | join(', ')) %}
  {% endif %}
{% endmacro %}
