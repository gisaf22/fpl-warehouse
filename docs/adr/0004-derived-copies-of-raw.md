# 0004. Derived copies of raw: raw stays authoritative, copies are rebuildable

- Status: accepted
- Date: 2026-10-15
- Decided on: #78 (W2, W8, W9, W10, W11), built in #193

## Context

Staging reads every element-summary payload in the raw tree on every build, one small
JSON object per player per run. The read grows with every capture and dominates the
build's time and memory (CLAUDE.md, "Build cost"; #78, #183). One parquet file per
capture day holds the same rows in a form that is far cheaper to read.

That parquet is a second copy of data that already exists in raw. ADR 0003 makes raw
captures immutable, append-only and the source the warehouse can always be rebuilt from.
A copy must not weaken any of that.

## Decision

- **Raw stays immutable and authoritative.** A derived copy never replaces, moves or
  deletes a raw capture. Anything a copy holds can be rebuilt from raw.
- **A derived copy is owned by the warehouse.** It lives under its own prefix,
  `s3://fpl-data-safari/compacted/`, mirroring `raw/fpl/<endpoint>/`. Only the
  warehouse writes it, and only from a scheduled run.
- **A copy is the source read, unchanged.** The element-summary copy for capture day D is
  `select * from read_json(<D's payload files>, union_by_name = true, filename = true)`,
  with `filename` the original URI and D only in the path (`date=D/part.parquet`). No
  column is added. Its schema is whatever that read returns: an internal contract, not a
  served one (`docs/compacted.md`).
- **A copy is reconciled before anything may read it.** A day's copy is referenced only by
  its compaction manifest, written last and only after its rows match the day's listed
  payload files, the files match the run index (captures[] or the backfill catalog) by key
  and sha256, and every run's manifest states extraction_date D. A day that fails has no
  manifest and stays in raw.
- **A copy is rebuildable.** Recompacting a day overwrites its parquet. The warehouse
  role has no delete permission on the prefix; removing a copy is a manual step.
- **Ported history captures are not compacted.** They stay under `history/` and are read
  as before.

## Rejected

| Option | Why rejected |
|---|---|
| A parquet schema of its own (payload, captured_at, source key; W2) | A second schema to keep in step with staging's read. Reading the copy the same way as raw keeps `capture_key_from_filename`, `declared_records` and every model unchanged (W8). |
| Capture metadata columns in the copy (run_id, received_at, extraction_date) | They come from the capture index, so storing them twice gives two places that could disagree (W8). |
| Compacting in dbt | Compaction must run before staging reads the copy, and needs S3 writes; a dbt model writes neither (W11). |
| Deleting or rewriting raw after compaction | Breaks ADR 0003's guarantee that raw rebuilds everything. |
| Delete permission on the prefix | Overwriting a fixed `part.parquet` makes recompaction idempotent without it (W9). |

## Consequences

- Turning compaction off means pointing staging back at raw and, if wanted, deleting the
  prefix by hand. Nothing in raw changes either way.
- The copy can lag raw: a day is compacted only once closed (#198). Staging reads
  compacted days plus the raw tail (#194).
- Per-day type inference can widen differently from inference across all files. The
  writer's fixture tests and the served diff in #194 cover it.
