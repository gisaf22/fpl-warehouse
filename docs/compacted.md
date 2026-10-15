# Compacted captures — internal contract

**Internal contract.** Nothing outside this repo reads `compacted/`, and no consumer may.
The parquet schema and manifest format below are owned by the warehouse; a change to
either is a maintainer's gate (Fred), not a served-contract change. Why it exists:
ADR 0004. Writer: `scripts/compact_element_summary.py` (#193). Day selection and wiring:
#198. Staging's read of it: #194.

## Layout

```
s3://fpl-data-safari/compacted/fpl/element-summary/date=<YYYY-MM-DD>/part.parquet
s3://fpl-data-safari/compacted/fpl/element-summary/_manifest/date=<YYYY-MM-DD>.json
```

One parquet and one manifest per capture day, both at fixed names. The capture day is the
date segment of the raw key (`raw/fpl/element-summary/<fpl_id>/<day>/<run_id>/payload.json`),
the run's start date in UTC. The leading `_` keeps the manifests out of a `date=*` glob.

## Parquet schema

Exactly `select * from read_json(<the day's payload files>, union_by_name = true,
filename = true)`:

- the payload's columns as DuckDB infers them for that day: `fixtures`, `history`,
  `history_past`, nested as in the JSON;
- `filename`: the payload file's full original URI, unchanged
  (`s3://fpl-data-safari/raw/fpl/element-summary/...`).

No other column. The day is in the path only; read with `hive_partitioning = false`, or
the reader adds a `date` column. Inferred types can differ by day (an all-integer field on
one day, decimals on another); read several days with `union_by_name = true`. An upstream
field change is not a contract change: the schema follows the source.

## Manifest

A manifest exists only for a day that passed every check, and is written after its parquet.
A day without one is not compacted, whatever parquet exists for it. Exactly these fields
(`MANIFEST_FIELDS`; a test fails on a missing or extra one):

| Field | Type | Meaning |
|---|---|---|
| `capture_day` | string | `YYYY-MM-DD`, the day compacted |
| `payload_files` | int | payload files listed under raw for that day |
| `parquet_rows` | int | rows in `part.parquet`, read back after the write |
| `distinct_filenames` | int | distinct `filename` values in `part.parquet` |
| `run_ids` | list of string | the ingest runs the day's captures come from, sorted |
| `compacted_at` | string | UTC, seconds, when the manifest was written |
| `git_sha` | string | the commit the writer ran from |

`payload_files = parquet_rows = distinct_filenames` in every manifest.

## Checks, per day

A failed check fails that day only: no manifest, the parquet stays unreferenced and is
overwritten next time, and the other days go on.

1. **Capture day = extraction_date.** Each file's run manifest
   (`raw/fpl/_manifests/*/<run_id>/manifest.json`) must state `extraction_date` = D.
2. **Counts.** Listed payload files = parquet rows = distinct `filename`.
3. **Index.** The listed files' keys equal the element-summary keys of D in the index of
   D's runs, and each file's sha256 equals the index's `content_sha256`. A run's index is
   its finalized manifest's `captures[]` (any status but `IN_PROGRESS`) if present,
   otherwise `raw/fpl/_catalog/backfill/<run_id>.json`: `base_capture_index`'s precedence.
   A run with neither fails the day.

## Who writes

A destination under `s3://fpl-data-safari/compacted/` is written only when
`GITHUB_EVENT_NAME == schedule`; any other value, or none, is refused. Local paths are
always allowed. No step of `ci.yml` or `served_diff.yml` runs the writer.
