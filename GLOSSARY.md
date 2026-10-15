# Glossary

One definition per term. A term is added here before an issue, PR or check cites it
(`CLAUDE.md`, opening). Where a decision record holds the full rule, the entry points to it.

## Captures and time

- **capture**: one payload fpl-ingest fetched from one FPL endpoint in one run, with its
  entry in the capture index. Identified by `capture_key`. Captures are immutable (ADR 0003).
- **admitted capture**: a capture the warehouse may read: from a finalized production run,
  usable and with a season (`int_capture_admission`, #97). Staging holds admitted captures
  only (#104).
- **observed_at / received_at**: when a capture was received. `observed_at` is the
  warehouse's name for fpl-ingest's `received_at`, read from the capture index (#104). It is
  not a field in FPL's data.
  - **Live captures:** taken when the HTTP response arrives, written with `isoformat()`,
    stored to the **microsecond** (PR #147).
  - **History port captures (2025-26):** the run's start time, in **whole seconds**.
- **moment / cutoff**: the time an as-of lookup is made at. The caller supplies it; it is
  not wired to the gameweek deadline (#142 P4). A deadline is one common cutoff.
- **as-of**: the latest capture strictly before the moment. A capture exactly at the moment
  is excluded (ADR 0002).
- **max_age**: an optional limit on an as-of lookup. The usable window is
  `[moment − max_age, moment)`. A latest capture older than that returns NULL; there is no
  fallback to an older one (#142 P3).
- **tie**: two captures of the same player claim the same `observed_at`. A tie is a defect:
  as-of needs unique times to be deterministic, so a tie on `(season, fpl_id, observed_at)`
  fails the build (#142 AC5).
- **run**: one execution of fpl-ingest, identified by `run_id` (e.g.
  `20260920T190000Z-aaaaaa`), with one run manifest at
  `raw/fpl/_manifests/<extraction_date>/<run_id>/manifest.json`. A run is **finalized**
  when its manifest's status is anything but `IN_PROGRESS` (`stg_run`). A run holds many
  captures.
- **capture day**: the date segment of a raw capture's key
  (`raw/fpl/<endpoint>/.../<capture day>/<run_id>/payload.json`), the run's start date in
  UTC. A run that spans midnight keeps its start date. It equals the run manifest's
  `extraction_date`, which the compaction writer checks per file (#78 W10, W11). It is the
  `date=` partition value under `compacted/` (`docs/compacted.md`).
- **closed day**: a capture day that may be compacted. Day D is closed once
  `D+1 00:00 UTC` plus the ingest job timeout has passed and every run manifest under
  `raw/fpl/_manifests/D/` is finalized (#198 D1). A day with a run still `IN_PROGRESS`
  stays open.
- **compacted capture**: a capture read from a capture day's parquet under `compacted/`
  instead of from its raw payload file. The row is unchanged and keeps the raw file's
  `filename`. A day's captures count as compacted only once its compaction manifest exists
  (ADR 0004, `docs/compacted.md`).
- **repeat**: the same record appearing more than once, for example in two runs. Staging
  resolves a repeat by `run_id`, which breaks an `observed_at` tie in capture order (#104).
  A repeat is expected; a tie is not.
- **capture clock**: per season, the newest staged `bootstrap-static` capture's `observed_at`.
  Staged means the capture has rows in `stg_gameweek`, so an admitted capture whose payload
  did not stage does not move it (#163 S12, S14c). A gameweek has **passed** when its
  `deadline_time` is at or before the capture clock. It stands in for `now()` so that a
  rebuild from the same captures gives the same rows (#163 S10).

## State and outcome

- **pre-deadline state**: what was observable before a deadline: a player's status, price
  and ownership as of that deadline (`dim_player_status_history`, `fct_player_market_snapshot`),
  and the fixture schedule as of that deadline (slice 1c).
- **pre-deadline freshness**: for a passed gameweek, how old the newest staged
  `bootstrap-static` capture strictly before its deadline was: `last_capture_before_deadline_at`
  and `state_age_seconds` on `dim_gameweek` (#169). NULL when the gameweek has not passed by
  the capture clock, or when no staged capture exists before the deadline (#163 S10, S13).
  Distinct from *freshness at cutoff*, which counts admitted live captures (#113); neither
  measures the other.
- **fixture schedule**: which gameweek a fixture is in, its kickoff time, its home and away
  teams, and each side's difficulty rating. Not its result: a score is a ratified outcome.
- **reschedule**: FPL changing a fixture's kickoff time after publishing it. A reschedule moves
  the fixture; the fixture keeps its id.
- **ratified outcome**: a gameweek's results after FPL has ratified its points and bonus
  (`is_ratified`, the `ratified` doc block in `models/marts/docs.md`). Not knowable before the
  deadline.

## Serving

- **served**: published to `served/` as parquet, `access: public` with an enforced contract
  (`CLAUDE.md`, "Served contract"). Consumers read only served tables.
- **private**: `access: private`; a model only this project's models and tests may `ref()`.
  Not published.

## Work

- **slice**: a Feature's vertical increment that delivers usable value end to end on its
  own (`AGENT_WORKFLOW.md`, "Story splitting").
- **gate**: an action only the human takes: merges, live writes, permission and access
  changes, workflow dispatches that write, and changes to a contract consumers depend on
  (`AGENT_WORKFLOW.md`, "Boundaries").

## Service levels

- **freshness at cutoff**: at each cutoff, the latest admitted live `bootstrap-static`
  capture before it is at most 15 min old. Target: ≥ 90% of gameweeks from GW6 of 2026-27,
  measured at the deadline, deadline − 1h and deadline − 5h (#113).

## Naming

- **column names** (#133 S8, limited by #163 S14b): a field read from FPL keeps FPL's name
  (`deadline_time`, `kickoff_time`). A point-in-time timestamp the warehouse derives ends in
  `_at` (`observed_at`, `last_capture_before_deadline_at`). SCD2 interval bounds are outside
  this rule and keep ADR 0001's `valid_from` / `valid_to`.

## Words to avoid

- **"snapshot"** unqualified: say capture, as-of state, or the model's name.
- **"latest"** without saying before what: say "latest before the deadline" or "latest
  admitted capture".
