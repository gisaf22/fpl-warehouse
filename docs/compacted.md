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
   (`raw/fpl/_manifests/*/<run_id>/manifest.json`) must state `extraction_date` = D. A day
   with no payload files, or with a run that has no run manifest, fails.
2. **Counts.** Listed payload files = parquet rows = distinct `filename`.
3. **Index.** The listed files' keys equal the element-summary keys of D in the index of
   D's runs (a key under `raw/fpl/element-summary/`, never the `endpoint` field, which
   ingest records as `element-summary/<fpl_id>`, #203), and each file's sha256 equals the index's `content_sha256`. A run's index is
   its finalized manifest's `captures[]` (any status but `IN_PROGRESS`) if present,
   otherwise `raw/fpl/_catalog/backfill/<run_id>.json`: `base_capture_index`'s precedence.
   A run with neither fails the day.

## Who writes

A destination under `s3://fpl-data-safari/compacted/` is written only when
`GITHUB_EVENT_NAME == schedule`; any other value, or none, is refused. Local paths are
always allowed. Only `scheduled_compaction.yml` may run the writer with a production
destination, and only on its schedule; any writer call in another workflow must pass a
literal local `--dest-root`. A test scans every workflow and fails on an `s3://` or
unresolved destination elsewhere, or on any trigger but `schedule` for that workflow
(#198 D3, #205 G4).

## Day selection and scheduling (#198, #205)

`scripts/compaction_step.py` runs in its own workflow, `scheduled_compaction.yml`, at
01:30 and 13:30 UTC (#78 W16). The scheduled build no longer runs it: builds read only
the compaction manifest (W4), so compaction runtime never affects a build. Runs never
overlap (`concurrency`, `cancel-in-progress: false`), and the job's `timeout-minutes` is
50, below the one-hour OIDC session.

**Config: `compaction.yml`**, the only place either value lives:

- `max_seconds_per_run`: the time budget (W16, replacing W14's day count). Queued days
  run oldest first; no new day starts once the elapsed time reaches the budget, and a
  started day always runs to completion, so a run can overrun the budget by one day.
  **Ships at 0** (#205): the step makes no S3 call, writes nothing, and records
  `days: []`. #200 sets it (W16 proposes 1,800s); the budget plus the heaviest
  dry-run day (1,084.4s for 2026-08-30, dry run 38828339698) must fit inside the
  50-minute timeout. A config without it is refused, never read as off. Rollback: set it
  back to 0.
- `ingest_job_timeout_hours`: 6, until fpl-ingest#99 sets ingest's own job timeout.

**Which days.** A day D is queued when all of these hold:

1. **Closed:** now is past D+1 00:00 UTC + the ingest job timeout, and every run manifest
   under `raw/fpl/_manifests/D/` is finalized. A day with a run still `IN_PROGRESS` past
   its grace (a killed run) stays open and is named in the summary.
2. **A candidate:** its finalized manifests record at least one element-summary object
   written. A day with none is skipped, not failed, and named in the summary (#198 O1).
3. **Uncompacted:** it has no compaction manifest.

Oldest first, while the budget lasts; days left over are named in the summary and wait
for the next run. A day that fails stays a candidate and is retried every run until
fixed; no failure state is kept, and the summary flags it each run (O1).

**What it records.** The compaction record (#205 G5), and a job summary headed
`**failed**` when any day failed. As each day finishes, the step prints
`compaction: day=<D> files=<n> seconds=<s> ok=<bool>` to its log, so a killed run still
shows the days it completed (#203 F4).

### The compaction record

`scripts/compaction_metrics.py` runs after the step with `if: always()`. It writes the
record to the job summary on every run, and on a scheduled run also to
`s3://fpl-data-safari/metrics/compaction/<run_id>.json`; a failed write fails the job.
A dispatch writes the summary only. Exactly these fields, pinned by
`scripts/tests/test_compaction_metrics.py`:

| Field | Meaning |
|---|---|
| `run_id`, `git_sha` | `GITHUB_RUN_ID`, `GITHUB_SHA` |
| `built_at` | UTC, seconds, when the record was written |
| `status` | the job result when the record was written: `success`, `failure` or `cancelled` |
| `compaction` | the W13 object: `budget_seconds` (`max_seconds_per_run`; named `n` before #205), `seconds`, `days_selected` (days queued, not all necessarily started), `days` (each `{capture_day, ok, reason, seconds, files_read, rows_written}`) and `peak_rss_mib`. If the step wrote nothing, `budget_seconds` from `compaction.yml`, `days` `[]`, the rest `null` |

Until #205 the W13 object rode in the #191 build record as `compaction`. Build records
from those runs still carry it; the #191 extraction query reads both.

### Runbook

- **The first scheduled run after #200 merges starts the backfill.** It compacts the
  oldest closed candidate days until the budget is spent, and each later run continues,
  until every closed day is compacted. Days missed during an outage are caught up the
  same way. There is no separate backfill.
- **Turning it off:** set `max_seconds_per_run: 0`. Existing compacted days stay;
  nothing is deleted.
- **A failed run alerts through GitHub's failed-run email.** The step is not
  `continue-on-error` in its own workflow, and there is no healthchecks.io check for it.
  The impact of a failed or missed run is a longer raw tail for staging to read, never
  wrong data: an uncompacted day is read from raw.
- **A day failing every run:** its reason is in each run's summary. Fix the cause in raw
  or the index (or recompact by hand). It is retried, and spends budget, until it
  succeeds.
- **A scheduled `run_id` with no record** under `metrics/compaction/` means the run was
  killed before the record step: the 50-minute timeout, a runner loss or an outage.

### Dry run (measurement for #200)

Dispatch `live-tests` from `main` with `compaction_dry_run` set to comma-separated capture
days. The step compacts those days from live raw to `.local/compacted` on the runner,
with no selection or budget and never to S3, and its compaction record goes to the job
summary only.

```sh
gh workflow run ci.yml --ref main -f compaction_dry_run=2026-09-06,2026-09-14
```

Record the per-day `seconds`, `peak_rss_mib` and the run URL on #78, then size the
budget by W16.
