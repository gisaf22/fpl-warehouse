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

## Staging's read (#194)

Staging reads element-summary as the compacted days plus the rest from raw (#78 W8,
W10). The `compacted_read` pre-hook (`macros/compacted_read.sql`) runs on
`stg_player_history_capture`, the one model that reads the source. It sets the read the
source runs, `query(getvariable('element_summary_read'))`:

```
read_parquet(<each manifest day's part.parquet>, union_by_name = true, hive_partitioning = false)
union all by name read_json(<raw tail>, union_by_name = true, filename = true)
union all by name read_json(<history seasons' glob>, union_by_name = true, filename = true)
```

- **Which days come from parquet:** exactly the days with a manifest. A parquet with no
  manifest (a failed day) is never read.
- **The raw tail:** every live payload whose capture day has no manifest: unclosed days,
  days not yet compacted, failed days and gaps. It is derived from one listing of the raw
  tree each build, never from hard-coded dates. The 2025-26 history-port captures are
  never compacted and are read as before.
- **Fails, never falls back (D1).** A manifest that cannot be read, or that does not
  name its own day, fails the build naming the file. So does a manifest day with no
  `part.parquet`. A listing that S3 refuses fails with DuckDB's error. A compacted root
  with no manifests at all is a fresh start: every day is read from raw.
- **No capture is read twice.** `stg_player_history_capture.capture_key` is unique (B2).
  A filename in both a parquet and the raw tail fails the build.
- **Types follow each read.** A day's parquet keeps the types inferred over that day.
  So the raw `history` struct in `stg_player_history_capture` can be wider than one
  all-raw read would give (`bps` `17.0`, not `17`). `stg_player_fixture` casts every
  field, so nothing downstream sees it (#78 W8's residual risk).
- **Roots:** `compacted_root`. It defaults to `dev_compacted_root`
  (`s3://fpl-data-safari/compacted`), or `tests/fixtures/compacted` under `fixtures`.
- **Not used with `capture_cutoff`:** a cutoff build reads raw and history only.
- **Fixture:** `tests/fixtures/compacted` holds trimmed production objects, built by
  `tests/fixtures/build_compacted_fixture.py`. Compacted days are 2026-08-29 and
  2026-09-02. 2026-08-31 has a parquet but no manifest.

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
record to the job summary on every run, and on a scheduled run with a budget above 0
also to `s3://fpl-data-safari/metrics/compaction/<run_id>.json`; a failed write fails the
job. A dispatch, or a run with the budget at 0, writes the summary only, so disabled
compaction writes nothing to production. Exactly these fields, pinned by
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
- **Reading every day from raw (emergency, #194 D1, an R6 exception).** Use it when a
  build fails on the compacted read and `served/` must still be rebuilt before the
  cause is fixed. That means a manifest is unreadable, a listed day's parquet is
  missing, or `compacted/` cannot be listed. The repository owner dispatches
  `gh workflow run scheduled_build.yml -f staging_read_mode=raw`. The run is flagged
  in its job summary and an annotation; any other dispatcher fails at the check step.
  dbt refuses `staging_read_mode: raw` on a schedule, push or pull_request event and
  allows it on `workflow_dispatch` or a local run (`GITHUB_EVENT_NAME` unset). The
  read costs what it did before #194 (the full raw tree). Then fix the cause: rewrite
  the day's parquet and manifest by recompacting it, or delete its manifest so the day
  falls back to the raw tail.
- **A day failing every run:** its reason is in each run's summary. Fix the cause in raw
  or the index (or recompact by hand). It is retried, and spends budget, until it
  succeeds.
- **A scheduled `run_id` with no record** under `metrics/compaction/`, while the budget is
  above 0, means the run was killed before the record step: the 50-minute timeout, a
  runner loss or an outage.

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

## Entry-picks (#216 D8)

Settled entry-picks gameweeks are compacted too, by `scripts/compact_entry_picks.py`, in
the same scheduled workflow, after the element-summary step.

```
s3://fpl-data-safari/compacted/fpl/entry-picks/season=<S>/gameweek=<G>/part.parquet
s3://fpl-data-safari/compacted/fpl/entry-picks/_manifest/season=<S>/gameweek=<G>.json
```

- **Which gameweeks:** every gameweek with a picks settlement marker
  (`raw/fpl/_settlement/entry-picks/<gw>/marker.json`) and no compaction manifest. The
  marker's season is the one season of its run's indexed entry-picks captures for that
  gameweek (#216 D14). No time budget: a gameweek is about 2,000 small files.
- **Never rewritten:** a gameweek with a manifest is skipped. Its picks cannot change once
  settled.
- **Parquet:** `select * from read_json(<the gameweek's payload files>, union_by_name =
  true, filename = true)`, as for element-summary. Invalid captures under `_invalid/` are
  not payloads and are never included.
- **Checks:** payload files = parquet rows = distinct `filename`, and the files equal the
  index keys of their runs, sha256 matching. The manifest is written last. A failed
  gameweek fails that gameweek only, and the run exits 1.
- **Manifest fields:** `season`, `gameweek`, `payload_files`, `parquet_rows`,
  `distinct_filenames`, `run_ids`, `compacted_at`, `git_sha`.
- **Staging's read:** the `entry_picks_compacted_read` pre-hook reads each compacted
  gameweek's parquet and the raw tail (every payload whose season and gameweek have no
  manifest). Types are inferred per read, so a gameweek whose `active_chip` or
  `automatic_subs` are all empty reads them as JSON where another reads VARCHAR or STRUCT.
  Each part is therefore typed separately from the source's declared fields
  (`entry_picks_typed`) before the union. `staging_read_mode: raw` reads every payload from
  raw.
- **Who writes:** the element-summary writer's gate. A destination under
  `s3://fpl-data-safari/compacted/` is written only when `GITHUB_EVENT_NAME == schedule`,
  and the workflow scan covers this writer too (`WRITER_SCRIPTS`).
- **Fixture:** `tests/fixtures/compacted/fpl/entry-picks` holds 2026-27 gameweeks 1 and 3,
  built by `tests/fixtures/build_compacted_picks_fixture.py`; gameweeks 2, 4 and 5 are the
  raw tail.
